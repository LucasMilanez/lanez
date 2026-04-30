# Documento de Requisitos — Lanez Fase 7: Audit Log (`/audit`)

## Introdução

A Fase 7 do Lanez introduz **audit log persistente**: uma trilha cronológica de eventos significativos do sistema (auth, MCP tool calls, briefing generation, memory writes, voice transcriptions, webhooks recebidos), persistida na tabela nova `audit_log`, e exposta ao usuário via página `/audit` no painel React. O backend ganha modelo + migration `005_add_audit_log.py`, service helper `app/services/audit.py` (com `AuditEventType` StrEnum e `log_event` que faz `flush` sem commit), 8 pontos de injeção nos routers/services existentes, endpoint `GET /audit` paginado com filtros (`event_type`, `since`, `until`, `q`), e nova setting `AUDIT_HISTORY_WINDOW_DAYS`. O frontend ganha hook `useAuditLog`, componentes `AuditEventBadge` + `AuditDetailDialog`, página `AuditPage` (modelo: BriefingsListPage), integração no `AppShell.navItems` e proxy Vite `/audit`. O escopo não inclui retention/cleanup automático, export CSV, real-time updates, agregações, ou audit de leituras (GET /briefings, /status, /auth/me).

### Divergências de modelo detectadas (pré-flight)

Antes de redigir os requisitos, os modelos reais foram inspecionados. Divergências relevantes em relação ao briefing:

| Divergência | Briefing assume | Modelo real | Ajuste nos requisitos |
|---|---|---|---|
| Loop `value[]` de notificações | Dentro de `app/services/webhook.py:process_notification` | Loop está em `app/routers/webhooks.py:receive_graph_notification` (linhas 115-128) — `process_notification` recebe **uma** notification por chamada e retorna `(user_id, service_type, event_id) \| None` | Hook `webhook.received` injetado **no router** dentro do loop, logo após `if result is not None` (garante `user_id` válido) |
| Commit do Briefing | Em "função background" genérica em `app/services/briefing.py` | `_briefing_background` está em `app/routers/webhooks.py:69` e chama `generate_briefing(db, redis, graph_svc, user, event_id)` em `app/services/briefing.py`; o commit manual é feito no router após o serviço retornar | Hook `briefing.generated` injetado em `app/services/briefing.py:generate_briefing` **após criar/persistir o Briefing** (ainda dentro da função do serviço — o commit do router cobre o flush) |
| `save_memory` standalone com retorno dict | Confirmado na Fase 6b | `async def save_memory(db, user_id, content, tags=None) -> dict` em `app/services/memory.py` ✓ | Adicionar kwarg `source: str = "rest"` na assinatura; passar `source="mcp"` no handler MCP, `source="rest"` no router REST |
| `/auth/logout` stateless | Confirmado | Endpoint atual NÃO usa `Depends(get_current_user)` — qualquer um bate e recebe 204 | Mudança: adicionar dependency `_get_current_user` + `get_db`; **quebra** teste pré-existente que bate sem auth e espera 204 — atualizar no mesmo commit |
| Migrations existentes | 4 migrations | `001_initial_tables`, `002_add_embeddings`, `003_add_memories`, `004_add_briefings` ✓ | Nova migration: `005_add_audit_log` com `down_revision="004_briefings"` |
| 9 tools MCP | Confirmado | `get_calendar_events`, `search_emails`, `get_onenote_pages`, `search_files`, `web_search`, `semantic_search`, `save_memory`, `recall_memory`, `get_briefing` ✓ | Hook `mcp.call` cobre as 9 tools uniformemente via `call_tool` |
| `get_db` faz commit no boundary | Confirmado | `app/database.py:get_db` faz `commit()` se sem exceção, `rollback()` caso contrário (regra Fase 4.5) ✓ | `log_event` faz apenas `flush`; commit fica para `get_db` ou caller (background tasks) |

## Glossário

- **Sistema**: aplicação backend Lanez (FastAPI)
- **Painel**: aplicação frontend React em `frontend/`
- **AuditLog**: tabela nova `audit_log` que armazena eventos persistentes
- **AuditEventType**: StrEnum em `app.services.audit` com 8 valores fechados (`auth.login`, `auth.logout`, `auth.refresh`, `mcp.call`, `briefing.generated`, `memory.created`, `voice.transcribed`, `webhook.received`)
- **log_event**: função em `app.services.audit` que cria entrada `AuditLog` e faz `flush` (NÃO commit)
- **arguments_summary**: resumo seguro de argumentos da chamada MCP — apenas `{type, length}` por chave para strings/listas, `{type, value}` para numéricos/bool — NUNCA o valor cru de strings (PII)
- **Inventário fechado**: lista pré-definida de 8 tipos de evento; novos tipos exigem revisão de spec
- **Audit de leituras**: NÃO incluído nesta fase — apenas operações que alteram estado ou consomem recurso externo (LLM, mic, Graph)

