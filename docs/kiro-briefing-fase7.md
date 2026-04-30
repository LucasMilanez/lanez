# Lanez — Briefing Fase 7 para KIRO

## Contexto crítico para esta fase

A Fase 6b entregou o painel React com voz (commit `3da0bbe`, **180/180 backend + 11/11 frontend**). Branch `main` foi pusheado (`origin/main` em `3da0bbe`). A Fase 7 introduz **audit log**: uma trilha persistente de eventos significativos (auth, MCP tool calls, briefing generation, memory writes, voice transcriptions, webhooks recebidos) e a página `/audit` no painel para o usuário consultar essa trilha.

Como nas fases 6a/6b, este briefing é deliberadamente prescritivo. Risco principal: **escopo de eventos** — o KIRO já tentou em outras fases logar tudo via middleware global (rejeitado na auditoria). Esta fase define um inventário **fechado** de 8 tipos de evento, injetados explicitamente nos pontos relevantes.

---

## O que é o Lanez

MCP Server pessoal que conecta AI assistants ao Microsoft 365. Single-user. Branch `main` em `3da0bbe`, suíte completa **180/180 backend + 11/11 smoke tests frontend**.

---

## O que as Fases 1-6b entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan, CORS, registra: auth, webhooks, graph, mcp,
│                          briefings, voice, memories, status (8 routers)
├── config.py            ← Settings (CORS_ORIGINS, ANTHROPIC_API_KEY, GROQ_API_KEY,
│                          BRIEFING_HISTORY_WINDOW_DAYS, ...) — adicionar
│                          AUDIT_HISTORY_WINDOW_DAYS
├── database.py          ← AsyncSessionLocal, get_db (commit/rollback no boundary),
│                          get_redis, Base
├── dependencies.py      ← get_current_user (cookie HttpOnly OU Bearer)
├── models/
│   ├── user.py
│   ├── cache.py
│   ├── webhook.py       ← WebhookSubscription (resource: String 255)
│   ├── embedding.py     ← Embedding (service: String 20, Vector 384, HNSW)
│   ├── memory.py        ← Memory (Vector 384, HNSW, GIN tags)
│   └── briefing.py      ← Briefing (event_id, content, tokens, generated_at)
├── routers/
│   ├── auth.py          ← /auth/microsoft, /auth/callback (dual), /auth/me,
│   │                      /auth/logout (204), /auth/refresh
│   ├── graph.py
│   ├── webhooks.py      ← POST /webhooks/notifications (Microsoft Graph)
│   ├── mcp.py           ← 9 ferramentas, dispatch via TOOLS_REGISTRY
│   ├── briefings.py     ← GET /briefings (paginado), GET /briefings/{event_id}
│   ├── voice.py         ← POST /voice/transcribe (multipart, 30s/5MB)
│   ├── memories.py      ← POST /memories (REST, reaproveita save_memory)
│   └── status.py        ← GET /status
├── schemas/
│   ├── auth.py          ← UserMeResponse, TokenResponse
│   ├── briefing.py
│   ├── memory.py        ← MemoryCreateRequest com field_validator anti-whitespace
│   └── status.py
└── services/
    ├── anthropic_client.py
    ├── briefing.py / briefing_context.py
    ├── embeddings.py
    ├── graph.py
    ├── memory.py        ← save_memory standalone (retorna dict), recall_memory
    ├── webhook.py       ← create_subscriptions, renew_subscriptions,
    │                      process_notification (chamado pelo router de webhooks)
    ├── groq_voice.py
    ├── cache.py
    └── searxng.py

