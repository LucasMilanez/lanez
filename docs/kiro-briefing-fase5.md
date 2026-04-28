# Lanez — Briefing Fase 5 para KIRO

## O que é o Lanez

MCP Server pessoal que conecta AI assistants aos dados do Microsoft 365. Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source. Branch `main` em sincronia com `origin/main`, suíte 123/123 verde.

---

## O que as Fases 1-4.5 entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan (Redis, DB, modelo de embeddings, webhook renewal)
├── config.py            ← Settings (MICROSOFT_*, SECRET_KEY, SEARXNG_URL...)
├── database.py          ← AsyncSessionLocal, get_db (commit/rollback no boundary), get_redis
├── dependencies.py      ← get_current_user() (valida JWT)
├── models/
│   ├── __init__.py      ← Base + User + GraphCache + WebhookSubscription + Embedding + Memory
│   ├── user.py
│   ├── cache.py
│   ├── webhook.py
│   ├── embedding.py     ← Embedding (Vector(384), HNSW)
│   └── memory.py        ← Memory (Vector(384), HNSW, GIN tags)
├── routers/
│   ├── auth.py
│   ├── graph.py
│   ├── webhooks.py      ← POST /webhooks/graph com BackgroundTasks (re-embedding)
│   └── mcp.py           ← 8 ferramentas
└── services/
    ├── cache.py
    ├── graph.py
    ├── searxng.py
    ├── webhook.py       ← process_notification → tuple[UUID, ServiceType] | None
    ├── embeddings.py    ← generate_embedding, ingest_graph_data, semantic_search
    └── memory.py        ← save_memory (flush), recall_memory

alembic/versions/
    001_initial_tables.py
    002_add_embeddings.py
    003_add_memories.py
```

**Reutilizar das fases anteriores:**
- `recall_memory` em `app/services/memory.py` — para puxar memórias relevantes ao montar o contexto do briefing
- `semantic_search` em `app/services/embeddings.py` — para encontrar conteúdo semanticamente relacionado ao tema da reunião em emails/OneNote/OneDrive
- `GraphService.fetch_data` / `fetch_with_params` em `app/services/graph.py` — para buscar evento, emails, arquivos e páginas
- Padrão de `BackgroundTasks` em `app/routers/webhooks.py::receive_graph_notification` (já existe `_reingest_background`) — mesmo modelo para a geração de briefing
- Padrão de tool MCP (description hardcoded, inputSchema, handler) em `app/routers/mcp.py`
- Padrão de migration com `Vector(384)`, `server_default`, e `op.execute()` para índices não-nativos do Alembic

**`process_notification` atual retorna `tuple[UUID, ServiceType] | None`.** Para a Fase 5 será necessário **extrair o `event_id` específico do resource da notificação** (formato: `Users/{user-guid}/Events/{event-id}`). Isso será uma modificação localizada — ver seção 5.7.

---

## Fase 5 — Briefing Automático de Reunião (escopo desta entrega)

### Objetivo

Quando um evento é criado ou alterado no Outlook calendar do usuário, o sistema gera automaticamente um briefing estruturado em Markdown contendo: contexto da reunião, histórico com participantes (emails recentes), notas e arquivos relevantes (OneNote, OneDrive), memórias relacionadas (`recall_memory`) e sugestões para a reunião. O briefing é gerado por **Claude Haiku 4.5** com **prompt caching ativo**, persistido na tabela `briefings`, e exposto via **endpoint REST** + **ferramenta MCP** `get_briefing`.

### Decisões técnicas (já aprovadas pelo usuário)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Modelo LLM | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Mais barato dos modelos Anthropic 4.x; suficiente para síntese estruturada com contexto provido. Custo estimado ~$0,013/briefing → ~$2/mês para 5 reuniões/dia |
| Trigger | Webhook calendar → `BackgroundTasks` | Webhook do Graph exige resposta 202 em <30s; geração leva 10-60s. Padrão já estabelecido em `_reingest_background` |
| Exposição | REST `GET /briefings/{event_id}` + MCP tool `get_briefing` | REST para Fase 6 (painel React); MCP para Claude Desktop puxar antes da reunião. Service compartilhado |
| Janela histórica | `BRIEFING_HISTORY_WINDOW_DAYS=90` em `app/config.py` (configurável via env) | Setting global por enquanto; UI de configuração por usuário fica para Fase 6 |
| SDK | `anthropic` oficial Python com **prompt caching** ativo | System prompt fixo (~2k tokens) faz cache hit valer a partir do 2º briefing |

---

## O que implementar

### 5.1 Configuração nova — `app/config.py`

Adicionar dois campos a `Settings`:

```python
# Anthropic API — obrigatório para Fase 5
ANTHROPIC_API_KEY: str