## Requisitos

### Requisito R1: Modelo + migration `audit_log`

**User Story:** Como sistema backend, quero uma tabela persistente para registrar eventos significativos do usuário, para que o painel possa exibir uma trilha cronológica de auditoria.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/models/audit.py` com classe `AuditLog(Base)` mapeando para `__tablename__ = "audit_log"` com colunas: `id` (UUID, PK, default=uuid4), `user_id` (UUID, FK users.id ondelete=CASCADE, nullable=False), `event_type` (String(64), nullable=False), `event_data` (JSONB, nullable=False, default=dict), `success` (Boolean, nullable=False, default=True), `error_message` (String(500), nullable=True), `latency_ms` (Integer, nullable=True), `created_at` (DateTime(timezone=True), nullable=False)
2. THE Sistema SHALL criar dois índices: `ix_audit_log_user_created` em `(user_id, created_at)` e `ix_audit_log_user_type_created` em `(user_id, event_type, created_at)`
3. THE Sistema SHALL criar migration Alembic `alembic/versions/005_add_audit_log.py` com `revision = "005_audit_log"` e `down_revision = "004_briefings"`
4. THE migration SHALL definir `id` com `server_default=sa.text("gen_random_uuid()")` (regra M2 da Fase 4.5)
5. THE migration SHALL definir `event_data` com `server_default=sa.text("'{}'::jsonb")` e usar `JSONB()` de `sqlalchemy.dialects.postgresql`
6. THE migration SHALL definir `success` com `server_default=sa.text("true")`
7. THE Sistema SHALL exportar `AuditLog` em `app/models/__init__.py` para que `Base.metadata.create_all` no lifespan registre a nova tabela
8. THE Sistema NÃO SHALL criar índice GIN em `event_data` nesta fase

### Requisito R2: Service helper `app/services/audit.py`

**User Story:** Como código de aplicação, quero uma função única e segura para registrar eventos no audit log, para que os 8 pontos de injeção sejam consistentes e não corrompam o estado da request.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/services/audit.py` exportando `AuditEventType` (StrEnum) e `log_event` (async function)
2. THE `AuditEventType` SHALL conter **exatamente** 8 valores: `AUTH_LOGIN = "auth.login"`, `AUTH_LOGOUT = "auth.logout"`, `AUTH_REFRESH = "auth.refresh"`, `MCP_CALL = "mcp.call"`, `BRIEFING_GENERATED = "briefing.generated"`, `MEMORY_CREATED = "memory.created"`, `VOICE_TRANSCRIBED = "voice.transcribed"`, `WEBHOOK_RECEIVED = "webhook.received"`
3. THE `log_event` SHALL ter assinatura `async def log_event(db: AsyncSession, *, user_id: UUID, event_type: AuditEventType, event_data: dict[str, Any] | None = None, success: bool = True, error_message: str | None = None, latency_ms: int | None = None) -> None`
4. THE `log_event` SHALL truncar `error_message` para no máximo 500 chars (com sufixo `"..."` quando truncado) antes de persistir
5. THE `log_event` SHALL usar `datetime.now(timezone.utc)` para `created_at`
6. THE `log_event` SHALL chamar `db.add(entry)` seguido de `await db.flush()` — NÃO chamar `db.commit()` (regra M1 da Fase 4.5)
7. IF `db.flush()` levantar exceção, THEN THE `log_event` NÃO SHALL propagar — apenas `logger.exception` e retornar `None` (audit não pode derrubar request)
8. THE `event_data` default SHALL ser `dict` vazio quando `None` é passado

### Requisito R3: Hook `auth.login`

**User Story:** Como usuário do painel, quero ver na auditoria quando autentiquei via OAuth, para identificar logins indevidos.

#### Critérios de Aceitação

