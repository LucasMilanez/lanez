# Lanez — Briefing Fase 4 para KIRO

## O que é o Lanez

MCP Server pessoal que conecta AI assistants aos dados do Microsoft 365. Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source.

---

## O que as Fases 1-3 entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan (Redis, DB, modelo de embeddings, webhook renewal)
├── config.py            ← Settings (MICROSOFT_*, SECRET_KEY, SEARXNG_URL...)
├── database.py          ← AsyncSessionLocal, get_db(), get_redis(), engine
├── dependencies.py      ← get_current_user() (valida JWT)
├── models/
│   ├── __init__.py      ← Base + User + GraphCache + WebhookSubscription + Embedding
│   ├── user.py
│   ├── cache.py
│   ├── webhook.py
│   └── embedding.py     ← Embedding (Vector(384), HNSW)
├── routers/
│   ├── auth.py
│   ├── graph.py
│   ├── webhooks.py      ← POST /webhooks/graph com BackgroundTasks (re-embedding)
│   └── mcp.py           ← 6 ferramentas (incluindo semantic_search)
├── schemas/
│   └── graph.py         ← ServiceType (CALENDAR, MAIL, ONENOTE, ONEDRIVE)
└── services/
    ├── cache.py
    ├── graph.py
    ├── searxng.py
    ├── webhook.py       ← process_notification → tuple[UUID, ServiceType] | None
    └── embeddings.py    ← get_model, generate_embedding, extract_text, chunk_text,
                           ingest_item, ingest_graph_data, semantic_search

alembic/versions/
    001_initial_tables.py
    002_add_embeddings.py
```

**Reutilizar da Fase 3:**
- `get_model()` e `generate_embedding()` de `app/services/embeddings.py` — NÃO criar outro singleton
- Padrão de migration com `op.execute()` para HNSW
- Padrão de tool MCP (description hardcoded, inputSchema, handler)

`pgvector==0.3.0` e `sentence-transformers==3.3.1` já estão em `requirements.txt`. Nenhuma dependência nova.

---

## Fase 4 — Memória Persistente (escopo desta entrega)

### Objetivo

O AI assistant lembra contexto entre sessões. O usuário (ou o próprio AI, via MCP) salva decisões, projetos em andamento, preferências e fatos importantes. Em sessões futuras, o AI recupera memórias relevantes para a conversa atual usando busca semântica.

### Diferença vs Embedding (Fase 3)

| Aspecto | Embedding (Fase 3) | Memory (Fase 4) |
|---|---|---|
| Origem | Microsoft Graph API (autoingestão via webhook) | Input explícito do user/AI via MCP tool |
| Conteúdo armazenado | Apenas hash + vetor (texto extraído do Graph) | Texto completo + tags + vetor |
| Deduplicação | Sim (content_hash, evita re-embedding desnecessário) | **Não** — cada `save_memory` cria nova entrada |
| Atualização | Upsert por (user_id, service, resource_id) | Sempre INSERT novo |
| Tags | N/A | `ARRAY(String)` filtrável |
| Acesso por tempo | `updated_at` apenas | `created_at` + `last_accessed_at` (atualizado em recall) |

---

## O que implementar

### 1. Modelo SQLAlchemy — `app/models/memory.py` (NOVO)

```python
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Memory(Base):
    """Memória persistente do AI — salva contexto, decisões, preferências."""

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    vector = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_memories_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
        Index("ix_memories_user_created", "user_id", "created_at"),
        Index("ix_memories_tags_gin", "tags", postgresql_using="gin"),
    )