frontend/
├── src/
│   ├── App.tsx          ← ThemeProvider > QueryClientProvider > BrowserRouter
│   │                      > AuthProvider > Routes
│   ├── auth/            ← AuthContext, ProtectedRoute
│   ├── theme/           ← ThemeContext (com resolvedTheme), ThemeToggle
│   ├── lib/             ← api.ts (request, requestMultipart com credentials
│   │                      'include'; ApiError), queryClient.ts, utils.ts,
│   │                      stripMarkdown.ts
│   ├── hooks/           ← useStatus, useBriefings, useBriefing, useVoiceRecorder,
│   │                      useTranscribe, useCreateMemory, useSpeechSynthesis
│   ├── components/      ← AppShell (sidebar 240px + TopBar inline com MicButton e
│   │                      ThemeToggle), StatusCard, TokenUsageChart, BriefingCard,
│   │                      BriefingMarkdown, BriefingTTSButton, EmptyState,
│   │                      ErrorState, LoadingSkeleton, voice/* + ui/*
│   └── pages/           ← LoginPage, DashboardPage, BriefingsListPage,
│                          BriefingDetailPage, SettingsPage
```

**Reutilizar das fases anteriores:**

- `get_current_user` em `app/dependencies.py` — auth dual cookie/Bearer
- `get_db` em `app/database.py` — commit/rollback no boundary do request
- `AsyncSessionLocal` para contextos fora do request (ex: webhooks → background; loop de renovação de webhooks → ver `app/main.py:renewal_loop`)
- `BriefingsListPage` em `frontend/src/pages/` — padrão de tabela paginada com filtro debounced (modelo para `AuditPage`)
- `Dialog` shadcn em `frontend/src/components/ui/dialog.tsx` — adicionado na 6b, agora reusado para `AuditDetailDialog`
- `AppShell` em `frontend/src/components/AppShell.tsx` — vai receber novo item "Auditoria" no `navItems`
- `api` client em `frontend/src/lib/api.ts` — sem alterações nesta fase

---

## Fase 7 — `/audit`

### Objetivo

1. **Backend de audit log** — nova tabela `audit_log`, helper `app.services.audit.log_event`, e 8 pontos de injeção que registram eventos significativos do sistema. Eventos são **persistidos** (não só logger), com `event_data` JSONB contendo metadados específicos por tipo.

2. **Endpoint `GET /audit`** — paginado, com filtros por `event_type`, `since`, `until`, `q` (busca em `event_data` via SQL JSONB cast).

3. **Página `/audit` no painel** — tabela com filtros, badges coloridas por tipo de evento, e dialog de detalhe que mostra `event_data` completo formatado em JSON.

### Inventário fechado de 8 tipos de evento

A definição é **fechada** — não inventar tipos novos. Cada tipo tem um schema de `event_data` definido. Se uma operação não cabe num desses 8 tipos, **não logar** (registrar gap no checkpoint final para discussão pós-fase).

| `event_type`              | Onde injetar                                                            | `event_data` (campos obrigatórios)                                          |
| ------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `auth.login`              | `app/routers/auth.py` `auth_callback`, após `db.commit()` do User       | `{ "method": "oauth_callback", "had_return_url": bool, "email": str }`      |
| `auth.logout`             | `app/routers/auth.py` `auth_logout`                                     | `{}` (sem campos — o `user_id` já identifica)                               |
| `auth.refresh`            | `app/routers/auth.py` `auth_refresh`, após `db.commit()` dos novos tokens | `{ "expires_in_seconds": int }`                                            |
| `mcp.call`                | `app/routers/mcp.py` `call_tool`, após `jsonrpc_success` ou `jsonrpc_domain_error` | `{ "tool_name": str, "arguments_summary": dict, "success": bool, "error_message": str \| null }` |
| `briefing.generated`      | `app/services/briefing.py` (ou onde o `_briefing_background` da Fase 5 grava o Briefing), após `db.commit()` do Briefing | `{ "event_id": str, "model_used": str, "input_tokens": int, "output_tokens": int, "cache_read_tokens": int, "cache_write_tokens": int }` |
| `memory.created`          | `app/services/memory.py` `save_memory`, antes do return       | `{ "tags": list[str], "content_length": int, "source": "rest" \| "mcp" }` |
| `voice.transcribed`       | `app/routers/voice.py` `transcribe`, após sucesso da Groq               | `{ "audio_bytes": int, "transcription_length": int, "duration_ms": int }`   |
| `webhook.received`        | `app/services/webhook.py` `process_notification`, ao começar o processamento de cada notificação | `{ "resource": str, "change_type": str, "subscription_id": str }`           |

**Notas críticas sobre o inventário:**

- **`auth.login`/`auth.refresh`/`memory.created`/`voice.transcribed`/`mcp.call`** — sempre registrados após o ponto de não-retorno do path feliz, mas **incluem falhas de domínio**. Para `mcp.call` especificamente, registrar **independentemente** do `success`: tanto `jsonrpc_success` quanto `jsonrpc_domain_error` produzem registro (com `success=true`/`false` no `event_data`).
- **`auth.logout`** — endpoint é stateless (só apaga cookie). Para registrar precisa de `user` autenticado; já que o endpoint atual **não exige auth** (qualquer um pode bater), o briefing **adiciona dependência** (ver §7.B.4).
- **`briefing.generated`** — o serviço da Fase 5 roda em background task com `AsyncSessionLocal()` próprio. O log_event vai usar a **mesma sessão** dessa task (ver §7.B.3 — passa `db` para o helper).
- **`memory.created`** — campo `source` distingue "rest" (POST /memories vindo do painel) de "mcp" (save_memory tool). A função `save_memory` em `app/services/memory.py` precisa receber esse parâmetro novo.
- **`webhook.received`** — uma única notificação Microsoft Graph pode trazer múltiplos `value[]`. Logar **um evento por entrada do array**, não um por request HTTP.
- **`mcp.call.arguments_summary`** — não logar argumentos brutos (PII em queries de email, conteúdo de memória, etc.). Logar apenas chaves presentes + tamanhos. Ver §7.B.5.

### O que NÃO entra na Fase 7

- **Sem retention/cleanup automático** — eventos crescem indefinidamente nesta fase. Fica para Fase 7b (ou job manual).
- **Sem export CSV/JSON** — só consulta via UI.
- **Sem real-time updates** — refetch manual ou navegação re-monta a página. Sem WebSocket/SSE.
- **Sem audit de leituras** (GET /briefings, /status, /auth/me) — só ações que alteram estado ou consomem recurso externo (LLM, mic, Graph).
- **Sem audit de erros de rede** (`httpx.HTTPError` da Groq, do Graph) que não cheguem ao endpoint — só o que tem entry-point HTTP é logado.
- **Sem PII em `event_data`** — proibido logar `query` de email, `content` de memória, `transcription` de voz, conteúdo de briefing.
- **Sem versionamento de schema do `event_data`** — formato é mutável; queries do frontend devem ser tolerantes a campos faltantes em registros antigos.
- **Sem campo de IP/User-Agent** — single-user, não precisa.
- **Sem agregação no endpoint** (counts por tipo, etc.) — só listagem paginada.

### Decisões técnicas (já aprovadas pelo usuário)

| Decisão                              | Escolha                                                                                          | Justificativa                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Estratégia de injeção                | Helper `audit.log_event(db, ...)` chamado explicitamente nos 8 pontos                            | Middleware global ruidoso (auth/me a cada 5s); injeção pontual é cirúrgica |
| Tipo da coluna `event_data`          | `JSONB` (PostgreSQL nativo)                                                                      | Filtragem por chave via `->>` no `q`; sem migrar a cada novo evento    |
| Tipo da coluna `event_type`          | `String(64)` com enum-like Python (`AuditEventType`) para segurança                              | Postgres ENUM exige migration a cada novo tipo; `String` + enum no app é mais flexível |
| Persistência de erros                | `mcp.call` registra falhas (`success=false`); demais eventos só registram path feliz             | Auditoria é "o que foi executado"; falhas de auth → 401 não chegam ao endpoint |
| Commit do log                        | `audit.log_event` faz `flush`, **não commit** — segue regra M1 da Fase 4.5; `get_db` faz commit no boundary | Consistência com regra existente; log e operação ficam na mesma transação atômica |
| Sessão para `briefing.generated`     | Helper aceita o `db` da background task (`AsyncSessionLocal()` chamado em `_briefing_background`) | Mesma sessão, mesmo commit                                            |
| Sessão para `webhook.received`       | Mesma sessão do `process_notification`                                                            | Ver acima                                                             |
| Tipo de telemetria de tokens em briefing.generated | `int` (mesmo que Briefing.input_tokens etc.)                                                | Espelhar tabela `briefings`                                           |
| Filtros do GET /audit                | `event_type` (lista, OR), `since`/`until` (datetime), `q` (ILIKE em event_type + busca JSON cast) | Suficiente; busca semântica é overkill                               |
| Paginação do GET /audit              | Mesmo padrão de /briefings (`page`/`page_size`/total) com `count_stmt` separado                  | Consistência                                                          |
| Janela default na UI                 | 30 dias (settings.AUDIT_HISTORY_WINDOW_DAYS = 30)                                                 | Backlog grande pode ser custoso na primeira visualização              |
| Ordenação                            | `created_at DESC` sempre                                                                          | Audit é cronológico                                                   |
| Status do endpoint                   | Auth-required (cookie OU Bearer), 401 se não autenticado                                          | Padrão do projeto                                                     |

---

## Pré-flight obrigatório

Antes de gerar a spec, executar:

```bash
# 1) Confirmar que migration 004 é a mais recente e que 005 vai criar audit_log
ls alembic/versions/

# 2) Confirmar a assinatura atual de save_memory (vai receber novo kwarg `source`)
grep -n "async def save_memory" app/services/memory.py
grep -n "save_memory(" app/routers/mcp.py app/routers/memories.py

# 3) Confirmar a estrutura de _briefing_background (sessão própria via AsyncSessionLocal)
grep -n "_briefing_background\|AsyncSessionLocal" app/services/briefing.py app/routers/webhooks.py

# 4) Confirmar a estrutura de process_notification (loop de value[]?)
grep -n "process_notification\|def process" app/services/webhook.py | head -10

# 5) Confirmar schema de WebhookNotification (campos resource, changeType, subscriptionId)
grep -n "subscription\|changeType\|resource" app/services/webhook.py | head -20

# 6) Confirmar que /auth/logout NÃO requer auth atualmente
grep -n "@router.post.*logout\|def auth_logout" app/routers/auth.py

# 7) Verificar quais nomes de tools MCP existem hoje (cobre o inventário do mcp.call)
grep -n "TOOLS_REGISTRY\b\|TOOLS_MAP\b" app/routers/mcp.py
```

Reportar no bloco "Explicação — Tarefa 1" os achados:

- Lista de migrations atuais (esperado: `001_initial_tables`, `002_add_embeddings`, `003_add_memories`, `004_add_briefings`)
- Assinatura real de `save_memory` (esperado: `async def save_memory(db, user_id, content, tags=None) -> dict`)
- **Onde** o Briefing é commitado em `_briefing_background` (esperado: dentro da função de background, após `db.commit()` da nova Briefing)
- Estrutura de `process_notification` — confirmar se itera `value[]` da notificação ou processa um item por chamada
- Confirmação de que `/auth/logout` é stateless (sem `Depends(get_current_user)` hoje) — vai mudar nesta fase
- Lista das 9 tools MCP no `TOOLS_REGISTRY` (esperado: `get_calendar_events`, `search_emails`, `get_onenote_pages`, `search_files`, `web_search`, `semantic_search`, `save_memory`, `recall_memory`, `get_briefing`)

Se algum destes pontos divergir, **ajustar o código gerado para o que realmente existe**, não inventar. Documentar as divergências.

---

## Parte B — Backend (8 mudanças)

### 7.B.1 — Modelo + migration

**Modelo (`app/models/audit.py` NOVO):**

```python
"""Modelo AuditLog — registro persistente de eventos significativos. Fase 7."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """Evento auditado — auth, MCP call, briefing, memory, voice, webhook.

    `event_type` é um discriminador String (não enum Postgres) — o app
    valida via `AuditEventType` em audit.py. `event_data` é JSONB livre
    com schema definido pelo tipo (sem versionamento — queries devem ser
    tolerantes a campos ausentes).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_audit_log_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_audit_log_user_type_created",
            "user_id",
            "event_type",
            "created_at",
        ),
    )
```

**Migration (`alembic/versions/005_add_audit_log.py` NOVO):**

```python
"""Add audit_log table for Fase 7

Revision ID: 005_audit_log
Revises: 004_briefings
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "005_audit_log"
down_revision: Union[str, None] = "004_briefings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "event_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_log_user_created",
        "audit_log",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_log_user_type_created",
        "audit_log",
        ["user_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_type_created", table_name="audit_log")
    op.drop_index("ix_audit_log_user_created", table_name="audit_log")
    op.drop_table("audit_log")
```

**Atenção:** `id` com `server_default=gen_random_uuid()` (regra M2 da Fase 4.5). Espelha o padrão das migrations 001-004. **Não** indexar `event_data` JSONB nesta fase — query plan pode ser revisitado depois.

**Adicionar `app/models/audit.py` ao `__init__.py`** dos models para o `Base.metadata.create_all` no lifespan pegar a nova tabela.

### 7.B.2 — Service helper `app/services/audit.py` (NOVO)

```python
"""Service helper para registrar eventos no audit log. Fase 7.

Helper único `log_event` que cria a entrada AuditLog e faz `flush` na
sessão recebida — segue regra M1 da Fase 4.5 (services não fazem commit).
O commit fica a cargo de quem dirige a sessão (get_db no caso de request,
ou o caller direto no caso de background tasks como `_briefing_background`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditEventType(StrEnum):
    """Inventário fechado de tipos de evento. Não estender sem revisão de spec."""

    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_REFRESH = "auth.refresh"
    MCP_CALL = "mcp.call"
    BRIEFING_GENERATED = "briefing.generated"
    MEMORY_CREATED = "memory.created"
    VOICE_TRANSCRIBED = "voice.transcribed"
    WEBHOOK_RECEIVED = "webhook.received"


_MAX_ERROR_LENGTH = 500


async def log_event(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: AuditEventType,
    event_data: dict[str, Any] | None = None,
    success: bool = True,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Registra um evento no audit log. NÃO faz commit — o caller é responsável.

    Trunca `error_message` a 500 chars para encaixar na coluna. Falhas em
    `flush` são logadas mas NÃO levantadas — auditoria não pode quebrar a
    operação principal.
    """
    if error_message and len(error_message) > _MAX_ERROR_LENGTH:
        error_message = error_message[: _MAX_ERROR_LENGTH - 3] + "..."

    entry = AuditLog(
        user_id=user_id,
        event_type=str(event_type),
        event_data=event_data or {},
        success=success,
        error_message=error_message,
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)

    try:
        await db.flush()
    except Exception:
        # Audit não pode derrubar request — log e segue
        logger.exception(
            "Falha ao registrar evento de auditoria event_type=%s user_id=%s",
            event_type,
            user_id,
        )
```

**Decisões:**

- **`StrEnum`** (Python 3.11+) — comparações com `==` retornam `True` contra strings literais e o `str(event_type)` retorna o valor sem prefixo de classe.
- **`flush` sem commit** — consistente com a regra M1; `get_db` faz commit no fim do request.
- **Try/except no flush** — se a sessão estiver inválida (rollback prévio, etc.), audit não levanta. **Mas atenção:** se a sessão já estiver corrompida, o flush vai falhar e o `db.add()` continua marcado. Isso só acontece em paths excepcionais; aceitável.
- **`error_message` truncado** — coluna é `String(500)`; trace de exception pode ser maior.

### 7.B.3 — Hook em briefing generation (`app/services/briefing.py`)

Localizar a função que faz o commit da Briefing (provavelmente em `_briefing_background` ou similar — confirmar no pré-flight). Adicionar `log_event` **após** o `db.commit()` da Briefing.

```python
# DENTRO da função de background que cria a Briefing — após db.commit() da Briefing:
from app.services.audit import AuditEventType, log_event

await log_event(
    db,
    user_id=user_id,
    event_type=AuditEventType.BRIEFING_GENERATED,
    event_data={
        "event_id": briefing.event_id,
        "model_used": briefing.model_used,
        "input_tokens": briefing.input_tokens,
        "output_tokens": briefing.output_tokens,
        "cache_read_tokens": briefing.cache_read_tokens,
        "cache_write_tokens": briefing.cache_write_tokens,
    },
    success=True,
)
await db.commit()  # commit do log
```

**Atenção:** background task usa `AsyncSessionLocal()` própria, não passa por `get_db`. Logo, `log_event` faz flush, mas o **commit é manual** depois (a função background já faz isso para a Briefing — agora também precisa cobrir o audit).

Se a função background **falha** ao gerar briefing (ex: Anthropic 429), **não logar** — `briefing.generated` é evento de sucesso. Falhas de Anthropic não cabem em nenhum dos 8 tipos.

### 7.B.4 — Hooks em auth (`app/routers/auth.py`)

**`auth_callback`** — após `db.commit()` do User (linhas ~261-262 do código atual), antes do `_create_jwt`:

```python
from app.services.audit import AuditEventType, log_event

await log_event(
    db,
    user_id=user.id,
    event_type=AuditEventType.AUTH_LOGIN,
    event_data={
        "method": "oauth_callback",
        "had_return_url": bool(state_data.get("return_url")),
        "email": email,
    },
    success=True,
)
```

(O commit do `get_db` no fim do request cobre o flush.)

**`auth_logout`** — endpoint atual é stateless. **Mudar para auth-required** + injetar `db`:

```python
@router.post("/logout", status_code=204)
async def auth_logout(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Limpa o cookie de sessão. Idempotente — sempre retorna 204."""
    await log_event(
        db,
        user_id=current_user.id,
        event_type=AuditEventType.AUTH_LOGOUT,
        event_data={},
        success=True,
    )
    response = Response(status_code=204)
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return response
```

**Justificativa para mudar `/auth/logout` para auth-required:** sem `user_id`, audit é inútil. **Quebra teste existente** `test_auth_logout_204` (Fase 6a) que bate sem cookie e espera 204. **Atualizar o teste** para enviar cookie/Bearer; outro teste novo verifica 401 sem auth.

**`auth_refresh`** — após `db.commit()` dos novos tokens:

```python
await log_event(
    db,
    user_id=current_user.id,
    event_type=AuditEventType.AUTH_REFRESH,
    event_data={"expires_in_seconds": expires_in},
    success=True,
)
```

### 7.B.5 — Hook em MCP (`app/routers/mcp.py`)

Modificar `call_tool` para medir latência e logar **independentemente** do success/error (incluindo erros de domínio que retornam `jsonrpc_domain_error`). Erros **antes** do despacho (método inválido, tool inexistente, parâmetro obrigatório ausente) **não logam** — esses são erros de protocolo, não de execução.

```python
import time
from app.services.audit import AuditEventType, log_event


def _summarize_arguments(arguments: dict) -> dict:
    """Resumo seguro de argumentos — chaves + tamanhos, sem PII.

    Não loga conteúdo de query, content de memória, etc.
    """
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            summary[key] = {"type": "string", "length": len(value)}
        elif isinstance(value, list):
            summary[key] = {"type": "array", "length": len(value)}
        elif isinstance(value, (int, float, bool)):
            summary[key] = {"type": type(value).__name__, "value": value}
        elif value is None:
            summary[key] = {"type": "null"}
        else:
            summary[key] = {"type": type(value).__name__}
    return summary


# ... dentro de call_tool, APÓS as validações de protocolo ...
started_at = time.monotonic()
success = True
error_msg: str | None = None

try:
    handler = TOOLS_REGISTRY[tool_name]
    data = await handler(arguments, user, db, redis, graph, searxng)
    response = jsonrpc_success(request.id, data)
except HTTPException as exc:
    success = False
    error_msg = str(exc.detail)
    response = jsonrpc_domain_error(request.id, str(exc.detail))
except Exception as exc:
    success = False
    error_msg = f"Erro interno: {exc}"
    logger.exception("Erro interno na ferramenta %s", tool_name)
    response = jsonrpc_domain_error(request.id, error_msg)

elapsed_ms = int((time.monotonic() - started_at) * 1000)

await log_event(
    db,
    user_id=user.id,
    event_type=AuditEventType.MCP_CALL,
    event_data={
        "tool_name": tool_name,
        "arguments_summary": _summarize_arguments(arguments),
        "success": success,
        "error_message": error_msg,
    },
    success=success,
    error_message=error_msg,
    latency_ms=elapsed_ms,
)

return response
```

**Atenção:**

- **`arguments_summary`** redunda com `success` e `error_message` no JSONB para facilitar consultas SQL via JSONB sem precisar `JOIN` com colunas estruturadas. Custo de redundância mínimo, valor de UI grande.
- **PII**: nenhuma string crua dos argumentos vai pro log. Se o usuário precisar do conteúdo bruto para debug, logger normal já cobre via `logger.exception`.
- O log é registrado **antes** de retornar a response — se falhar, o request inteiro falha (mas o try/except dentro de `log_event` evita isso).

### 7.B.6 — Hook em memory (`app/services/memory.py`)

Modificar `save_memory` para aceitar `source: str = "rest"` (default) e logar evento. **MCP handler** (`app/routers/mcp.py:handle_save_memory`) passa `source="mcp"`. **REST router** (`app/routers/memories.py`) passa `source="rest"`.

```python
# app/services/memory.py — nova assinatura:
async def save_memory(
    db: AsyncSession,
    user_id: UUID,
    content: str,
    tags: list[str] | None = None,
    source: str = "rest",  # NOVO — "rest" | "mcp"
) -> dict:
    # ... lógica existente que cria a Memory ...
    # Antes do return final, após flush/refresh do Memory:
    from app.services.audit import AuditEventType, log_event
    await log_event(
        db,
        user_id=user_id,
        event_type=AuditEventType.MEMORY_CREATED,
        event_data={
            "tags": tags or [],
            "content_length": len(content),
            "source": source,
        },
        success=True,
    )
    return {...}  # mesmo dict de antes
```

**Em `app/routers/mcp.py:handle_save_memory`:**

```python
return await save_memory(db, user.id, content, tags, source="mcp")
```

**Em `app/routers/memories.py:create_memory`:**

```python
result = await save_memory(
    db=db,
    user_id=user.id,
    content=body.content,
    tags=body.tags,
    source="rest",  # NOVO
)
```

### 7.B.7 — Hook em voice (`app/routers/voice.py`)

Após o `logger.info` final de telemetria em `transcribe`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.audit import AuditEventType, log_event

# Adicionar dependency `db: AsyncSession = Depends(get_db)` na assinatura.
# Após `text = await transcribe_audio(...)`:

await log_event(
    db,
    user_id=user.id,
    event_type=AuditEventType.VOICE_TRANSCRIBED,
    event_data={
        "audio_bytes": len(audio_bytes),
        "transcription_length": len(text),
        "duration_ms": elapsed_ms,
    },
    success=True,
    latency_ms=elapsed_ms,
)
```

**Atenção:** se a Groq falha (`GroqTranscriptionError` → 502), **não logar** — `voice.transcribed` é evento de sucesso. Falhas ficam só no logger normal.

### 7.B.8 — Hook em webhooks (`app/services/webhook.py`)

`process_notification` é chamado pelo router `webhooks.py`. Confirmar no pré-flight como o loop sobre `value[]` funciona. Para cada item processado:

```python
from app.services.audit import AuditEventType, log_event

# Para CADA notificação dentro do value[]:
await log_event(
    db,
    user_id=subscription.user_id,
    event_type=AuditEventType.WEBHOOK_RECEIVED,
    event_data={
        "resource": notification.resource,
        "change_type": notification.change_type,
        "subscription_id": str(notification.subscription_id),
    },
    success=True,
)
```

**Atenção:** o webhook router roda fora do contexto autenticado por usuário (Microsoft Graph não envia JWT). O `user_id` vem da `WebhookSubscription` recuperada por `subscription_id`. Se a subscrição não existir, **não logar** — log órfão sem user_id violaria FK.

### 7.B.9 — Endpoint `GET /audit` (`app/routers/audit.py` NOVO)

```python
"""Router REST para consulta de audit log. Fase 7."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import (
    AuditLogItem,
    AuditLogListResponse,
)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_log(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event_type: Annotated[list[str] | None, Query()] = None,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(default=None, description="Busca em event_type OU event_data"),
) -> AuditLogListResponse:
    """Lista eventos de auditoria do usuário, paginados, filtrados, ordenados desc."""
    filters = [AuditLog.user_id == user.id]
    if event_type:
        filters.append(AuditLog.event_type.in_(event_type))
    if since:
        filters.append(AuditLog.created_at >= since)
    if until:
        filters.append(AuditLog.created_at <= until)
    if q:
        # Busca em event_type OU em event_data como texto JSON
        filters.append(
            (AuditLog.event_type.ilike(f"%{q}%"))
            | (func.cast(AuditLog.event_data, String).ilike(f"%{q}%"))
        )

    count_stmt = select(func.count()).select_from(AuditLog).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    paged_stmt = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(paged_stmt)).scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(i, from_attributes=True) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

**Schema (`app/schemas/audit.py` NOVO):**

```python
"""Schemas Pydantic para audit log REST. Fase 7."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    event_data: dict[str, Any]
    success: bool
    error_message: str | None
    latency_ms: int | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
```

**Registrar em `app/main.py`:** `app.include_router(audit.router)`.

**Importar `String` no router:**

```python
from sqlalchemy import func, select, String  # String para o cast no filtro q
```

### 7.B.10 — Settings nova em `app/config.py`

```python
AUDIT_HISTORY_WINDOW_DAYS: int = 30
```

Exposta via `GET /status` no `StatusConfig` (consistente com `briefing_history_window_days` da Fase 6a).

**Modificar `app/schemas/status.py:StatusConfig`:**

```python
class StatusConfig(BaseModel):
    briefing_history_window_days: int
    audit_history_window_days: int  # NOVO Fase 7
```

**Modificar `app/routers/status.py`** para passar o novo campo:

```python
config=StatusConfig(
    briefing_history_window_days=settings.BRIEFING_HISTORY_WINDOW_DAYS,
    audit_history_window_days=settings.AUDIT_HISTORY_WINDOW_DAYS,  # NOVO
),
```

### 7.B.11 — Testes do backend (mínimo 18 novos)

**Para `app/services/audit.py`:**

- `test_log_event_creates_audit_log_entry` — chama `log_event`, verifica row criada com campos corretos (event_type, event_data, success, latency_ms)
- `test_log_event_truncates_long_error_message` — error_message com 600 chars → row tem 500 chars com sufixo "..."
- `test_log_event_does_not_raise_on_flush_failure` — mock `db.flush` levantando → função não levanta (apenas loga)

**Para `GET /audit`:**

- `test_audit_list_returns_paginated_items` — seed 5 events, GET /audit?page=1&page_size=2 → 2 items + total=5
- `test_audit_list_filters_by_event_type` — seed 3 mcp.call + 2 auth.login, filtro `event_type=mcp.call` → só 3
- `test_audit_list_filters_by_event_type_multiple` — seed 3 mcp.call + 2 auth.login + 1 voice → filtro `event_type=mcp.call&event_type=voice.transcribed` → 4 items
- `test_audit_list_filters_by_since_until` — eventos em 3 dias diferentes, filtro since/until → range correto
- `test_audit_list_q_searches_event_data` — seed event com `arguments_summary.tool_name=search_emails`, q="search_emails" → 1 hit
- `test_audit_list_orders_desc_by_created_at` — seed 3 events em ordens diferentes → resposta vem desc
- `test_audit_list_requires_auth` — sem cookie/Bearer → 401
- `test_audit_list_isolates_per_user` — user A tem event, user B autenticado → user B vê 0 items

**Para os hooks (smoke):**

- `test_audit_logged_on_mcp_call_success` — POST /mcp/call com tool válido → row `mcp.call` com `success=true`
- `test_audit_logged_on_mcp_call_failure` — mock handler levantando `HTTPException` → row `mcp.call` com `success=false` e error_message truncado
- `test_audit_logged_on_memory_create_rest` — POST /memories → row `memory.created` com `event_data.source="rest"`
- `test_audit_logged_on_memory_create_mcp` — POST /mcp/call save_memory → row `memory.created` com `event_data.source="mcp"`
- `test_audit_logged_on_voice_transcribe_success` — POST /voice/transcribe (mock Groq) → row `voice.transcribed` com `audio_bytes` e `duration_ms`
- `test_audit_logged_on_auth_logout` — POST /auth/logout autenticado → row `auth.logout`; cobre também a quebra do test legado
- `test_auth_logout_now_requires_auth` — POST /auth/logout sem auth → 401 (regressão da mudança em §7.B.4)

Os testes devem usar `app.dependency_overrides` para `get_current_user` e `get_db`, conforme padrão das Fases 5-6b.

**Atenção ao teste legado da Fase 6a:** `test_auth_logout_204` (ou nome equivalente) precisa ser **atualizado** para enviar cookie de auth — caso contrário, falha após mudança em §7.B.4.

---

## Parte F — Frontend (4 mudanças)

### 7.F.1 — Estrutura de diretórios (incremental)

```
frontend/src/
├── components/
│   ├── (existentes ...)
│   ├── AuditEventBadge.tsx              ← NOVO — badge colorida por event_type
│   └── AuditDetailDialog.tsx            ← NOVO — modal mostrando event_data
├── hooks/
│   ├── (existentes ...)
│   └── useAuditLog.ts                   ← NOVO — TanStack query paginada
├── pages/
│   ├── (existentes ...)
│   └── AuditPage.tsx                    ← NOVO — tabela + filtros
└── __tests__/
    ├── (existentes ...)
    ├── AuditPage.test.tsx               ← NOVO
    └── AuditEventBadge.test.tsx         ← NOVO
```

**Modificar:**

- `frontend/src/App.tsx` — adicionar rota `/audit` dentro do AppShell
- `frontend/src/components/AppShell.tsx` — adicionar item "Auditoria" ao `navItems` com `History` (lucide-react)
- `frontend/vite.config.ts` — adicionar `/audit` ao proxy

### 7.F.2 — Hook `useAuditLog.ts`

```ts
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AuditLogItem {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  success: boolean;
  error_message: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFilters {
  page: number;
  pageSize: number;
  eventTypes?: string[];
  since?: string;
  until?: string;
  q?: string;
}

export function useAuditLog(filters: AuditFilters) {
  const params = new URLSearchParams();
  params.set("page", String(filters.page));
  params.set("page_size", String(filters.pageSize));
  filters.eventTypes?.forEach((t) => params.append("event_type", t));
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.q) params.set("q", filters.q);

  return useQuery<AuditLogListResponse>({
    queryKey: ["audit", filters],
    queryFn: () => api.get<AuditLogListResponse>(`/audit?${params.toString()}`),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
```

### 7.F.3 — Componentes

**`AuditEventBadge.tsx`** — paleta fixa por tipo (mesmo padrão da paleta de TokenUsageChart da 6a):

```tsx
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_STYLES: Record<string, string> = {
  "auth.login": "bg-green-500/15 text-green-700 dark:text-green-400",
  "auth.logout": "bg-slate-500/15 text-slate-700 dark:text-slate-400",
  "auth.refresh": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  "mcp.call": "bg-purple-500/15 text-purple-700 dark:text-purple-400",
  "briefing.generated": "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  "memory.created": "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  "voice.transcribed": "bg-pink-500/15 text-pink-700 dark:text-pink-400",
  "webhook.received": "bg-indigo-500/15 text-indigo-700 dark:text-indigo-400",
};

const FALLBACK_STYLE = "bg-muted text-muted-foreground";

interface AuditEventBadgeProps {
  eventType: string;
  className?: string;
}

export function AuditEventBadge({ eventType, className }: AuditEventBadgeProps) {
  const style = TYPE_STYLES[eventType] ?? FALLBACK_STYLE;
  return (
    <Badge variant="secondary" className={cn(style, "font-mono text-xs", className)}>
      {eventType}
    </Badge>
  );
}
```

**Decisão crítica:** cores via Tailwind utility classes literais (não via tokens shadcn) — exceção justificada pela mesma razão da `bg-red-500` do `RecordingIndicator` na Fase 6b: o usuário precisa diferenciar tipos visualmente, e tokens shadcn (primary/accent/destructive) só dão 3-4 cores distintas. Documentar como única exceção da fase.

**`AuditDetailDialog.tsx`:**

```tsx
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AuditEventBadge } from "@/components/AuditEventBadge";
import type { AuditLogItem } from "@/hooks/useAuditLog";

interface AuditDetailDialogProps {
  item: AuditLogItem | null;
  onOpenChange: (open: boolean) => void;
}

export function AuditDetailDialog({ item, onOpenChange }: AuditDetailDialogProps) {
  return (
    <Dialog open={item !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        {item && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <AuditEventBadge eventType={item.event_type} />
                {!item.success && (
                  <span className="text-sm text-destructive">falhou</span>
                )}
              </div>
              <DialogTitle className="font-mono text-sm pt-2">
                {new Date(item.created_at).toLocaleString("pt-BR")}
              </DialogTitle>
              <DialogDescription>
                {item.latency_ms !== null && `${item.latency_ms} ms`}
              </DialogDescription>
            </DialogHeader>

            {item.error_message && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
                <p className="text-sm font-medium text-destructive">Erro</p>
                <p className="text-sm font-mono mt-1">{item.error_message}</p>
              </div>
            )}

            <div>
              <p className="text-sm font-medium mb-2">Detalhes</p>
              <pre className="rounded-md bg-muted p-3 text-xs font-mono overflow-auto max-h-96">
                {JSON.stringify(item.event_data, null, 2)}
              </pre>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

### 7.F.4 — Página `AuditPage.tsx`

Modelo: `BriefingsListPage.tsx` (debounce 300ms, paginação Anterior/Próximo, EmptyState/LoadingSkeleton/ErrorState).

```tsx
import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AuditEventBadge } from "@/components/AuditEventBadge";
import { AuditDetailDialog } from "@/components/AuditDetailDialog";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useAuditLog, type AuditLogItem } from "@/hooks/useAuditLog";

const EVENT_TYPES = [
  "auth.login",
  "auth.logout",
  "auth.refresh",
  "mcp.call",
  "briefing.generated",
  "memory.created",
  "voice.transcribed",
  "webhook.received",
];

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selected, setSelected] = useState<AuditLogItem | null>(null);
  const [activeTypes, setActiveTypes] = useState<string[]>([]);
  const pageSize = 50;

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading, error, refetch } = useAuditLog({
    page,
    pageSize,
    eventTypes: activeTypes.length > 0 ? activeTypes : undefined,
    q: debouncedSearch || undefined,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  const toggleType = (type: string) => {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Auditoria</h1>

      <div className="space-y-3">
        <Input
          placeholder="Buscar (event_type ou event_data)..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          {EVENT_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => toggleType(t)}
              className="cursor-pointer"
              type="button"
            >
              <AuditEventBadge
                eventType={t}
                className={activeTypes.includes(t) ? "ring-2 ring-foreground/40" : "opacity-60"}
              />
            </button>
          ))}
        </div>
      </div>

      {isLoading && <LoadingSkeleton count={5} className="h-12" />}

      {error && <ErrorState onRetry={() => void refetch()} />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="Nenhum evento encontrado"
          description="Ajuste filtros ou aguarde — eventos aparecem conforme você usa o sistema."
          icon={<History className="h-10 w-10" />}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-48">Quando</TableHead>
                <TableHead className="w-44">Tipo</TableHead>
                <TableHead>Resumo</TableHead>
                <TableHead className="w-20 text-right">Latência</TableHead>
                <TableHead className="w-20 text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => (
                <TableRow
                  key={item.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(item)}
                >
                  <TableCell className="font-mono text-xs">
                    {new Date(item.created_at).toLocaleString("pt-BR")}
                  </TableCell>
                  <TableCell>
                    <AuditEventBadge eventType={item.event_type} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-md">
                    {summarizeEventData(item)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {item.latency_ms !== null ? `${item.latency_ms} ms` : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {item.success ? (
                      <span className="text-xs text-green-600 dark:text-green-400">ok</span>
                    ) : (
                      <span className="text-xs text-destructive">erro</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Anterior
            </Button>
            <span className="text-sm text-muted-foreground">
              Página {page} de {totalPages} ({data.total} eventos)
            </span>
            <Button variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Próximo
            </Button>
          </div>
        </>
      )}

      <AuditDetailDialog item={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </div>
  );
}

function summarizeEventData(item: AuditLogItem): string {
  const data = item.event_data;
  switch (item.event_type) {
    case "mcp.call":
      return `${data.tool_name ?? "?"}${data.success === false ? " (falhou)" : ""}`;
    case "briefing.generated":
      return `event=${data.event_id ?? "?"} model=${data.model_used ?? "?"}`;
    case "memory.created":
      return `source=${data.source ?? "?"} length=${data.content_length ?? "?"}`;
    case "voice.transcribed":
      return `${data.audio_bytes ?? "?"} bytes → ${data.transcription_length ?? "?"} chars`;
    case "webhook.received":
      return `${data.resource ?? "?"} ${data.change_type ?? ""}`;
    case "auth.login":
      return `${data.email ?? "?"}`;
    default:
      return "—";
  }
}
```

**Componente shadcn novo necessário:** `table` — adicionar via `npx shadcn@latest add table` na Tarefa do frontend.

### 7.F.5 — Integração

**`frontend/src/App.tsx`** — adicionar rota dentro do `<Routes>` autenticado:

```tsx
<Route path="/audit" element={<AuditPage />} />
```

**`frontend/src/components/AppShell.tsx`** — adicionar item ao `navItems`:

```tsx
import { History } from "lucide-react";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/briefings", label: "Briefings", icon: FileText },
  { to: "/audit", label: "Auditoria", icon: History },
  { to: "/settings", label: "Configurações", icon: Settings },
];
```

**`frontend/vite.config.ts`** — adicionar `/audit` ao `proxy`:

```ts
proxy: {
  "/auth": "http://localhost:8000",
  "/briefings": "http://localhost:8000",
  "/status": "http://localhost:8000",
  "/mcp": "http://localhost:8000",
  "/voice": "http://localhost:8000",
  "/memories": "http://localhost:8000",
  "/audit": "http://localhost:8000",  // Fase 7
},
```

### 7.F.6 — Testes do frontend (mínimo 2 novos)

- `AuditEventBadge.test.tsx` — 8 tipos conhecidos têm classes específicas; tipo desconhecido cai no fallback (`bg-muted`)
- `AuditPage.test.tsx` — render inicial mostra LoadingSkeleton; mock do hook com items mostra tabela e badges; click em row abre AuditDetailDialog; toggle em badge filtro re-dispara query

---

## Critérios de aceitação

A entrega 7 é aceita se TODOS abaixo passarem:

### Backend

1. Tabela `audit_log` criada com `event_type`, `event_data` (JSONB), `success`, `error_message` (max 500), `latency_ms`, `created_at`, indexada por `(user_id, created_at)` e `(user_id, event_type, created_at)`
2. Migration `005_add_audit_log.py` criada com `id` server-defaulted via `gen_random_uuid()` (regra M2)
3. `app/services/audit.py` exporta `AuditEventType` (StrEnum com 8 valores) e `log_event(...)` que faz `flush` (não commit) e não levanta em falha de flush
4. Cada um dos 8 tipos de evento tem hook implementado nos pontos definidos no §7.B (auth.login/logout/refresh, mcp.call, briefing.generated, memory.created, voice.transcribed, webhook.received)
5. `mcp.call` é registrado **independentemente** do success/error, com `latency_ms` medido por `time.monotonic()` e `arguments_summary` sem PII
6. `save_memory` aceita kwarg `source` ("rest"|"mcp") e propaga para `event_data.source`
7. `/auth/logout` agora exige auth e retorna 401 sem cookie/Bearer (regressão coberta por teste novo)
8. `GET /audit` aceita filtros `event_type` (lista, OR), `since`, `until`, `q` (busca em event_type e cast JSON de event_data); ordenado `created_at DESC`; paginado com `total/page/page_size`
9. `GET /audit` requer auth e isola por `user_id` (user A não vê eventos de user B)
10. `app/main.py` registra `audit.router`
11. `settings.AUDIT_HISTORY_WINDOW_DAYS` (default 30) exposto via `GET /status` no `StatusConfig.audit_history_window_days`
12. **Suíte completa de testes passa sem flags `-k` ou `-x`** — meta exata `180 baseline + 18 novos − 0 quebrados (test legado de logout atualizado, não quebrado) = 198 verdes`. **Atenção:** se mais testes pré-existentes ficarem desatualizados, **atualizar** todos no commit feat (não em commit polish separado — gap capturado na auditoria da Fase 5)

### Frontend

13. `frontend/` tem os arquivos novos do §7.F.1 (com componente shadcn `table` adicionado)
14. AppShell sidebar lista "Auditoria" com ícone `History` entre "Briefings" e "Configurações"
15. `AuditPage` (`/audit`) lista eventos em `<Table>` com colunas Quando/Tipo/Resumo/Latência/Status, ordenado mais recente primeiro
16. Click em row abre `AuditDetailDialog` com `event_type` (badge), timestamp, latência, error_message (se houver) e `event_data` formatado em `<pre>` JSON
17. Filtros funcionam: clicar numa badge de tipo toggla filtro (visual: opacity 60% inativo, ring quando ativo); search debouncing 300ms; mudança de filtros reseta para page=1
18. Estados loading/empty/error idênticos ao padrão BriefingsListPage (mesmos componentes EmptyState/LoadingSkeleton/ErrorState)
19. `npm run build` em `frontend/` zero erros TypeScript e zero warnings de `tsc`
20. `npm test` (`vitest run`) passa todos os smoke tests existentes (11) + os 2 novos da 7 → mínimo 13 verdes

### Estilo

21. Toda primitiva visual vem de `@/components/ui/` — incluindo `table` recém-adicionado
22. Cores das badges via Tailwind literais (8 cores distintas) — **única exceção justificada** ao princípio "cores via tokens shadcn" desta fase (análoga ao `bg-red-500` do RecordingIndicator da 6b); registrar no Explicação da tarefa
23. Toda página com requisição de servidor tem estados loading/empty/error onde aplicável

---

## Restrições / O que NÃO entra

- **Sem retention/cleanup automático** de eventos antigos. A tabela cresce indefinidamente nesta fase
- **Sem export CSV/JSON**
- **Sem real-time updates** (WebSocket, SSE, polling)
- **Sem agregação no endpoint** (counts por tipo, latência média, etc.)
- **Sem audit de leituras** — só de operações que alteram estado ou consomem recurso externo
- **Sem PII em event_data** — proibido logar query de email, content de memória, transcription de voz, conteúdo de briefing. Reviewer (auditor) **vai grep** no código por padrões de PII
- **Sem campo de IP/User-Agent**
- **Sem versionamento de schema do event_data**
- **Sem novos tipos de evento** fora dos 8 do inventário fechado
- **Não tocar em** `app/services/embeddings.py`, `app/services/searxng.py`, `app/services/graph.py`, `app/services/cache.py`, `app/services/groq_voice.py`, `app/models/{user,cache,webhook,embedding,memory,briefing}.py`, `app/dependencies.py`, `frontend/src/{auth,theme}/*`, `frontend/src/pages/{Login,Dashboard,BriefingDetail,BriefingsList,Settings}Page.tsx`
- **Modificações cirúrgicas em**: `app/services/memory.py` (kwarg source + log_event), `app/services/briefing.py` (log_event após commit), `app/services/webhook.py` (log_event no loop), `app/routers/auth.py` (3 hooks + dependency em logout), `app/routers/mcp.py` (try/except envolvendo dispatch + summarize_arguments), `app/routers/voice.py` (db dep + log_event), `app/routers/memories.py` (kwarg source), `app/routers/status.py` (campo novo), `app/schemas/status.py` (campo novo), `app/config.py` (1 setting), `app/main.py` (registrar router), `app/models/__init__.py` (export do AuditLog), `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/vite.config.ts`
- **Não otimizar performance** (índice GIN em event_data, materialized view, etc.) — fica para Fase 7b se necessário

---

## Estratégia de testes

### Backend

- Mocks com `unittest.mock.AsyncMock` para handlers MCP, Anthropic, Groq
- `app.dependency_overrides[get_current_user]` e `[get_db]` para testes de endpoint
- **Reuso da fixture de banco** em `tests/conftest.py` — nova tabela `audit_log` aparece automaticamente via `Base.metadata.create_all` se modelo for importado em `app/models/__init__.py`
- **Não fazer chamadas reais** a Anthropic/Groq nos testes
- **Verificar a invariante crítica do log_event:** flush não causa rollback do request (transação atômica)
- Para testes do hook em MCP, **mockar o handler da tool** mas deixar o `call_tool` real — o objetivo é garantir que `log_event` é chamado no path certo

### Frontend

- Mockar `useAuditLog` nos testes de página (sem hit no backend real)
- Reaproveitar mocks de `setup.ts` (MediaRecorder, speechSynthesis) — sem alterações
- **Sem testes E2E** — testar manualmente em Chrome/Firefox em dev:
  1. Fazer login → ver `auth.login` em /audit
  2. Logout → ver `auth.logout`
  3. Re-login + refresh manual via /settings → ver `auth.refresh`
  4. Chamar uma tool MCP via curl → ver `mcp.call` com latency
  5. Receber webhook real (ou simular POST /webhooks/notifications) → ver `webhook.received`
  6. Salvar memória pelo painel → ver `memory.created` com source=rest
  7. Salvar memória via MCP `save_memory` → ver `memory.created` com source=mcp
  8. Gravar voz e transcrever → ver `voice.transcribed`
  9. Aguardar geração automática de briefing (calendar webhook) → ver `briefing.generated`
  10. Filtrar por `mcp.call`, click em row → ver event_data com arguments_summary
  11. Search "search_emails" → eventos correspondentes filtrados

---

## Estrutura sugerida — arquivos novos e modificados

### Backend

| Arquivo                                   | Tipo  | Issue                                                |
| ----------------------------------------- | ----- | ---------------------------------------------------- |
| `app/models/audit.py`                     | NOVO  | 7.B.1                                                |
| `app/models/__init__.py`                  | MOD   | exportar AuditLog                                    |
| `alembic/versions/005_add_audit_log.py`   | NOVO  | 7.B.1                                                |
| `app/services/audit.py`                   | NOVO  | 7.B.2                                                |
| `app/services/briefing.py`                | MOD   | 7.B.3 (hook após commit do Briefing)                 |
| `app/services/memory.py`                  | MOD   | 7.B.6 (kwarg source + hook)                          |
| `app/services/webhook.py`                 | MOD   | 7.B.8 (hook por notificação)                         |
| `app/routers/auth.py`                     | MOD   | 7.B.4 (3 hooks + auth em /logout)                    |
| `app/routers/mcp.py`                      | MOD   | 7.B.5 (try/except + summarize_arguments + handle_save_memory) |
| `app/routers/memories.py`                 | MOD   | 7.B.6 (kwarg source na chamada)                      |
| `app/routers/voice.py`                    | MOD   | 7.B.7 (dep db + hook)                                |
| `app/routers/status.py`                   | MOD   | 7.B.10 (campo novo no StatusConfig)                  |
| `app/routers/audit.py`                    | NOVO  | 7.B.9                                                |
| `app/schemas/audit.py`                    | NOVO  | 7.B.9                                                |
| `app/schemas/status.py`                   | MOD   | 7.B.10                                               |
| `app/config.py`                           | MOD   | 7.B.10 (1 setting nova)                              |
| `app/main.py`                             | MOD   | registrar audit.router                               |
| `tests/test_audit_service.py`             | NOVO  | 7.B.11 (3 testes)                                    |
| `tests/test_audit_endpoint.py`            | NOVO  | 7.B.11 (8 testes)                                    |
| `tests/test_audit_hooks.py`               | NOVO  | 7.B.11 (7 testes)                                    |
| `tests/test_auth_logout_dual.py` (existente) | MOD | atualizar test legado de /auth/logout                |

### Frontend

| Arquivo                                                | Tipo | Issue                          |
| ------------------------------------------------------ | ---- | ------------------------------ |
| `frontend/src/components/ui/table.tsx`                 | NOVO | shadcn add                     |
| `frontend/src/hooks/useAuditLog.ts`                    | NOVO | 7.F.2                          |
| `frontend/src/components/AuditEventBadge.tsx`          | NOVO | 7.F.3                          |
| `frontend/src/components/AuditDetailDialog.tsx`        | NOVO | 7.F.3                          |
| `frontend/src/pages/AuditPage.tsx`                     | NOVO | 7.F.4                          |
| `frontend/src/App.tsx`                                 | MOD  | rota /audit                    |
| `frontend/src/components/AppShell.tsx`                 | MOD  | nav item "Auditoria"           |
| `frontend/vite.config.ts`                              | MOD  | proxy /audit                   |
| `frontend/src/__tests__/AuditEventBadge.test.tsx`      | NOVO | 7.F.6                          |
| `frontend/src/__tests__/AuditPage.test.tsx`            | NOVO | 7.F.6                          |

Total backend: 6 novos + 13 modificados. Total frontend: 6 novos + 3 modificados.

---

## Instrução global de documentação

Seguir o mesmo padrão das Fases 4-6b: gerar bloco "Explicação — Tarefa X.Y" para cada tarefa concluída, com arquivos, trechos relevantes, justificativa e invariantes.

---

## Observação para o KIRO

Esta fase tem **risco moderado de divergência** — ponto crítico é manter o inventário **fechado** de 8 tipos de evento. Erros comuns que o auditor já viu nas fases anteriores:

1. **Inventar tipos novos de evento** — proibido. Se algum ponto não cabe nos 8, **NÃO LOGAR** e relatar gap no checkpoint final
2. **Logar PII** — proibido logar queries de email, conteúdo de memória, transcription crua, conteúdo de briefing. Reviewer vai grep por `query`, `content`, `transcription` em eventos
3. **Middleware global** — descartado de propósito. Hooks são pontuais
4. **Quebrar regra M1 da Fase 4.5** — `log_event` não faz commit. `get_db` faz commit no boundary; background tasks fazem commit manualmente. NÃO chamar `db.commit()` dentro do `log_event`
5. **Ignorar a quebra do teste de /auth/logout** — mudança em §7.B.4 quebra teste pré-existente. **Atualizar no mesmo commit feat**, não em polish separado (gap da Fase 5)
6. **Esquecer de adicionar AuditLog ao `__init__.py` dos models** — `Base.metadata.create_all` no lifespan precisa enxergar a classe; sem isso, testes que usam DB in-memory falham silenciosamente
7. **Pular a redução PII em mcp.call** — `arguments_summary` deve ter apenas `{type, length}` por chave, nunca o `value` original (exceto numéricos/bool)
8. **Não rodar `pytest` completo** — após cada tarefa de backend, `pytest` sem flags. Reportar contagem absoluta. Meta cumulativa final: **180 baseline + 18 novos = 198 verdes**
9. **Skip do hook em webhook.received quando subscription não existe** — log com `user_id` órfão viola FK; tratar a borda
10. **Misturar paleta de cores** — 8 cores de badge são via Tailwind literais (justificativa documentada). NÃO usar variantes shadcn semânticas (primary/destructive) para diferenciar tipos

**Ordem sugerida das tarefas:**

1. Tarefa 1: Backend — modelo + migration + `__init__.py` (7.B.1) + 0 testes
2. Tarefa 2: Backend — service `audit.py` + 3 testes (7.B.2, 7.B.11 parcial)
3. Tarefa 3: Backend — hooks em auth (login/logout/refresh) + atualizar teste legado de logout + 2 testes novos (7.B.4, 7.B.11 parcial)
4. Tarefa 4: Backend — hook em MCP + summarize_arguments + 2 testes (7.B.5, 7.B.11 parcial)
5. Tarefa 5: Backend — hook em memory (REST + MCP, kwarg source) + 2 testes (7.B.6, 7.B.11 parcial)
6. Tarefa 6: Backend — hook em voice + 1 teste (7.B.7, 7.B.11 parcial)
7. Tarefa 7: Backend — hook em briefing + hook em webhook + 0 testes (cobertos por integração manual)
8. Tarefa 8: Backend — endpoint `GET /audit` + schemas + setting + status update + 8 testes (7.B.9, 7.B.10, 7.B.11)
9. Tarefa 9: Frontend — setup (`shadcn add table`) + hook + componentes (badge + dialog) + 1 teste (7.F.2, 7.F.3, 7.F.6 parcial)
10. Tarefa 10: Frontend — `AuditPage` + integração (App.tsx, AppShell, vite proxy) + 1 teste (7.F.4, 7.F.5, 7.F.6 parcial)
11. Checkpoint final — Suíte completa backend (`pytest` sem flags, esperar 198 verdes) + frontend (`npm run build` limpo, `npm test` 13 verdes), verificar escopo, sem migrations além da 005

**Comece gerando a spec em `.kiro/specs/lanez-fase7-audit/` (`design.md`, `requirements.md`, `tasks.md`)** seguindo o formato das fases anteriores. Apresente a spec para aprovação antes de implementar.