1. WHEN `auth_callback` em `app/routers/auth.py` completa o `db.commit()` do User (existente ou novo) e antes de emitir o JWT interno, THEN THE Sistema SHALL chamar `log_event(db, user_id=user.id, event_type=AuditEventType.AUTH_LOGIN, event_data={"method": "oauth_callback", "had_return_url": bool(state_data.get("return_url")), "email": email}, success=True)`
2. THE hook SHALL ser executado em ambos os modos do callback (com ou sem `return_url`)
3. IF a troca de código por tokens falhar (status != 200), THEN THE Sistema NÃO SHALL registrar evento — `auth.login` é evento de sucesso

### Requisito R4: Hook `auth.logout`

**User Story:** Como usuário do painel, quero ver na auditoria quando minha sessão foi encerrada, para acompanhar atividade da minha conta.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar `auth_logout` em `app/routers/auth.py` adicionando dependências `current_user: User = Depends(_get_current_user)` e `db: AsyncSession = Depends(get_db)`
2. WHEN `auth_logout` é chamado com auth válida, THEN THE Sistema SHALL chamar `log_event(db, user_id=current_user.id, event_type=AuditEventType.AUTH_LOGOUT, event_data={}, success=True)` antes de limpar o cookie
3. THE endpoint SHALL continuar retornando 204 com `delete_cookie` (idempotente)
4. IF não houver cookie HttpOnly nem Bearer, THEN THE endpoint SHALL retornar 401 (mudança em relação à Fase 6a, que aceitava sem auth)
5. THE Sistema SHALL atualizar o teste pré-existente de `/auth/logout` (Fase 6a) que assumia stateless — enviar cookie/Bearer no novo teste; criar teste regressivo que verifica 401 sem auth

### Requisito R5: Hook `auth.refresh`

**User Story:** Como usuário do painel, quero ver na auditoria quando meus tokens Microsoft foram renovados.

#### Critérios de Aceitação

1. WHEN `auth_refresh` em `app/routers/auth.py` completa o `db.commit()` dos novos tokens, THEN THE Sistema SHALL chamar `log_event(db, user_id=current_user.id, event_type=AuditEventType.AUTH_REFRESH, event_data={"expires_in_seconds": expires_in}, success=True)`
2. IF a renovação falhar (status != 200), THEN THE Sistema NÃO SHALL registrar evento — `auth.refresh` é evento de sucesso

### Requisito R6: Hook `mcp.call`

**User Story:** Como usuário, quero ver na auditoria todas as chamadas de ferramentas MCP feitas em meu nome, com latência e sucesso/falha, para entender o que AI assistants têm feito.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar `call_tool` em `app/routers/mcp.py` envolvendo o despacho do handler em try/except que mede latência via `time.monotonic()`
2. THE Sistema SHALL chamar `log_event` **independentemente** de o handler ter sucesso ou levantar exceção, com `success=True/False` apropriado e `latency_ms` calculado
3. IF o handler levantar `HTTPException`, THEN THE Sistema SHALL registrar evento com `success=False` e `error_message=str(exc.detail)` truncado
4. IF o handler levantar `Exception` genérica, THEN THE Sistema SHALL registrar evento com `success=False` e `error_message=f"Erro interno: {exc}"` truncado, **e** retornar `jsonrpc_domain_error`
5. THE Sistema NÃO SHALL registrar evento para erros de protocolo (`method != "tools/call"`, tool inexistente, parâmetro obrigatório ausente) — esses são erros de protocolo, não de execução
6. THE Sistema SHALL criar função interna `_summarize_arguments(arguments: dict) -> dict` que retorna resumo seguro: para strings → `{"type": "string", "length": int}`; para listas → `{"type": "array", "length": int}`; para int/float/bool → `{"type": "<typename>", "value": <value>}`; para None → `{"type": "null"}`; demais → `{"type": "<typename>"}`
7. THE Sistema NÃO SHALL incluir o valor cru de strings ou listas em `arguments_summary` (PII)
8. THE `event_data` SHALL conter `{"tool_name": str, "arguments_summary": dict, "success": bool, "error_message": str | None}`

### Requisito R7: Hook `briefing.generated`

**User Story:** Como usuário, quero ver na auditoria quando briefings automáticos foram gerados pela LLM, com tokens consumidos.

#### Critérios de Aceitação