```

**Atenção sobre `tags`:**
- Usar `sqlalchemy.ARRAY(String)` — tipo nativo do PostgreSQL, indexável com GIN.
- **Não** usar JSON ou JSONB para tags. Arrays nativos são mais rápidos para `ANY()` e `@>`.
- Default `list` (não `[]`) para evitar mutable default no SQLAlchemy.

---

### 2. Serviço de memória — `app/services/memory.py` (NOVO)

Reutiliza `generate_embedding()` do `app/services/embeddings.py`. Não duplicar o singleton.

```python
"""Serviço de memória persistente — save_memory e recall_memory.

Reutiliza generate_embedding() de app.services.embeddings (mesmo modelo
all-MiniLM-L6-v2). Memórias são input intencional do user/AI, sem deduplicação.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.embeddings import generate_embedding


_RECALL_DISTANCE_THRESHOLD = 0.5
_RECALL_LIMIT_DEFAULT = 5
_RECALL_LIMIT_MAX = 20


async def save_memory(
    db: AsyncSession,
    user_id: UUID,
    content: str,
    tags: list[str] | None = None,
) -> dict:
    """Persiste uma memória nova. Sempre INSERT — nunca atualiza existentes.

    Args:
        content: Texto da memória. Não pode ser vazio (após strip).
        tags: Lista opcional de tags. Strings vazias são filtradas.

    Returns:
        dict com id, content, tags, created_at.

    Raises:
        ValueError: se content vazio (chamador deve tratar).
    """
    if not content.strip():
        raise ValueError("content não pode ser vazio")

    clean_tags = [t.strip() for t in (tags or []) if t.strip()]
    vector = generate_embedding(content)
    now = datetime.now(timezone.utc)

    memory = Memory(
        user_id=user_id,
        content=content,
        tags=clean_tags,
        vector=vector,
        created_at=now,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    return {
        "id": str(memory.id),
        "content": memory.content,
        "tags": memory.tags,
        "created_at": memory.created_at.isoformat(),
    }


async def recall_memory(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    tags: list[str] | None = None,
    limit: int = _RECALL_LIMIT_DEFAULT,
) -> list[dict]:
    """Recupera memórias relevantes por busca semântica + filtro de tags.

    - Filtra por user_id (multi-tenant)
    - Filtro opcional de tags: memória deve conter PELO MENOS UMA tag (OR)
    - Threshold de distância coseno: 0.5
    - Atualiza last_accessed_at dos resultados retornados
    """
    if not query.strip():
        return []

    limit = min(max(limit, 1), _RECALL_LIMIT_MAX)
    query_vector = generate_embedding(query)

    distance_col = Memory.vector.cosine_distance(query_vector).label("distance")

    stmt = select(Memory, distance_col).where(Memory.user_id == user_id)

    if tags:
        clean_tags = [t.strip() for t in tags if t.strip()]
        if clean_tags:
            # tags && clean_tags — sobreposição (OR)
            stmt = stmt.where(Memory.tags.overlap(clean_tags))

    stmt = stmt.order_by("distance").limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    filtered = [
        (row.Memory, row.distance)
        for row in rows
        if row.distance < _RECALL_DISTANCE_THRESHOLD
    ]

    if filtered:
        ids = [m.id for m, _ in filtered]
        now = datetime.now(timezone.utc)
        await db.execute(
            update(Memory).where(Memory.id.in_(ids)).values(last_accessed_at=now)
        )
        await db.commit()

    return [
        {
            "id": str(memory.id),
            "content": memory.content,
            "tags": memory.tags,
            "created_at": memory.created_at.isoformat(),
            "relevance_score": round(1 - distance, 4),
        }
        for memory, distance in filtered
    ]
```

**Atenção sobre `Memory.tags.overlap()`:**
- `overlap()` corresponde ao operador `&&` do PostgreSQL — verdadeiro se há sobreposição.
- Se quiser "contém TODAS as tags" use `Memory.tags.contains(clean_tags)` (`@>`). **Decisão: usar `overlap()` (OR)** — ergonomia melhor para memórias.

---

### 3. Migração Alembic — `alembic/versions/003_add_memories.py` (NOVO)

```python
"""Add memories table with pgvector and tags array

Revision ID: 003_memories
Revises: 002_embeddings
Create Date: 2026-04-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_memories"
down_revision: Union[str, None] = "002_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("vector", sa.Text(), nullable=False),  # pgvector gerencia
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_memories_user_created", "memories", ["user_id", "created_at"]
    )

    # GIN index em tags
    op.execute("CREATE INDEX ix_memories_tags_gin ON memories USING gin(tags)")

    # HNSW index em vector
    op.execute(
        "CREATE INDEX ix_memories_vector_hnsw ON memories "
        "USING hnsw (vector vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memories_tags_gin")
    op.drop_index("ix_memories_user_created", table_name="memories")
    op.drop_table("memories")
```

**Atenção:**
- A extensão `vector` já foi criada na migration 002 — não recriar.
- `server_default=sa.text("ARRAY[]::varchar[]")` garante array vazio default.

---

### 4. Atualizar `app/models/__init__.py`

```python
from app.models.memory import Memory  # adicionar