# Briefing — janela histórica de coleta de contexto (em dias)
BRIEFING_HISTORY_WINDOW_DAYS: int = 90
```

`ANTHROPIC_API_KEY` é obrigatório (sem default) — a aplicação falha na inicialização se não estiver definido em `.env`. Adicionar entrada vazia em `.env.example` (criar se não existir) com comentário sobre onde obter a chave.

---

### 5.2 Schema Pydantic — `app/schemas/briefing.py` (NOVO)

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BriefingResponse(BaseModel):
    """Schema de resposta para briefing — usado pelo endpoint REST e tool MCP."""
    id: UUID
    event_id: str
    event_subject: str
    event_start: datetime
    event_end: datetime
    attendees: list[str]
    content: str  # Markdown gerado pelo Haiku
    generated_at: datetime
    model_used: str
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
```

---

### 5.3 Modelo SQLAlchemy — `app/models/briefing.py` (NOVO)

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Briefing(Base):
    """Briefing gerado automaticamente para um evento de calendar."""

    __tablename__ = "briefings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attendees: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_briefing_user_event"),
        Index("ix_briefings_user_event_start", "user_id", "event_start"),
    )
```

E em `app/models/__init__.py`, importar `Briefing` e adicionar a `__all__` em ordem alfabética (entre `Base` e `Embedding`).

---

### 5.4 Migration Alembic — `alembic/versions/004_add_briefings.py` (NOVO)

`revision = "004_briefings"`, `down_revision = "003_memories"`. Criar tabela `briefings` com:

- `id` Uuid PK `server_default=sa.text("gen_random_uuid()")`
- `user_id` Uuid FK `users.id` ON DELETE CASCADE not null
- `event_id` String(255) not null
- `event_subject` String(500) not null
- `event_start` DateTime(timezone=True) not null
- `event_end` DateTime(timezone=True) not null
- `attendees` ARRAY(String) not null `server_default=sa.text("ARRAY[]::varchar[]")`
- `content` Text not null
- `model_used` String(64) not null
- `input_tokens` Integer not null `server_default=sa.text("0")`
- `cache_read_tokens` Integer not null `server_default=sa.text("0")`
- `cache_write_tokens` Integer not null `server_default=sa.text("0")`
- `output_tokens` Integer not null `server_default=sa.text("0")`
- `generated_at` DateTime(timezone=True) not null

Constraints: `UniqueConstraint("user_id", "event_id", name="uq_briefing_user_event")` + B-tree composto `ix_briefings_user_event_start` em (user_id, event_start).

`downgrade` simétrico (drop index + drop table).

**Aplicar lições da Fase 4.5** desde o início: `server_default` (não `default`), tipos corretos para todas as colunas, downgrade limpo.

---

### 5.5 Cliente Anthropic — `app/services/anthropic_client.py` (NOVO)

Encapsular o uso do SDK oficial `anthropic` com prompt caching e telemetria de tokens.

```python
"""Cliente Claude para geração de briefings.

Usa SDK oficial anthropic com prompt caching ativo. O system prompt é fixo
e marcado como cacheable (cache_control type=ephemeral). O cache TTL padrão
da Anthropic é 5 minutos — para uso esporádico, cada nova reunião paga cache
write na primeira chamada e hit nas seguintes dentro da janela.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic

from app.config import settings

_MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1500


class BriefingResult:
    content: str
    model: str
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int


_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    """Retorna cliente Anthropic singleton."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def generate_briefing_text(
    system_prompt: str,
    user_content: str,
) -> BriefingResult:
    """Chama Claude Haiku 4.5 e retorna texto + telemetria de tokens.

    O system_prompt é marcado como cacheable. Estrutura da chamada:

        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )

    Retorna BriefingResult com:
    - content: response.content[0].text
    - model: response.model
    - input_tokens: response.usage.input_tokens
    - cache_read_tokens: response.usage.cache_read_input_tokens (0 se ausente)
    - cache_write_tokens: response.usage.cache_creation_input_tokens (0 se ausente)
    - output_tokens: response.usage.output_tokens
    """