1. WHEN `generate_briefing` em `app/services/briefing.py` cria/persiste a entidade `Briefing` (após `db.add(briefing)` e `db.flush()` ou equivalente), THEN THE Sistema SHALL chamar `log_event(db, user_id=user.id, event_type=AuditEventType.BRIEFING_GENERATED, event_data={"event_id": briefing.event_id, "model_used": briefing.model_used, "input_tokens": briefing.input_tokens, "output_tokens": briefing.output_tokens, "cache_read_tokens": briefing.cache_read_tokens, "cache_write_tokens": briefing.cache_write_tokens}, success=True)`
2. THE log SHALL ser executado dentro de `generate_briefing` (não em `_briefing_background`) — o `db.commit()` manual em `_briefing_background` cobre o flush do log
3. IF `generate_briefing` levantar exceção (Anthropic 429, etc.), THEN THE Sistema NÃO SHALL registrar evento — `briefing.generated` é evento de sucesso

### Requisito R8: Hook `memory.created`

**User Story:** Como usuário, quero ver na auditoria quando memórias foram criadas, distinguindo entre painel (REST) e MCP.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar a assinatura de `save_memory` em `app/services/memory.py` para `async def save_memory(db, user_id, content, tags=None, source: str = "rest") -> dict`
2. WHEN `save_memory` persiste a Memory e antes do `return`, THEN THE Sistema SHALL chamar `log_event(db, user_id=user_id, event_type=AuditEventType.MEMORY_CREATED, event_data={"tags": tags or [], "content_length": len(content), "source": source}, success=True)`
3. THE `app/routers/mcp.py:handle_save_memory` SHALL passar `source="mcp"` ao chamar `save_memory`
4. THE `app/routers/memories.py:create_memory` SHALL passar `source="rest"` ao chamar `save_memory`
5. THE Sistema NÃO SHALL incluir o `content` cru no `event_data` — apenas `content_length` (PII)

### Requisito R9: Hook `voice.transcribed`

**User Story:** Como usuário, quero ver na auditoria quando transcrições por voz foram feitas, sem o conteúdo da transcrição.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar `transcribe` em `app/routers/voice.py` adicionando dependência `db: AsyncSession = Depends(get_db)` na assinatura
2. WHEN a chamada à Groq tem sucesso, THEN THE Sistema SHALL chamar `log_event(db, user_id=user.id, event_type=AuditEventType.VOICE_TRANSCRIBED, event_data={"audio_bytes": len(audio_bytes), "transcription_length": len(text), "duration_ms": elapsed_ms}, success=True, latency_ms=elapsed_ms)`
3. IF `GroqTranscriptionError` for levantado, THEN THE Sistema NÃO SHALL registrar evento — `voice.transcribed` é evento de sucesso
4. THE Sistema NÃO SHALL incluir a `transcription` crua no `event_data` (PII)

### Requisito R10: Hook `webhook.received`

**User Story:** Como usuário, quero ver na auditoria webhooks recebidos do Microsoft Graph, para entender o que disparou re-ingest e briefings.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar `receive_graph_notification` em `app/routers/webhooks.py` adicionando log dentro do loop de `body.get("value", [])`, **após** `process_notification` retornar
2. IF `process_notification` retornar `None` (subscrição não encontrada / sem usuário válido), THEN THE Sistema NÃO SHALL registrar evento — `user_id` órfão violaria FK
3. WHEN `process_notification` retornar tupla `(user_id, service_type, event_id)`, THEN THE Sistema SHALL chamar `log_event(db, user_id=user_id, event_type=AuditEventType.WEBHOOK_RECEIVED, event_data={"resource": notification.resource, "change_type": notification.change_type, "subscription_id": str(notification.subscription_id)}, success=True)`
4. THE log SHALL ser registrado **antes** dos `background_tasks.add_task` (ordem importa apenas para garantir que está no mesmo `db` da request)

### Requisito R11: Endpoint `GET /audit`

