# Lanez — Briefing Fase 3 para KIRO

## O que é o Lanez

MCP Server pessoal que conecta AI assistants aos dados do Microsoft 365. Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source.

---

## O que as Fases 1 e 2 entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan (Redis, DB, webhook renewal loop)
├── config.py            ← Settings (MICROSOFT_*, SECRET_KEY, SEARXNG_URL...)
├── database.py          ← AsyncSessionLocal, get_db(), get_redis(), engine
├── dependencies.py      ← get_current_user() (valida JWT)
├── models/
│   ├── __init__.py      ← importa Base + todos os modelos
│   ├── user.py          ← User (microsoft_access_token, microsoft_refresh_token)
│   ├── cache.py         ← GraphCache
│   └── webhook.py       ← WebhookSubscription
├── routers/
│   ├── auth.py          ← OAuth flow completo
│   ├── graph.py         ← GET /graph/{service}
│   ├── webhooks.py      ← POST /webhooks/graph, GET /webhooks/subscriptions
│   └── mcp.py           ← 5 ferramentas MCP (GET /mcp, POST /mcp/call, GET /mcp/sse)
├── schemas/
│   └── graph.py         ← ServiceType enum (CALENDAR, MAIL, ONENOTE, ONEDRIVE)
└── services/
    ├── cache.py         ← CacheService (Redis get/set/invalidate)
    ├── graph.py         ← GraphService (fetch_data, fetch_with_params, token refresh)
    ├── searxng.py       ← SearXNGService
    └── webhook.py       ← WebhookService.process_notification() → retorna bool

alembic/versions/
    001_initial_tables.py  ← users, graph_cache, webhook_subscriptions
```

**`pgvector==0.3.0` já está em `requirements.txt`** — apenas `sentence-transformers` precisa ser adicionado.

---

## Fase 3 — Busca Semântica (escopo desta entrega)

### Objetivo

Encontrar qualquer informação em emails, calendário, OneNote e OneDrive simultaneamente por **significado**, não por palavra-chave. A ferramenta `semantic_search` retorna os resultados mais relevantes de todos os serviços de uma só vez.

---

## O que implementar

### 1. Modelo SQLAlchemy — `app/models/embedding.py` (NOVO)

```python
import uuid
from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service = Column(String(20), nullable=False)        # "calendar" | "mail" | "onenote" | "onedrive"
    resource_id = Column(String(255), nullable=False)   # Graph API item ID (ou "id__chunk_i" para chunks)
    content_hash = Column(String(64), nullable=False)   # SHA-256 do texto — deduplicação
    vector = Column(Vector(384), nullable=False)        # embedding all-MiniLM-L6-v2
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "service", "resource_id", name="uq_embedding_user_service_resource"),
        Index(
            "ix_embeddings_vector_hnsw",
            vector,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )
```

---

### 2. Serviço de embeddings — `app/services/embeddings.py` (NOVO)

Contém tudo relacionado a embeddings: modelo singleton, extração de texto, chunking, ingestão e busca.

#### 2a. Singleton do modelo

```python
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def generate_embedding(text: str) -> list[float]:
    return get_model().encode(text).tolist()
```

#### 2b. Extração de texto por serviço

```python
def extract_text(service: str, data: dict) -> str:
    """Extrai texto relevante de um item Graph API para embedding."""
    if service == "calendar":
        parts = [data.get("subject", "")]
        if body := data.get("body", {}).get("content"):
            parts.append(body[:500])
        if attendees := data.get("attendees", []):
            names = [a.get("emailAddress", {}).get("name", "") for a in attendees]
            parts.append("Participantes: " + ", ".join(filter(None, names)))
        return " | ".join(filter(None, parts))

    elif service == "mail":
        return " | ".join(filter(None, [
            data.get("subject", ""),
            data.get("from", {}).get("emailAddress", {}).get("name", ""),
            data.get("bodyPreview", ""),
        ]))

    elif service == "onenote":
        return " | ".join(filter(None, [
            data.get("title", ""),
            data.get("contentUrl", ""),
        ]))

    elif service == "onedrive":
        return " | ".join(filter(None, [
            data.get("name", ""),
            data.get("description", ""),
        ]))

    return ""
```

#### 2c. Chunking para textos longos (> 512 tokens)

```python
def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Divide texto por parágrafo, respeitando limite de ~400 tokens (~1200 chars)."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current_chunk, current_len = [], [], 0

    for paragraph in paragraphs:
        plen = len(paragraph)
        if current_len + plen > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk, current_len = [paragraph], plen
        else:
            current_chunk.append(paragraph)
            current_len += plen

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks or [text[:max_chars]]
```

#### 2d. Ingestão com deduplicação por content_hash

```python
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.embedding import Embedding