```

**Implementar exatamente como descrito.** Não criar wrapper genérico para outros usos do Claude — esse cliente é específico para briefings.

**Adicionar `anthropic>=0.40.0` em `requirements.txt`.**

---

### 5.6 Service de coleta de contexto — `app/services/briefing_context.py` (NOVO)

Responsabilidade isolada: dado um `event_id`, coletar todo o contexto necessário para o briefing. Retorna um dict estruturado que será serializado no user prompt.

```python
async def collect_briefing_context(
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    user: User,
    event_id: str,
    history_window_days: int,
) -> dict:
    """Coleta contexto multi-fonte para um evento.

    Retorna dict com:
    - event: {subject, start, end, location, body_preview, attendees: [emails]}
    - emails_with_attendees: lista de até 10 emails (subject + bodyPreview + receivedDateTime)
      filtrados pelos últimos history_window_days e onde o from/to inclui pelo menos um attendee
    - onenote_pages: lista de até 5 páginas via semantic_search(subject, services=["onenote"], limit=5)
    - onedrive_files: lista de até 5 arquivos via semantic_search(subject, services=["onedrive"], limit=5)
    - memories: lista de até 5 memórias via recall_memory(subject + " " + " ".join(attendees), limit=5)

    Se algum bloco falhar (Graph 404, etc.), loga warning e retorna lista vazia
    para esse bloco — nunca propaga exceção. O briefing deve ser gerado mesmo
    com contexto parcial.
    """
```

**Detalhes da coleta:**

1. **Evento** — `graph.fetch_with_params(user, f"/me/events/{event_id}", params, db, redis)` com `$select=subject,start,end,location,bodyPreview,attendees`. Extrair lista de emails dos `attendees[].emailAddress.address`.

2. **Emails com participantes** — `graph.fetch_with_params(user, "/me/messages", params, db, redis)` com:
   - `$select=subject,from,toRecipients,receivedDateTime,bodyPreview`
   - `$top=10`
   - `$orderby=receivedDateTime desc`
   - `$filter=receivedDateTime ge {ISO de hoje - history_window_days}`
   - Filtragem em Python: manter apenas emails onde `from.emailAddress.address` ou algum `toRecipients[].emailAddress.address` está na lista de attendees

3. **OneNote** — Reutilizar `semantic_search(db, user.id, query=event_subject, limit=5, services=["onenote"])` da Fase 3.

4. **OneDrive** — `semantic_search(db, user.id, query=event_subject, limit=5, services=["onedrive"])`.

5. **Memórias** — `recall_memory(db, user.id, query=f"{event_subject} {' '.join(attendees)}", limit=5)` da Fase 4.

Cada fonte é independente — se uma falha, as outras continuam.

---

### 5.7 Service orquestrador — `app/services/briefing.py` (NOVO)

Responsabilidade: orquestrar coleta + LLM + persistência. **Não chama `commit()` diretamente** (regra herdada da Fase 4.5).

```python
SYSTEM_PROMPT = """\
Você é um assistente que prepara briefings para reuniões de trabalho. Para cada
reunião, gere um briefing conciso em Markdown com EXATAMENTE estas seções
(nesta ordem, com esses títulos):

## Contexto
[1-3 frases explicando do que se trata a reunião, baseado no assunto e na agenda fornecida]

## Participantes
[Para cada participante listado: 1 linha com email e papel/observação relevante extraída
do contexto fornecido]

## Histórico recente
[Bullets com últimas trocas relevantes — emails, decisões. Cite a data quando útil.
Se não há histórico, escreva "Sem trocas recentes registradas."]

## Documentos relevantes
[Bullets com links/títulos de OneNote e OneDrive — 1 linha de descrição por item.
Se vazio, escreva "Sem documentos diretamente relacionados."]

## Memórias relevantes
[Bullets com memórias passadas relevantes recuperadas. Se vazio, omitir esta seção
inteira (não escreva título)]

## Sugestões para a reunião
[2-3 bullets curtos com perguntas, materiais a preparar ou decisões pendentes]

REGRAS:
- Use APENAS o contexto fornecido. NÃO invente dados, datas, decisões ou nomes.
- Se um campo não tem dados suficientes, escreva o placeholder indicado acima.
- Português do Brasil, tom profissional e direto.
- Total máximo 1500 tokens.
"""