**User Story:** Como painel React, quero consultar o audit log do usuário com filtros e paginação, para construir a página `/audit`.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/routers/audit.py` com `APIRouter(prefix="/audit", tags=["audit"])` e endpoint `GET ""` com `response_model=AuditLogListResponse`
2. THE endpoint SHALL aceitar query params: `page: int = 1` (ge=1), `page_size: int = 50` (ge=1, le=200), `event_type: list[str] | None` (repeatable), `since: datetime | None`, `until: datetime | None`, `q: str | None`
3. THE endpoint SHALL filtrar por `user_id == user.id` (sempre, isolamento por usuário)
4. WHEN `event_type` for fornecido, THEN THE endpoint SHALL filtrar com `AuditLog.event_type.in_(event_type)` (OR lógico entre tipos)
5. WHEN `since` for fornecido, THEN THE endpoint SHALL filtrar com `AuditLog.created_at >= since`
6. WHEN `until` for fornecido, THEN THE endpoint SHALL filtrar com `AuditLog.created_at <= until`
7. WHEN `q` for fornecido, THEN THE endpoint SHALL aplicar filtro disjunto: `AuditLog.event_type ILIKE %q%` OR `cast(AuditLog.event_data, String) ILIKE %q%`
8. THE endpoint SHALL usar `count_stmt` separado para `total` (mesmos filtros, sem offset/limit) — padrão da Fase 6a
9. THE endpoint SHALL ordenar por `AuditLog.created_at DESC`
10. THE endpoint SHALL retornar `AuditLogListResponse` com campos `items` (list[AuditLogItem]), `total` (int), `page` (int), `page_size` (int)
11. THE endpoint SHALL usar `Depends(get_current_user)` e retornar 401 sem auth
12. THE Sistema SHALL criar `app/schemas/audit.py` com `AuditLogItem` (id, event_type, event_data, success, error_message, latency_ms, created_at) e `AuditLogListResponse`
13. THE `AuditLogItem` SHALL usar `model_config = ConfigDict(from_attributes=True)` para conversão direta do ORM
14. THE Sistema SHALL registrar `audit.router` em `app/main.py`

### Requisito R12: Setting `AUDIT_HISTORY_WINDOW_DAYS` + extensão de `/status`

**User Story:** Como painel, quero saber a janela default da auditoria via `/status`, para configurar a UI consistentemente com outras configurações.

#### Critérios de Aceitação

1. THE Sistema SHALL adicionar `AUDIT_HISTORY_WINDOW_DAYS: int = 30` em `app/config.py`
2. THE Sistema SHALL adicionar campo `audit_history_window_days: int` em `app/schemas/status.py:StatusConfig`
3. THE Sistema SHALL atualizar `app/routers/status.py` para retornar `StatusConfig(briefing_history_window_days=settings.BRIEFING_HISTORY_WINDOW_DAYS, audit_history_window_days=settings.AUDIT_HISTORY_WINDOW_DAYS)`

### Requisito R13: Testes do Backend (mínimo 18 novos)

**User Story:** Como desenvolvedor, quero cobertura automatizada para o helper, endpoint e hooks, para garantir que o audit log funciona corretamente e que não há regressões.

#### Critérios de Aceitação

**Service helper (3 testes em `tests/test_audit_service.py`):**

1. THE Sistema SHALL incluir `test_log_event_creates_audit_log_entry` — chama `log_event` com event_type, event_data, success, latency_ms; verifica row criada com campos corretos
2. THE Sistema SHALL incluir `test_log_event_truncates_long_error_message` — passa error_message de 600 chars; verifica row tem 500 chars terminando com `"..."`
3. THE Sistema SHALL incluir `test_log_event_does_not_raise_on_flush_failure` — mock `db.flush` levantando; verifica que função não levanta (apenas loga)

**Endpoint (8 testes em `tests/test_audit_endpoint.py`):**

4. THE Sistema SHALL incluir `test_audit_list_returns_paginated_items` — seed 5 events, GET `?page=1&page_size=2` → 2 items + total=5
5. THE Sistema SHALL incluir `test_audit_list_filters_by_event_type` — seed 3 mcp.call + 2 auth.login, filtro `event_type=mcp.call` → só 3
6. THE Sistema SHALL incluir `test_audit_list_filters_by_event_type_multiple` — seed 3 mcp.call + 2 auth.login + 1 voice, filtro `event_type=mcp.call&event_type=voice.transcribed` → 4 items
7. THE Sistema SHALL incluir `test_audit_list_filters_by_since_until` — events em 3 dias diferentes, filtro range → range correto
8. THE Sistema SHALL incluir `test_audit_list_q_searches_event_data` — seed event com `arguments_summary.tool_name=search_emails`, q=`search_emails` → 1 hit
9. THE Sistema SHALL incluir `test_audit_list_orders_desc_by_created_at` — seed 3 events em ordens diferentes; resposta vem desc
10. THE Sistema SHALL incluir `test_audit_list_requires_auth` — sem cookie/Bearer → 401
11. THE Sistema SHALL incluir `test_audit_list_isolates_per_user` — user A seeds events; user B autenticado → vê 0 items

**Hooks de injeção (7 testes em `tests/test_audit_hooks.py`):**

12. THE Sistema SHALL incluir `test_audit_logged_on_mcp_call_success` — POST /mcp/call com tool válido (mock handler) → row `mcp.call` com `success=True` e `latency_ms` presente
13. THE Sistema SHALL incluir `test_audit_logged_on_mcp_call_failure` — mock handler levantando `HTTPException` → row `mcp.call` com `success=False` e `error_message` truncado
14. THE Sistema SHALL incluir `test_audit_logged_on_memory_create_rest` — POST /memories → row `memory.created` com `event_data.source == "rest"`
15. THE Sistema SHALL incluir `test_audit_logged_on_memory_create_mcp` — POST /mcp/call save_memory → row `memory.created` com `event_data.source == "mcp"`
16. THE Sistema SHALL incluir `test_audit_logged_on_voice_transcribe_success` — POST /voice/transcribe (mock Groq) → row `voice.transcribed` com `audio_bytes` e `duration_ms`
17. THE Sistema SHALL incluir `test_audit_logged_on_auth_logout` — POST /auth/logout autenticado → row `auth.logout`; teste pré-existente de logout atualizado para enviar cookie
18. THE Sistema SHALL incluir `test_auth_logout_now_requires_auth` — POST /auth/logout sem auth → 401 (regressão da mudança em R4.4)

**Suíte completa:**

19. THE suíte completa de testes SHALL passar sem flags `-k` ou `-x` — meta exata `180 baseline + 18 novos = 198 verdes`
20. THE Sistema SHALL atualizar TODOS os testes pré-existentes que ficaram desatualizados (em particular o teste legado de `/auth/logout`) **no mesmo commit feat** — gap capturado na auditoria da Fase 5

### Requisito R14: Setup do Frontend e Hook

**User Story:** Como desenvolvedor frontend, quero o componente shadcn `table` instalado e o hook `useAuditLog` criado, para que a página de auditoria possa consumir o backend.

#### Critérios de Aceitação

1. THE Painel SHALL adicionar componente shadcn/ui `table` via `npx shadcn@latest add table` — verificar criação de `frontend/src/components/ui/table.tsx`
2. THE Painel SHALL modificar `frontend/vite.config.ts` adicionando proxy `"/audit": "http://localhost:8000"` (com comentário `// Fase 7`); NÃO alterar proxies existentes
3. THE Painel SHALL criar `frontend/src/hooks/useAuditLog.ts` exportando interfaces `AuditLogItem`, `AuditLogListResponse`, `AuditFilters` e função `useAuditLog(filters: AuditFilters)`
4. THE hook SHALL usar TanStack `useQuery` com `queryKey: ["audit", filters]`, `placeholderData: keepPreviousData`, `staleTime: 30_000`
5. THE hook SHALL construir `URLSearchParams` repetindo `event_type` para cada tipo no array (suporta filtro OR)
6. THE hook SHALL chamar `api.get<AuditLogListResponse>(\`/audit?${params.toString()}\`)`