async def ingest_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    service: str,
    resource_id: str,
    text: str,
) -> bool:
    """Gera e upserta o embedding de um item. Retorna True se houve mudança."""
    if not text.strip():
        return False

    content_hash = hashlib.sha256(text.encode()).hexdigest()

    result = await db.execute(
        select(Embedding).where(
            Embedding.user_id == user_id,
            Embedding.service == service,
            Embedding.resource_id == resource_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing and existing.content_hash == content_hash:
        return False  # conteúdo não mudou

    vector = generate_embedding(text)
    now = datetime.now(timezone.utc)

    if existing:
        existing.vector = vector
        existing.content_hash = content_hash
        existing.updated_at = now
    else:
        db.add(Embedding(
            user_id=user_id,
            service=service,
            resource_id=resource_id,
            content_hash=content_hash,
            vector=vector,
            updated_at=now,
        ))

    await db.commit()
    return True


async def ingest_graph_data(
    db: AsyncSession,
    user_id: uuid.UUID,
    service: str,
    resource_id: str,
    data: dict,
) -> None:
    """Extrai texto do item, faz chunking se necessário, ingere embeddings."""
    text = extract_text(service, data)
    if not text:
        return

    chunks = chunk_text(text)
    if len(chunks) == 1:
        await ingest_item(db, user_id, service, resource_id, chunks[0])
    else:
        for i, chunk in enumerate(chunks):
            await ingest_item(db, user_id, service, f"{resource_id}__chunk_{i}", chunk)
```

#### 2e. Busca semântica

```python
async def semantic_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 10,
    services: list[str] | None = None,
) -> list[dict]:
    """Busca por significado em todos os serviços. Threshold de distância: 0.5."""
    query_vector = generate_embedding(query)

    stmt = (
        select(
            Embedding,
            Embedding.vector.cosine_distance(query_vector).label("distance"),
        )
        .where(Embedding.user_id == user_id)
    )

    if services:
        stmt = stmt.where(Embedding.service.in_(services))

    stmt = stmt.order_by("distance").limit(limit)
    results = await db.execute(stmt)

    return [
        {
            "service": row.Embedding.service,
            "resource_id": row.Embedding.resource_id,
            "relevance_score": round(1 - row.distance, 4),
        }
        for row in results.all()
        if row.distance < 0.5  # descarta resultados com similaridade < 50%
    ]
```

---

### 3. Migração Alembic — `alembic/versions/002_add_embeddings.py` (NOVO)

```python
"""Add embeddings table with pgvector

Revision ID: 002_embeddings
Revises: 001_initial
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_embeddings"
down_revision = "001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", sa.Text(), nullable=False),  # pgvector gerencia o tipo
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "service", "resource_id",
                            name="uq_embedding_user_service_resource"),
    )
    op.create_index("ix_embeddings_user_id", "embeddings", ["user_id"])

    # Índice HNSW — deve ser criado depois da tabela, antes de inserir dados
    op.execute("""
        CREATE INDEX ix_embeddings_vector_hnsw
        ON embeddings USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_vector_hnsw")
    op.drop_index("ix_embeddings_user_id", table_name="embeddings")
    op.drop_table("embeddings")
```

**Atenção:** O tipo `vector` não tem representação nativa no SQLAlchemy migration — usar `op.execute()` para o índice HNSW. A tabela usa `sa.Text()` como placeholder, mas a coluna real é criada pelo `pgvector.sqlalchemy.Vector(384)` via `Base.metadata.create_all`. Em produção, o Alembic gerencia o schema; em desenvolvimento, o `create_all` no lifespan cuida disso.

---

### 4. Atualizar `app/models/__init__.py`

Importar o novo modelo para que `Base.metadata.create_all` o inclua:

```python
from app.models.embedding import Embedding  # adicionar esta linha
```

---

### 5. Precarregar modelo no lifespan — `app/main.py`

O modelo `all-MiniLM-L6-v2` leva ~2s para carregar e ocupa ~300MB de RAM. Deve ser carregado **uma vez** no startup, não a cada request.

```python
from app.services.embeddings import get_model  # adicionar import

# No lifespan, após init_redis():
get_model()  # força carregamento do modelo no startup
logger.info("Modelo de embeddings carregado")
```

---

### 6. Re-embedding via webhook — `app/services/webhook.py` (MODIFICAR)

Alterar o tipo de retorno de `process_notification` de `bool` para `tuple[uuid.UUID, ServiceType] | None`:
- Sucesso → retorna `(user_id, service_type)` (eram necessários para disparar o re-embedding)
- Falha (clientState inválido, subscrição não encontrada, resource desconhecido) → retorna `None`

```python
# Assinatura atual:
async def process_notification(...) -> bool:

# Nova assinatura:
async def process_notification(...) -> tuple[uuid.UUID, ServiceType] | None:
    # ... validações existentes retornam None em vez de False ...
    # No final, em vez de return True:
    return user_id, service_type
```

---

### 7. Disparar re-embedding no router de webhooks — `app/routers/webhooks.py` (MODIFICAR)

Usar `BackgroundTasks` do FastAPI para agendar re-embedding após processamento da notificação:

```python
from fastapi import BackgroundTasks
from app.services.embeddings import ingest_graph_data
from app.database import AsyncSessionLocal, get_redis
from app.services.graph import GraphService

async def _reingest_background(user_id: uuid.UUID, service_type: ServiceType) -> None:
    """Background task: busca dados frescos e regenera embeddings."""
    from app.services.graph import GraphService
    from app.services.embeddings import ingest_graph_data

    async with AsyncSessionLocal() as db:
        graph_svc = GraphService()
        try:
            redis = get_redis()  # acessa o client Redis global do lifespan
            response = await graph_svc.fetch_data(user_id, service_type, db, redis)
            data = response.data
            items = data.get("value", []) if isinstance(data, dict) else []

            for item in items:
                resource_id = item.get("id", "")
                if resource_id:
                    await ingest_graph_data(db, user_id, service_type.value, resource_id, item)
        except Exception:
            logger.exception(
                "Erro no re-embedding user_id=%s service=%s [token=REDACTED]",
                user_id,
                service_type.value,
            )
        finally:
            await graph_svc.close()


# No endpoint POST /webhooks/graph — adicionar BackgroundTasks:
@router.post("/graph")
async def receive_graph_notification(
    request: Request,
    background_tasks: BackgroundTasks,         # ← NOVO
    validation_token: str | None = ...,
    ...
) -> Response:
    ...
    for item in body.get("value", []):
        notification = WebhookNotification(...)
        try:
            result = await webhook_service.process_notification(notification, cache_service, db)
            if result is not None:
                user_id, service_type = result
                background_tasks.add_task(_reingest_background, user_id, service_type)  # ← NOVO
        except Exception:
            logger.exception(...)

    return Response(status_code=202)
```

**Atenção sobre `get_redis()`**: verificar como `get_redis()` está implementado em `database.py`. Se for um async generator de FastAPI, não pode ser chamado diretamente em uma background task. Nesse caso, importar a variável Redis global diretamente do módulo `database` (ex: `from app.database import _redis_client`). Adaptar conforme a implementação existente.

---

### 8. Adicionar ferramenta `semantic_search` ao MCP — `app/routers/mcp.py` (MODIFICAR)

Adicionar como 6ª ferramenta:

```python
TOOL_SEMANTIC_SEARCH = MCPTool(
    name="semantic_search",
    description=(
        "Busca por significado em todos os serviços do Microsoft 365 simultaneamente. "
        "Use quando o usuário quiser encontrar algo sem saber em qual serviço está, "
        "ou quando uma busca por palavra-chave não for suficiente. "
        "Exemplos: 'encontre informações sobre o projeto Alpha', "
        "'o que discutimos com João sobre contratos?'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Descrição do que você está buscando"},
            "services": {
                "type": "array",
                "items": {"type": "string", "enum": ["calendar", "mail", "onenote", "onedrive"]},
                "description": "Filtrar por serviços específicos (opcional — padrão: todos)",
            },
            "limit": {
                "type": "integer",
                "description": "Número máximo de resultados (padrão: 10, máximo: 20)",
            },
        },
        "required": ["query"],
    },
)
```

Handler:

```python
async def handle_semantic_search(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> list[dict]:
    from app.services.embeddings import semantic_search as _semantic_search
    query = arguments["query"]
    services = arguments.get("services")
    limit = min(int(arguments.get("limit", 10)), 20)
    return await _semantic_search(db, user.id, query, limit, services)
```

Adicionar ao `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS`.

---

### 9. Atualizar `requirements.txt`

Adicionar:
```
sentence-transformers==3.3.1
```

---

## Modelo de dados — novo

```
Embedding
├── id (uuid, PK)
├── user_id (uuid, FK → users.id ON DELETE CASCADE)
├── service (string: "calendar" | "mail" | "onenote" | "onedrive")
├── resource_id (string — Graph API item ID, ou "id__chunk_i" para chunks longos)
├── content_hash (string SHA-256 — deduplicação)
├── vector (Vector(384) — pgvector)
└── updated_at (datetime)

Constraint único: (user_id, service, resource_id)
Índice: HNSW com vector_cosine_ops (m=16, ef_construction=64)
```

---

## Estrutura de pastas — o que muda

```
# Novos:
app/models/embedding.py
app/services/embeddings.py
alembic/versions/002_add_embeddings.py

# Modificados:
app/models/__init__.py         ← importar Embedding
app/services/webhook.py        ← process_notification retorna tuple | None
app/routers/webhooks.py        ← BackgroundTasks + _reingest_background
app/routers/mcp.py             ← 6ª ferramenta semantic_search
app/main.py                    ← get_model() no startup
requirements.txt               ← sentence-transformers
```

---

## Decisões técnicas (não questionar)

- **Singleton do modelo**: carregar `SentenceTransformer` uma vez no startup — ~2s e ~300MB; por request seria inaceitável
- **HNSW em vez de IVFFlat**: melhor qualidade de busca, não requer dados pré-existentes nem VACUUM para calibração; IVFFlat é melhor para >1M vetores com restrição de memória
- **Coseno em vez de L2**: invariante ao comprimento do texto — emails longos e notas curtas sobre o mesmo assunto terão distância correta
- **content_hash SHA-256**: evita re-embedding quando webhook notifica mudança de metadados sem alteração de conteúdo (cenário comum)
- **Threshold 0.5**: resultados com distância coseno ≥ 0.5 (similaridade ≤ 50%) são descartados — muito poucos relevantes abaixo desse limiar para uso pessoal
- **Chunking por parágrafo a 1200 chars (~400 tokens)**: preserva contexto semântico; não corta frases no meio
- **BackgroundTasks para re-embedding**: webhook deve retornar 202 em <10s (exigência da Graph API); re-embedding em background não bloqueia a resposta
- **process_notification retorna tuple**: limpa — o router sabe exatamente o que agendou e não precisa inspecionar a notificação novamente

---

## O que NÃO fazer nesta fase

- Não usar OpenAI Embeddings API (custo, dependência externa)
- Não usar Pinecone, Weaviate ou outro banco vetorial separado (pgvector já está no stack)
- Não armazenar o texto bruto na tabela `embeddings` — apenas hash e vetor
- Não bloquear o handler do webhook esperando o re-embedding completar
- Não implementar memória persistente (Fase 4)
- Não implementar briefing automático (Fase 5)

---

## Entregáveis esperados da Fase 3

1. `app/models/embedding.py` — modelo SQLAlchemy com Vector(384) e índice HNSW
2. `app/services/embeddings.py` — singleton, extract_text, chunk_text, ingest_graph_data, semantic_search
3. `alembic/versions/002_add_embeddings.py` — migration: CREATE EXTENSION vector + CREATE TABLE embeddings
4. `app/models/__init__.py` atualizado — importa Embedding
5. `app/services/webhook.py` atualizado — process_notification retorna tuple | None
6. `app/routers/webhooks.py` atualizado — BackgroundTasks + _reingest_background
7. `app/routers/mcp.py` atualizado — 6ª ferramenta semantic_search
8. `app/main.py` atualizado — get_model() no lifespan
9. `requirements.txt` atualizado — sentence-transformers

---

## Verificação funcional

```bash
# 1. Verificar que a ferramenta aparece no MCP
curl -s http://localhost:8000/mcp -H "Authorization: Bearer JWT" | python -m json.tool
# Esperado: lista com 6 ferramentas incluindo semantic_search

# 2. Busca semântica via MCP
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-sem",
    "method": "tools/call",
    "params": {
      "name": "semantic_search",
      "arguments": {"query": "reunião de planejamento", "limit": 5}
    }
  }' | python -m json.tool
# Esperado: lista de {service, resource_id, relevance_score} com score > 0.5

# 3. Verificar tabela no banco
psql -U lanez -d lanez -c "SELECT COUNT(*) FROM embeddings;"
# Esperado: > 0 após webhook ou ingestão manual
```