async def generate_briefing(
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    user: User,
    event_id: str,
) -> Briefing:
    """Orquestra coleta de contexto, chamada Haiku e persistência.

    Passos:
    1. Verifica se já existe Briefing para (user_id, event_id) — se sim, retorna o existente
       (idempotência — webhooks podem chegar duplicados).
    2. Coleta contexto via collect_briefing_context.
    3. Renderiza user_content concatenando os dados coletados em Markdown.
    4. Chama generate_briefing_text(SYSTEM_PROMPT, user_content).
    5. Cria Briefing com event_subject/start/end/attendees do contexto + content + telemetria.
    6. db.add(briefing); db.flush(); db.refresh(briefing). NÃO commit (get_db faz).
    7. Retorna o Briefing.

    Raises:
    - HTTPException(404) se o evento não for encontrado na Graph API.
    """
```

**Renderização do user_content** (formato exato):

```
# Reunião

**Assunto:** {event.subject}
**Quando:** {event.start} - {event.end}
**Local:** {event.location or "(não especificado)"}
**Resumo:** {event.body_preview or "(sem resumo)"}

# Participantes

{lista de emails, um por linha precedido de "- "}

# Contexto coletado

## Emails recentes com participantes (últimos {N} dias)

{para cada email: "**[{date}] {subject}**\n{bodyPreview}\n", separado por linhas em branco}
{se vazio: "Nenhum email recente encontrado."}

## Páginas OneNote relacionadas

{para cada página: "- {title}", uma por linha}
{se vazio: "Nenhuma página relacionada."}

## Arquivos OneDrive relacionados

{para cada arquivo: "- {name}", uma por linha}
{se vazio: "Nenhum arquivo relacionado."}

## Memórias relevantes

{para cada memória: "- {content[:200]}", uma por linha}
{se vazio: "Nenhuma memória relevante."}

---

Gere o briefing seguindo as regras do system prompt.
```

---

### 5.8 Webhook handler — modificações em `app/routers/webhooks.py` e `app/services/webhook.py`

**Mudança 1 — `app/services/webhook.py::process_notification`:**

Atualmente retorna `tuple[UUID, ServiceType] | None`. Trocar para `tuple[UUID, ServiceType, str | None] | None` onde o terceiro elemento é o `event_id` extraído do `notification.resource` quando o serviço é CALENDAR.

Lógica de extração:
```python
event_id: str | None = None
if service_type == ServiceType.CALENDAR:
    # notification.resource formato: "Users/{user-guid}/Events/{event-id}"
    parts = notification.resource.split("/Events/")
    if len(parts) == 2:
        event_id = parts[1]
```

Para outros serviços, `event_id = None`. Manter a compatibilidade — não quebrar `_reingest_background` que continua usando apenas `(user_id, service_type)`.

**Mudança 2 — `app/routers/webhooks.py::receive_graph_notification`:**

Após `result = await webhook_service.process_notification(...)`, desempacotar a tupla com 3 elementos. Manter `_reingest_background` como está (ele só usa user_id e service_type). Adicionar:

```python
if event_id is not None and service_type == ServiceType.CALENDAR:
    background_tasks.add_task(_briefing_background, user_id, event_id)
```

**Nova função `_briefing_background`:**

```python
async def _briefing_background(user_id: uuid.UUID, event_id: str) -> None:
    """Background task: gera briefing para um evento de calendar.

    Cria sessão própria. Loga erros sem propagar (webhook já respondeu 202).
    """
    graph_svc = GraphService()
    try:
        async with AsyncSessionLocal() as db:
            redis = get_redis()
            # buscar User pelo id
            user = await db.get(User, user_id)
            if user is None:
                logger.warning("Usuário %s não encontrado para briefing", user_id)
                return
            await generate_briefing(db, redis, graph_svc, user, event_id)
            await db.commit()  # única exceção: BackgroundTask não passa pelo get_db
    except Exception:
        logger.exception(
            "Erro gerando briefing user_id=%s event_id=%s",
            user_id, event_id,
        )
    finally:
        await graph_svc.close()