### Requisito R15: Componentes `AuditEventBadge` e `AuditDetailDialog`

**User Story:** Como usuário, quero badges coloridas distintas por tipo de evento e um modal que mostre o detalhe completo do evento.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/components/AuditEventBadge.tsx` com `Badge variant="secondary"` da shadcn e mapping fixo de 8 tipos para classes Tailwind literais (`bg-{cor}-500/15 text-{cor}-700 dark:text-{cor}-400`)
2. THE mapping SHALL atribuir cores: `auth.login`→green, `auth.logout`→slate, `auth.refresh`→blue, `mcp.call`→purple, `briefing.generated`→amber, `memory.created`→cyan, `voice.transcribed`→pink, `webhook.received`→indigo
3. IF o `eventType` for desconhecido, THEN THE badge SHALL aplicar fallback `bg-muted text-muted-foreground`
4. THE componente SHALL aceitar prop opcional `className` para composição
5. THE Painel SHALL criar `frontend/src/components/AuditDetailDialog.tsx` usando `Dialog` da shadcn com `max-w-2xl`
6. THE dialog SHALL receber prop `item: AuditLogItem | null` — abre quando `item !== null`
7. THE dialog SHALL exibir: badge do tipo, marcador "falhou" se `!success`, timestamp formatado em `pt-BR`, latência (`{n} ms`) se presente, bloco de erro com `border-destructive/50 bg-destructive/10` se `error_message`, e `<pre>` formatado com `JSON.stringify(event_data, null, 2)`
8. THE Painel SHALL usar Tailwind literais como **única exceção** ao princípio "cores via tokens shadcn" desta fase — análoga à `bg-red-500` do `RecordingIndicator` da Fase 6b

### Requisito R16: Página `AuditPage` + integração no AppShell

**User Story:** Como usuário do painel, quero uma página com tabela paginada de eventos com filtros por tipo e busca textual, para consultar a auditoria do meu sistema.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/pages/AuditPage.tsx` com layout: título "Auditoria", input de busca com debounce 300ms, linha de badges-toggle (filtros por tipo), tabela, controles de paginação Anterior/Próximo
2. THE página SHALL usar `pageSize = 50` constante
3. THE input de busca SHALL fazer debounce de 300ms (mesmo padrão de BriefingsListPage), reseta `page = 1` na mudança
4. THE página SHALL renderizar 8 badges-toggle (uma por tipo), com visual: `opacity-60` quando inativo, `ring-2 ring-foreground/40` quando ativo
5. WHEN o usuário clicar em badge-toggle, THEN THE página SHALL alternar o tipo na lista `activeTypes` e resetar `page = 1`
6. THE tabela (`<Table>` shadcn) SHALL ter colunas: Quando (timestamp formatado pt-BR, font-mono text-xs), Tipo (`<AuditEventBadge>`), Resumo (texto truncado max-w-md, font-mono text-xs muted), Latência (`{n} ms` ou `—`, text-right), Status (`ok` em verde ou `erro` em destructive, text-right)
7. WHEN o usuário clicar em uma row, THEN THE página SHALL abrir `AuditDetailDialog` com o item selecionado
8. THE página SHALL implementar função `summarizeEventData(item)` com switch por tipo: para `mcp.call` → `tool_name + (falhou)?`; para `briefing.generated` → `event=... model=...`; para `memory.created` → `source=... length=...`; para `voice.transcribed` → `... bytes → ... chars`; para `webhook.received` → `resource change_type`; para `auth.login` → `email`; default `"—"`
9. THE página SHALL exibir EmptyState com ícone `History` quando `items.length === 0`
10. THE página SHALL exibir LoadingSkeleton (count=5) quando `isLoading`
11. THE página SHALL exibir ErrorState com `onRetry={() => void refetch()}` quando há erro
12. THE Painel SHALL modificar `frontend/src/App.tsx` adicionando `<Route path="/audit" element={<AuditPage />} />` dentro do `<Routes>` autenticado
13. THE Painel SHALL modificar `frontend/src/components/AppShell.tsx` adicionando item `{ to: "/audit", label: "Auditoria", icon: History }` ao array `navItems` entre "Briefings" e "Configurações"
14. THE Painel SHALL importar `History` de `lucide-react` em `AppShell.tsx`