__all__ = [
    "Base",
    "Embedding",
    "GraphCache",
    "Memory",   # adicionar
    "User",
    "WebhookSubscription",
]
```

---

### 5. Adicionar tools `save_memory` e `recall_memory` ao MCP — `app/routers/mcp.py` (MODIFICAR)

#### 5a. Definições de tools

```python
TOOL_SAVE_MEMORY = MCPTool(
    name="save_memory",
    description=(
        "Salve uma memória persistente que deve ser lembrada em sessões futuras. "
        "Use para registrar decisões, preferências do usuário, fatos sobre projetos em "
        "andamento, ou contexto que não está nos dados do Microsoft 365. "
        "Exemplos: 'Usuário prefere reuniões antes das 11h', "
        "'Decidimos adiar o lançamento do produto Alpha para Q3'."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Texto da memória — descreva o fato/decisão/preferência claramente",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags opcionais para filtragem futura (ex: ['preferencia', 'projeto-alpha'])",
            },
        },
        "required": ["content"],
    },
)

TOOL_RECALL_MEMORY = MCPTool(
    name="recall_memory",
    description=(
        "Recupere memórias relevantes para a conversa atual via busca semântica. "
        "Use no início de uma nova sessão ou quando precisar de contexto sobre "
        "decisões/preferências passadas. "
        "Exemplos: 'O que sabemos sobre o projeto Alpha?', "
        "'Quais preferências o usuário tem para reuniões?'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Descrição do que você está procurando lembrar",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrar por tags (opcional — retorna memórias com pelo menos uma das tags)",
            },
            "limit": {
                "type": "integer",
                "description": "Número máximo de resultados (padrão: 5, máximo: 20)",
            },
        },
        "required": ["query"],
    },
)
```

#### 5b. Handlers

```python
async def handle_save_memory(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    from app.services.memory import save_memory as _save_memory

    content = arguments["content"]
    tags = arguments.get("tags")
    return await _save_memory(db, user.id, content, tags)


async def handle_recall_memory(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> list[dict]:
    from app.services.memory import recall_memory as _recall_memory

    query = arguments["query"]
    tags = arguments.get("tags")
    limit = min(int(arguments.get("limit", 5)), 20)
    return await _recall_memory(db, user.id, query, tags, limit)
```

#### 5c. Registrar nas 3 estruturas

```python
TOOLS_REGISTRY: dict[str, Any] = {
    "get_calendar_events": handle_get_calendar_events,
    "search_emails": handle_search_emails,
    "get_onenote_pages": handle_get_onenote_pages,
    "search_files": handle_search_files,
    "web_search": handle_web_search,
    "semantic_search": handle_semantic_search,
    "save_memory": handle_save_memory,         # NOVO
    "recall_memory": handle_recall_memory,     # NOVO
}

TOOLS_MAP: dict[str, MCPTool] = {
    # ... 6 anteriores ...
    "save_memory": TOOL_SAVE_MEMORY,           # NOVO
    "recall_memory": TOOL_RECALL_MEMORY,       # NOVO
}

ALL_TOOLS: list[MCPTool] = [
    # ... 6 anteriores ...
    TOOL_SAVE_MEMORY,
    TOOL_RECALL_MEMORY,
]
```

**Total de ferramentas após Fase 4: 8.**

---

### 6. Tratamento de erro de domínio em `save_memory`

`save_memory` levanta `ValueError` quando `content` é vazio. O dispatcher de `call_tool` em `app/routers/mcp.py` já captura `Exception` genérica e converte em `jsonrpc_domain_error`. Mas é melhor levantar `HTTPException(400)` no handler para que o erro de cliente seja explícito:

```python
async def handle_save_memory(...) -> dict:
    from fastapi import HTTPException
    from app.services.memory import save_memory as _save_memory

    content = arguments["content"]
    tags = arguments.get("tags")

    try:
        return await _save_memory(db, user.id, content, tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

O dispatch de `call_tool` já converte `HTTPException` em `jsonrpc_domain_error` — comportamento correto.

**Alternativa simples**: deixar a validação de content vazio acontecer no service (levantar `ValueError`) e confiar no dispatcher genérico. Decidir conforme o que o KIRO achar mais limpo. Recomendado: explicit é melhor.

---

## Modelo de dados — novo

```
Memory
├── id (uuid, PK)
├── user_id (uuid, FK → users.id ON DELETE CASCADE)
├── content (text — sem limite)
├── tags (varchar[] — array PostgreSQL)
├── vector (Vector(384) — pgvector)
├── created_at (datetime tz)
└── last_accessed_at (datetime tz, nullable)

Índices:
- ix_memories_vector_hnsw (HNSW vector_cosine_ops, m=16, ef_construction=64)
- ix_memories_user_created (B-tree em (user_id, created_at) — listagens cronológicas)
- ix_memories_tags_gin (GIN em tags — filtros por tag)
```

---

## Estrutura de pastas — o que muda

```
# Novos:
app/models/memory.py
app/services/memory.py
alembic/versions/003_add_memories.py

# Modificados:
app/models/__init__.py     ← importar Memory
app/routers/mcp.py         ← TOOL_SAVE_MEMORY, TOOL_RECALL_MEMORY, handlers, registries

# NÃO mexer:
app/services/embeddings.py ← reutilizar generate_embedding(), nada a alterar
app/main.py                ← lifespan já carrega o modelo (Fase 3)
requirements.txt           ← nenhuma dependência nova
```

---

## Decisões técnicas (não questionar)

- **Reuso do modelo all-MiniLM-L6-v2**: não criar outro singleton, importar `generate_embedding` de `app.services.embeddings`. O modelo já é carregado no startup pela Fase 3.
- **ARRAY(String) nativo, não JSON**: PostgreSQL tem suporte nativo a arrays com índice GIN — performance e ergonomia (`overlap()`, `contains()`) muito superiores a JSON.
- **Sem deduplicação por content_hash**: memórias são input intencional, podem se repetir (ex: registrar a mesma preferência sob ângulos diferentes). Cada `save_memory` é um INSERT novo.
- **Threshold 0.5 em recall_memory**: mesmo da Fase 3 — descartar resultados com cosine_distance ≥ 0.5.
- **Limit padrão 5, máx 20**: memórias são contexto direto para o AI — limites menores que `semantic_search` (10/20) porque a relevância tende a ser mais focada.
- **`overlap()` para tags**: filtro OR (memória deve ter PELO MENOS UMA tag da lista). Mais útil que AND para memórias.
- **`last_accessed_at` atualizado em `recall`**: permite ranking/decay futuro (Fase 5/6) e detectar memórias órfãs nunca usadas.
- **Tools separadas (save vs recall)**: cada uma tem propósito claro; agrupar em uma `manage_memory(action, ...)` aumenta superfície de erro do AI.
- **Filtro de tags com `.strip()` e descartar vazias**: defesa contra inputs malformados do AI (ex: `["", " ", "valid"]` → `["valid"]`).

---

## O que NÃO fazer nesta fase

- Não implementar update/delete de memória (ficam para futuro)
- Não implementar decay automático ou compactação de memórias antigas
- Não usar memórias automaticamente em briefings — isso é Fase 5
- Não criar endpoint REST direto (`/memories`) — apenas via MCP
- Não persistir embeddings das memórias na tabela `embeddings` (são tabelas separadas)
- Não criar webhook trigger para memória — memórias são input explícito, não derivam de Graph
- Não usar JSONB para tags (PostgreSQL ARRAY é melhor)
- Não levar adiante issues anotados da Fase 3 (chunks órfãos do `ingest_graph_data`) — escopo separado

---

## Entregáveis esperados da Fase 4

1. `app/models/memory.py` — modelo SQLAlchemy com Vector(384), ARRAY(String), HNSW + GIN
2. `app/services/memory.py` — `save_memory` e `recall_memory` (reusa `generate_embedding`)
3. `alembic/versions/003_add_memories.py` — migration: tabela memories + 3 índices (HNSW, GIN, B-tree composto)
4. `app/models/__init__.py` atualizado — importa Memory, adiciona ao `__all__`
5. `app/routers/mcp.py` atualizado — 8 ferramentas no total (6 anteriores + save_memory + recall_memory)

---

## Testes (mesmo rigor da Fase 3)

### Property-based tests (Hypothesis)

1. **`test_property_memory_vector_dim`** — embedding gerado por `save_memory` sempre tem 384 dims (validar via mock + count, ou verificar que `generate_embedding` é chamado).
2. **`test_property_memory_tags_cleaned`** — strings vazias em tags são filtradas em `save_memory` (input arbitrário com strings vazias misturadas → output sem vazias).
3. **`test_property_recall_threshold`** — todos os resultados de `recall_memory` têm `relevance_score > 0.5`.
4. **`test_property_recall_empty_query`** — `recall_memory` com query vazia retorna `[]`, sem hit no banco.
5. **`test_property_save_memory_rejects_empty`** — `save_memory` com content vazio/whitespace levanta `ValueError`, sem `db.add`.

### Edge cases

1. **`test_save_memory_empty_content`** — content="" e content="   " → ValueError.
2. **`test_save_memory_no_tags`** — tags=None e tags=[] → memória persistida com `tags=[]`.
3. **`test_save_memory_dirty_tags`** — `tags=["", "a", " ", "b"]` → memória persistida com `tags=["a", "b"]`.
4. **`test_recall_memory_no_results`** — banco vazio → `[]`.
5. **`test_recall_memory_below_threshold`** — todos os resultados com distance ≥ 0.5 → `[]`.
6. **`test_recall_memory_with_tags_filter`** — verifica que `Memory.tags.overlap(...)` é aplicado na query (mock de db.execute).
7. **`test_recall_memory_limit_capped`** — `recall_memory(..., limit=100)` → query usa `limit=20`.
8. **`test_recall_memory_updates_last_accessed`** — após recall com hits, `update(Memory).values(last_accessed_at=...)` é executado para os IDs retornados.
9. **`test_mcp_save_memory_missing_content`** — POST /mcp/call sem `content` → `error -32602`.
10. **`test_mcp_recall_memory_missing_query`** — POST /mcp/call sem `query` → `error -32602`.
11. **`test_mcp_list_tools_returns_8`** — GET /mcp retorna 8 ferramentas, incluindo `save_memory` e `recall_memory`.

---

## Verificação funcional

```bash
# 1. Lista de ferramentas — esperado 8
curl -s http://localhost:8000/mcp -H "Authorization: Bearer JWT" | python -m json.tool
# Esperado: tools com 8 entradas, incluindo save_memory e recall_memory

# 2. Salvar memória
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "save-1",
    "method": "tools/call",
    "params": {
      "name": "save_memory",
      "arguments": {
        "content": "Usuario prefere reuniões antes das 11h da manhã",
        "tags": ["preferencia", "agenda"]
      }
    }
  }' | python -m json.tool
# Esperado: result com {id, content, tags, created_at}

# 3. Recuperar por query semântica
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "recall-1",
    "method": "tools/call",
    "params": {
      "name": "recall_memory",
      "arguments": {"query": "qual a preferência do usuário para horários?"}
    }
  }' | python -m json.tool
# Esperado: array com a memoria salva acima, relevance_score > 0.5

# 4. Recuperar com filtro de tags
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "recall-2",
    "method": "tools/call",
    "params": {
      "name": "recall_memory",
      "arguments": {"query": "preferencias", "tags": ["preferencia"]}
    }
  }' | python -m json.tool

# 5. Verificar tabela
psql -U lanez -d lanez -c "SELECT id, content, tags, created_at, last_accessed_at FROM memories;"
# Esperado: 1+ linhas, last_accessed_at atualizado após o passo 3
```

---

## Pontos de atenção para o KIRO

1. **Reuso do modelo de embeddings**: NÃO recriar singleton `_model` em `memory.py`. Importar `generate_embedding` de `app.services.embeddings`.
2. **`ARRAY(String)` em SQLAlchemy**: `from sqlalchemy import ARRAY, String` — comportamento diferente de Lists Python. `Memory.tags.overlap(...)` é o método ORM correspondente ao `&&`.
3. **HNSW em memória vazia**: a Fase 3 já lida com isso (índice criado em raw SQL). Replicar exatamente o padrão.
4. **GIN index em tags**: criar via raw SQL na migration (`CREATE INDEX ... USING gin(tags)`). O modelo SQLAlchemy também declara `postgresql_using="gin"` para `Base.metadata.create_all` em dev.
5. **`db.refresh(memory)` após commit**: garante que `id` (default uuid4) e `created_at` estejam populados no objeto retornado.
6. **Atualização de `last_accessed_at`**: usar `update(...).where(...).values(...)` em batch, não loop. Commit no fim. Se `filtered` for vazio, pular o update.
7. **Erro -32602 quando content/query ausentes**: já tratado pelo dispatcher genérico em `call_tool` (validação via `inputSchema.required`). Apenas verificar que `required` está correto em ambos os schemas.
8. **`save_memory` levanta `ValueError` para content vazio**: o handler MCP deve converter para `HTTPException(400)` (que vira `jsonrpc_domain_error`). Não retornar dict de erro manual.