```

**Atenção:** o `await db.commit()` aqui é necessário porque a sessão é criada manualmente via `AsyncSessionLocal()`, fora do dependency `get_db`. Esse é o **único caso permitido** de commit em código que não é `get_db` — registrar como exceção justificada da regra M1 da Fase 4.5. Padrão idêntico já existe em `_reingest_background` na Fase 3 (mas lá não há mais commit pois `ingest_item` foi limpo na 4.5 — verificar e adicionar commit ao final de `_reingest_background` se a suíte mostrar regressão).

**Verificação obrigatória:** rodar a suíte atual antes de mexer; se algum teste de integração de webhook quebrar por causa da remoção de commit em `ingest_item` na Fase 4.5, **corrigir adicionando `await db.commit()` ao final do `_reingest_background`** — esse é o local correto, não o serviço.

---

### 5.9 Endpoint REST — `app/routers/briefings.py` (NOVO)

```python
"""Router de briefings — exposição REST para consumo pelo painel React (Fase 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.user import User
from app.schemas.briefing import BriefingResponse

router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.get("/{event_id}", response_model=BriefingResponse)
async def get_briefing_by_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BriefingResponse:
    """Retorna o briefing gerado para um evento específico do usuário autenticado.

    404 se não houver briefing para o evento (ainda não foi gerado, ou evento
    inexistente).
    """
    stmt = select(Briefing).where(
        Briefing.user_id == user.id,
        Briefing.event_id == event_id,
    )
    result = await db.execute(stmt)
    briefing = result.scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status_code=404, detail="Briefing não encontrado")

    return BriefingResponse(
        id=briefing.id,
        event_id=briefing.event_id,
        event_subject=briefing.event_subject,
        event_start=briefing.event_start,
        event_end=briefing.event_end,
        attendees=briefing.attendees,
        content=briefing.content,
        generated_at=briefing.generated_at,
        model_used=briefing.model_used,
        input_tokens=briefing.input_tokens,
        cache_read_tokens=briefing.cache_read_tokens,
        cache_write_tokens=briefing.cache_write_tokens,
        output_tokens=briefing.output_tokens,
    )
```

Registrar o router em `app/main.py` (junto aos outros).

---

### 5.10 Tool MCP `get_briefing` — modificações em `app/routers/mcp.py`

Adicionar 9ª ferramenta:

```python
TOOL_GET_BRIEFING = MCPTool(
    name="get_briefing",
    description=(
        "Recupera o briefing automático gerado para um evento de reunião do calendar. "
        "Use antes de uma reunião para obter contexto completo: histórico com participantes, "
        "documentos relevantes, memórias relacionadas e sugestões. "
        "Exemplo: 'me prepare para a reunião de amanhã com a equipe Alpha'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "ID do evento no Outlook (formato Microsoft Graph)",
            },
        },
        "required": ["event_id"],
    },
)


async def handle_get_briefing(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Recupera briefing para um event_id."""
    from sqlalchemy import select
    from app.models.briefing import Briefing

    event_id = arguments["event_id"]
    stmt = select(Briefing).where(
        Briefing.user_id == user.id,
        Briefing.event_id == event_id,
    )
    result = await db.execute(stmt)
    briefing = result.scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status_code=404, detail="Briefing não encontrado")

    return {
        "id": str(briefing.id),
        "event_id": briefing.event_id,
        "event_subject": briefing.event_subject,
        "event_start": briefing.event_start.isoformat(),
        "event_end": briefing.event_end.isoformat(),
        "attendees": briefing.attendees,
        "content": briefing.content,
        "generated_at": briefing.generated_at.isoformat(),
    }