### Requisito R17: Testes do Frontend (mínimo 2 novos)

**User Story:** Como desenvolvedor, quero smoke tests para os componentes novos, garantindo que renderizam corretamente e respondem a interações básicas.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/__tests__/AuditEventBadge.test.tsx`:
   - Verificar que tipos conhecidos (`auth.login`, `mcp.call`) aplicam classes específicas (ex: `text-green-700`, `text-purple-700`)
   - Verificar que tipo desconhecido (`unknown.type`) aplica fallback `bg-muted text-muted-foreground`
2. THE Painel SHALL criar `frontend/src/__tests__/AuditPage.test.tsx`:
   - Mockar `useAuditLog` retornando `isLoading: true` → verificar LoadingSkeleton presente
   - Mockar `useAuditLog` retornando items → verificar tabela presente com badges
   - Verificar que click em row abre `AuditDetailDialog` (presença do `<pre>` ou do label "Detalhes" após click)
3. THE Painel SHALL passar `npm run build` (`tsc && vite build`) com zero erros TypeScript e zero warnings
4. THE Painel SHALL passar `npm test` (`vitest run`) com todos os 11 smoke tests existentes + 2 novos = mínimo **13 verdes**

### Requisito NF1: Inventário fechado de eventos

**User Story:** Como mantenedor do sistema, quero garantir que apenas os 8 tipos de evento definidos sejam usados, para evitar drift do schema implícito de `event_data`.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL adicionar tipos de evento fora dos 8 definidos em `AuditEventType`
2. IF um ponto operacional não couber em nenhum dos 8 tipos, THEN THE implementador NÃO SHALL logar e SHALL registrar gap no checkpoint final para discussão pós-fase

### Requisito NF2: Proibição de PII em `event_data`

**User Story:** Como usuário do sistema, quero que dados sensíveis (queries, conteúdo de memória, transcrições, conteúdo de briefing) NÃO sejam persistidos no audit log.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL incluir o conteúdo cru de strings de argumentos MCP (`query`, `content`, `event_id` é OK) — apenas `{type, length}` via `_summarize_arguments`
2. THE Sistema NÃO SHALL incluir o `content` de memória — apenas `content_length`
3. THE Sistema NÃO SHALL incluir a `transcription` de voz — apenas `transcription_length`
4. THE Sistema NÃO SHALL incluir o `content` de briefing — apenas tokens e identificadores
5. THE auditor (Claude Code) SHALL grep o código por padrões de PII (`query`, `content`, `transcription`) em pontos de injeção como parte da revisão

### Requisito NF3: Regra M1 da Fase 4.5 mantida

**User Story:** Como desenvolvedor, quero que `log_event` siga a mesma regra M1 (services não fazem commit) usada nos demais services do projeto.

#### Critérios de Aceitação

1. THE `log_event` NÃO SHALL chamar `db.commit()` — apenas `db.add` + `db.flush`
2. THE commit SHALL ser feito por `get_db` (request scope) ou pelo caller (background tasks via `AsyncSessionLocal()`)
3. THE Sistema NÃO SHALL introduzir `db.commit()` em `app/services/audit.py`, `app/services/memory.py`, `app/services/briefing.py`, ou `app/services/webhook.py` — exceto onde já existem (preservar)

### Requisito NF4: Restrições de escopo

**User Story:** Como mantenedor, quero que esta fase mantenha foco no audit log essencial sem inflar com features auxiliares.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL implementar retention/cleanup automático de eventos antigos (fica para Fase 7b)
2. THE Sistema NÃO SHALL implementar export CSV/JSON
3. THE Sistema NÃO SHALL implementar real-time updates (WebSocket, SSE, polling)
4. THE Sistema NÃO SHALL implementar agregações no endpoint (counts por tipo, latência média, etc.)
5. THE Sistema NÃO SHALL incluir audit de leituras (GET /briefings, GET /status, GET /auth/me, GET /audit)
6. THE Sistema NÃO SHALL incluir campos IP/User-Agent (single-user)
7. THE Sistema NÃO SHALL implementar versionamento de schema do `event_data`

### Requisito NF5: Restrições de modificação

**User Story:** Como mantenedor, quero garantir que arquivos fora do escopo permaneçam inalterados.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL modificar `app/services/embeddings.py`, `app/services/searxng.py`, `app/services/graph.py`, `app/services/cache.py`, `app/services/groq_voice.py`
2. THE Sistema NÃO SHALL modificar `app/models/{user,cache,webhook,embedding,memory,briefing}.py`
3. THE Sistema NÃO SHALL modificar `app/dependencies.py`
4. THE Sistema NÃO SHALL modificar `frontend/src/{auth,theme}/*`
5. THE Sistema NÃO SHALL modificar `frontend/src/pages/{Login,Dashboard,BriefingDetail,BriefingsList,Settings}Page.tsx`
6. THE Sistema PODE modificar (mudanças cirúrgicas): `app/services/memory.py` (kwarg source + log_event), `app/services/briefing.py` (log_event), `app/services/webhook.py` (preservado — log fica no router), `app/routers/auth.py`, `app/routers/mcp.py`, `app/routers/memories.py`, `app/routers/voice.py`, `app/routers/webhooks.py`, `app/routers/status.py`, `app/schemas/status.py`, `app/config.py`, `app/main.py`, `app/models/__init__.py`, `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/vite.config.ts`

### Requisito NF6: Integridade da suíte de testes

**User Story:** Como desenvolvedor, quero que a suíte completa permaneça verde após as mudanças.

#### Critérios de Aceitação

1. THE suíte de testes backend SHALL manter os 180 testes existentes verdes (após atualização do teste pré-existente de logout) + 18 novos = **198 verdes**
2. THE suíte de testes frontend SHALL manter os 11 smoke tests existentes + 2 novos = mínimo **13 verdes**
3. THE suíte SHALL ser executada com `pytest` e `vitest run` sem flags `-k` ou `-x` — todos os testes devem passar