```

Registrar em `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS`. **Total passa de 8 → 9 ferramentas.**

Atualizar `tests/test_edge_cases_mcp.py::test_mcp_list_tools_returns_8_including_semantic_search` para 9 (renomear o teste e o `expected` set).

---

## Critérios de aceitação

A entrega é aceita se TODOS abaixo passarem:

1. ✅ `app/config.py` tem `ANTHROPIC_API_KEY: str` (obrigatório) e `BRIEFING_HISTORY_WINDOW_DAYS: int = 90`.
2. ✅ `app/models/briefing.py` define `Briefing` com todas as colunas/constraints/índices listados em 5.3, e o modelo é exportado em `app/models/__init__.py`.
3. ✅ Migration `004_add_briefings.py` cria a tabela com `server_default` em colunas com default e `UniqueConstraint("user_id", "event_id")`.
4. ✅ `app/services/anthropic_client.py` faz chamada com `cache_control: {"type": "ephemeral"}` no system prompt e captura `cache_read_input_tokens` / `cache_creation_input_tokens` da resposta.
5. ✅ `app/services/briefing_context.py::collect_briefing_context` coleta as 5 fontes (evento, emails, OneNote, OneDrive, memórias) e degrada graciosamente em caso de erro parcial.
6. ✅ `app/services/briefing.py::generate_briefing` é idempotente (retorna existente se já há Briefing para (user_id, event_id)) e usa `flush()` (não commit).
7. ✅ `app/services/webhook.py::process_notification` retorna 3-tupla com `event_id` para CALENDAR, `None` para outros.
8. ✅ `app/routers/webhooks.py` dispara `_briefing_background` apenas para CALENDAR + event_id não-None.
9. ✅ `_briefing_background` cria sessão própria e faz commit ao final (única exceção justificada à regra M1).
10. ✅ `app/routers/briefings.py::get_briefing_by_event` retorna 200 com `BriefingResponse` ou 404.
11. ✅ Tool MCP `get_briefing` registrada — `GET /mcp` retorna 9 ferramentas.
12. ✅ `requirements.txt` tem `anthropic>=0.40.0`.
13. ✅ Suíte completa passa, **sem novas falhas**, com pelo menos os testes abaixo:

### Testes obrigatórios (mínimo 12 novos)

**Unit / edge cases:**

- `test_briefing_context_collects_event` — mocka graph, verifica que evento é buscado com $select correto
- `test_briefing_context_filters_emails_by_attendees` — mocka graph retornando emails variados, verifica que apenas os com from/to nos attendees são mantidos
- `test_briefing_context_handles_partial_failure` — mocka 1 das 5 fontes para falhar, verifica que outras 4 continuam e o briefing é gerado
- `test_briefing_idempotent` — chama `generate_briefing` duas vezes para o mesmo event_id, verifica que só há 1 row em `briefings`
- `test_briefing_uses_flush_not_commit` — verifica que `db.flush` é chamado e `db.commit` não (regra M1)
- `test_anthropic_client_uses_cache_control` — mocka `AsyncAnthropic.messages.create`, captura kwargs, verifica que `system[0].cache_control == {"type": "ephemeral"}`
- `test_anthropic_client_captures_cache_tokens` — mocka response com `cache_read_input_tokens=100`, verifica que `BriefingResult.cache_read_tokens == 100`

**Integração / handlers:**

- `test_webhook_extracts_event_id_for_calendar` — mocka notificação com resource `Users/abc/Events/xyz`, verifica que `process_notification` retorna `event_id="xyz"`
- `test_webhook_returns_none_event_id_for_non_calendar` — para mail/onenote/onedrive, terceiro elemento da tupla é None
- `test_briefings_endpoint_returns_briefing` — cria briefing em DB de teste, GET retorna 200 + BriefingResponse
- `test_briefings_endpoint_404_when_missing` — GET com event_id inexistente retorna 404
- `test_mcp_get_briefing_tool_returns_9_tools` — substitui o teste atual de 8, verifica 9 com `get_briefing` no set
- `test_mcp_get_briefing_404_when_missing` — call_tool com event_id inexistente retorna jsonrpc_domain_error

**Property-based (recomendado, mínimo 1):**

- `test_property_briefing_context_attendee_filter` — Hypothesis: gera lista aleatória de emails como attendees + lista aleatória de from/to em emails, verifica invariante "se um email não tem nenhum attendee em from nem to, é filtrado"

---

## Restrições / O que NÃO entra

- **Sem painel React** — fica para Fase 6.
- **Sem geração proativa em horário** (cron) — só trigger via webhook.
- **Sem regeneração automática** se o evento muda — idempotência por `(user_id, event_id)`. Se o usuário quiser regenerar, terá um endpoint `DELETE /briefings/{event_id}` na Fase 6 (não agora).
- **Sem multi-modelo** — só Haiku 4.5.
- **Sem fallback se a Anthropic API estiver indisponível** — log de erro, briefing não é gerado, próxima notificação tenta de novo (idempotência cobre).
- **Sem rate limiting próprio** para a Anthropic — confiamos nos limits do tier free/paid contratado.
- **Sem internacionalização** — system prompt fixo em pt-BR.
- **Não tocar em** `app/routers/auth.py`, `app/services/cache.py`, `app/services/searxng.py`, `app/models/user.py`/`cache.py`/`webhook.py`/`embedding.py`/`memory.py`, `app/services/memory.py`, `app/services/embeddings.py` (exceto reuso de `semantic_search` e `recall_memory` por import).
- **Não otimizar nada fora do escopo da Fase 5.** Se notar issue, anotar em PR description.

---

## Estratégia de testes

Mocks em todos os testes — **sem chamada real à Anthropic em CI**. Use `unittest.mock.AsyncMock` para `AsyncAnthropic.messages.create` retornando objetos com a estrutura `content[0].text`, `model`, `usage.input_tokens`, `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens`, `usage.output_tokens`.

Usar mocks para `GraphService.fetch_with_params` retornando estruturas dict equivalentes às respostas reais do Microsoft Graph API.

Manter o estilo `@pytest.mark.asyncio` para testes simples e `asyncio.run()` em property tests (consistente com Fases anteriores).

---

## Estrutura sugerida — arquivos novos e modificados

| Arquivo | Tipo | Issue |
|---|---|---|
| `app/config.py` | MOD | 5.1 |
| `app/schemas/briefing.py` | NOVO | 5.2 |
| `app/models/briefing.py` | NOVO | 5.3 |
| `app/models/__init__.py` | MOD | 5.3 |
| `alembic/versions/004_add_briefings.py` | NOVO | 5.4 |
| `app/services/anthropic_client.py` | NOVO | 5.5 |
| `app/services/briefing_context.py` | NOVO | 5.6 |
| `app/services/briefing.py` | NOVO | 5.7 |
| `app/services/webhook.py` | MOD | 5.8 |
| `app/routers/webhooks.py` | MOD | 5.8 |
| `app/routers/briefings.py` | NOVO | 5.9 |
| `app/main.py` | MOD | 5.9 (registrar router) |
| `app/routers/mcp.py` | MOD | 5.10 |
| `tests/test_edge_cases_mcp.py` | MOD | 5.10 (8 → 9 tools) |
| `tests/test_edge_cases_briefing.py` | NOVO | testes 5.11 |
| `tests/test_anthropic_client.py` | NOVO | testes 5.11 |
| `tests/test_property_briefing_attendees.py` | NOVO | property test |
| `tests/test_webhook_service.py` | MOD | testes de extração event_id |
| `requirements.txt` | MOD | 5.5 (anthropic) |

Total: 8 novos + 11 modificados.

---

## Instrução global de documentação

Após implementar cada tarefa, gerar bloco no formato padrão das Fases 4 e 4.5:

```
### Explicação — Tarefa X.Y

**Arquivo(s):** `caminho/dos/arquivos.py`

Para cada trecho relevante:
- Cite o trecho (função, linha ou bloco)
- Explique o que mudou e por quê
- Aponte invariante ou restrição que a mudança garante
- Indique o que quebraria se removida
```

---

## Observação para o KIRO

Esta é a primeira fase com integração externa de LLM (Anthropic). Atenção especial:

1. **Custos** — toda a logística de cache foi pensada para custo < $5/mês. Não introduza chamadas extras ao Claude (ex: para fallback, retry, etc.) sem justificativa explícita.
2. **Determinismo nos testes** — JAMAIS faça testes que chamam a API real. Sempre mock.
3. **Idempotência** — webhooks do Graph chegam duplicados em condições normais. A `UniqueConstraint(user_id, event_id)` + verificação prévia em `generate_briefing` protege.
4. **Background task isolation** — sessão de DB criada localmente em `_briefing_background`. NÃO tente reutilizar a sessão do request original (ela já foi fechada quando o webhook respondeu 202).
5. **Anthropic API key em testes** — Settings exige `ANTHROPIC_API_KEY`. Em `tests/conftest.py` ou via env de teste, definir `ANTHROPIC_API_KEY=test-key-not-used` (verificar se conftest existente já cobre via monkeypatch — provavelmente sim para outros campos obrigatórios).

Comece gerando a spec em `.kiro/specs/lanez-fase5-briefing-automatico/` (design.md, requirements.md, tasks.md) seguindo o mesmo formato das fases anteriores. Ordem sugerida das tarefas:

1. Tarefa 1: Config + Schema Pydantic + requirements.txt (preparação)
2. Tarefa 2: Modelo Briefing + Models Init + Migration 004
3. Tarefa 3: Anthropic client (com testes)
4. Tarefa 4: Service de coleta de contexto (com testes)
5. Tarefa 5: Service orquestrador `generate_briefing` (com testes)
6. Tarefa 6: Modificações em webhook (process_notification + receive_graph_notification + _briefing_background)
7. Tarefa 7: Router REST briefings + registro em main.py
8. Tarefa 8: Tool MCP get_briefing + ajuste de teste de listagem

Apresente a spec para aprovação antes de implementar.
