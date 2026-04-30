# Tarefas de Implementação — Lanez Fase 7: Audit Log (`/audit`)

## Instrução global de documentação

Após implementar cada tarefa, gere um bloco de explicação com o seguinte formato:

```
### Explicação — Tarefa X.Y

**Arquivo:** `caminho/do/arquivo.py`

Para cada trecho relevante do código implementado:
- Cite o trecho (função, classe, linha ou bloco)
- Explique o que faz
- Explique por que foi escolhida essa abordagem (decisão técnica, alternativa descartada, trade-off)

Inclua especificamente:
- Por que essa biblioteca/função foi usada em vez de alternativas
- Qualquer invariante ou restrição de segurança que o código está garantindo
- O que quebraria se esse trecho fosse removido ou alterado
```

Esta instrução não é um item de tarefa — não crie checkboxes para ela. Aplica-se a todas as tarefas abaixo.

---

## Tarefa 1: Backend — Modelo + migration `audit_log` + export em `__init__.py`

- [ ] 1.1 Pré-flight — confirmar achados do código real antes de prosseguir. Reportar no bloco de explicação:
  - Migrations existentes em `alembic/versions/`: esperado `001_initial_tables`, `002_add_embeddings`, `003_add_memories`, `004_add_briefings` (4 arquivos)
  - Assinatura de `save_memory` em `app/services/memory.py`: esperado `async def save_memory(db, user_id, content, tags=None) -> dict`
  - Localização do commit do Briefing: esperado em `app/routers/webhooks.py:_briefing_background` (linha ~91, `await db.commit()`); `generate_briefing` está em `app/services/briefing.py`
  - Estrutura do loop `value[]`: esperado em `app/routers/webhooks.py:receive_graph_notification` linhas 115-128
  - Endpoint `/auth/logout`: esperado SEM `Depends(get_current_user)` atualmente
  - Lista de 9 tools MCP em `TOOLS_REGISTRY`: esperado `get_calendar_events`, `search_emails`, `get_onenote_pages`, `search_files`, `web_search`, `semantic_search`, `save_memory`, `recall_memory`, `get_briefing`
  - Confirmar que `get_db` faz commit/rollback no boundary (`app/database.py`)
  - Se algum destes pontos divergir, reportar e ajustar a implementação para o real
  - _Requisitos: R1.1–R1.7, R7.1, R10.1_

- [ ] 1.2 Criar `app/models/audit.py` com:
  - Classe `AuditLog(Base)` com `__tablename__ = "audit_log"`
  - Colunas: `id` (UUID, PK, default=uuid4), `user_id` (UUID, FK users.id ondelete=CASCADE, nullable=False), `event_type` (String(64), nullable=False), `event_data` (JSONB, nullable=False, default=dict), `success` (Boolean, nullable=False, default=True), `error_message` (String(500), nullable=True), `latency_ms` (Integer, nullable=True), `created_at` (DateTime(timezone=True), nullable=False)
  - `__table_args__` com 2 índices: `ix_audit_log_user_created` em `(user_id, created_at)` e `ix_audit_log_user_type_created` em `(user_id, event_type, created_at)`
  - Importar `JSONB` de `sqlalchemy.dialects.postgresql`
  - _Requisitos: R1.1, R1.2_

- [ ] 1.3 Criar migration `alembic/versions/005_add_audit_log.py` com:
  - `revision = "005_audit_log"`, `down_revision = "004_briefings"`
  - `op.create_table("audit_log", ...)` espelhando o modelo
  - `id` com `server_default=sa.text("gen_random_uuid()")`
  - `event_data` com `JSONB()` e `server_default=sa.text("'{}'::jsonb")`
  - `success` com `server_default=sa.text("true")`
  - `op.create_index(...)` para os 2 índices
  - `downgrade()` que dropa os índices e a tabela
  - _Requisitos: R1.3, R1.4, R1.5, R1.6_

- [ ] 1.4 Modificar `app/models/__init__.py` para exportar `AuditLog`:
  - Adicionar `from app.models.audit import AuditLog`
  - Garantir que aparece em `__all__` se houver, ou simplesmente importado para side-effect de registro
  - _Requisitos: R1.7_

- [ ] 1.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Esperado: 180 testes verdes (baseline mantido — nenhum teste novo ainda)
  - Se algum teste pré-existente falhar (ex: por mudança em `__init__.py`), investigar e reportar
  - _Requisitos: NF6.1_

## Tarefa 2: Backend — Service helper `app/services/audit.py` + 3 testes

**Dependência:** Tarefa 1 completa.

- [ ] 2.1 Criar `app/services/audit.py` com:
  - Imports: `logging`, `datetime`, `timezone`, `StrEnum`, `Any`, `UUID`, `AsyncSession`, `AuditLog`
  - Constante `_MAX_ERROR_LENGTH = 500`
  - Classe `AuditEventType(StrEnum)` com **exatamente** 8 valores: `AUTH_LOGIN = "auth.login"`, `AUTH_LOGOUT = "auth.logout"`, `AUTH_REFRESH = "auth.refresh"`, `MCP_CALL = "mcp.call"`, `BRIEFING_GENERATED = "briefing.generated"`, `MEMORY_CREATED = "memory.created"`, `VOICE_TRANSCRIBED = "voice.transcribed"`, `WEBHOOK_RECEIVED = "webhook.received"`
  - Função `async def log_event(db, *, user_id, event_type, event_data=None, success=True, error_message=None, latency_ms=None) -> None`
  - Truncamento de `error_message` para 500 chars com sufixo `"..."` quando truncado
  - `created_at = datetime.now(timezone.utc)`
  - `entry = AuditLog(...)` + `db.add(entry)` + `await db.flush()` envolto em try/except que apenas `logger.exception` (NÃO levanta)
  - NÃO chamar `db.commit()`
  - _Requisitos: R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R2.7, R2.8, NF3.1_

- [ ] 2.2 Criar `tests/test_audit_service.py` com 3 testes:
  - `test_log_event_creates_audit_log_entry` — chama `log_event` com event_type, event_data, success, latency_ms, faz commit, query a tabela e verifica row criada com campos corretos
  - `test_log_event_truncates_long_error_message` — passa `error_message="x" * 600`, query e verifica `len(row.error_message) == 500` e termina com `"..."`
  - `test_log_event_does_not_raise_on_flush_failure` — mock `db.flush` com `AsyncMock(side_effect=Exception("db down"))`, chama `log_event` e verifica que NÃO levanta (apenas executa)
  - Usar fixture de banco existente em `tests/conftest.py`
  - _Requisitos: R13.1, R13.2, R13.3_

- [ ] 2.3 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 180 baseline + 3 novos = **183 verdes**
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 3: Backend — Hooks em `auth.py` (login/logout/refresh) + atualizar teste pré-existente

**Dependência:** Tarefa 2 completa.

- [ ] 3.1 Modificar `app/routers/auth.py:auth_callback`:
  - Adicionar import: `from app.services.audit import AuditEventType, log_event`
  - Após `await db.commit()` do User (linhas ~261-262 do código atual), antes de `_create_jwt(str(user.id))`, chamar:
    ```python
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
  - _Requisitos: R3.1, R3.2_

- [ ] 3.2 Modificar `app/routers/auth.py:auth_logout`:
  - Adicionar dependências `current_user: User = Depends(_get_current_user)` e `db: AsyncSession = Depends(get_db)` na assinatura
  - Adicionar import `AsyncSession` se ausente
  - Antes de criar `Response` e `delete_cookie`, chamar `log_event` com `AuditEventType.AUTH_LOGOUT`, `event_data={}`
  - Manter retorno 204 com `delete_cookie` idempotente
  - _Requisitos: R4.1, R4.2, R4.3, R4.4_

- [ ] 3.3 Modificar `app/routers/auth.py:auth_refresh`:
  - Após `await db.commit()` (linha ~412 do código atual), antes de `_create_jwt(str(current_user.id))`, chamar:
    ```python
    await log_event(
        db,
        user_id=current_user.id,
        event_type=AuditEventType.AUTH_REFRESH,
        event_data={"expires_in_seconds": expires_in},
        success=True,
    )
    ```
  - _Requisitos: R5.1, R5.2_

- [ ] 3.4 Atualizar teste pré-existente de `/auth/logout` (Fase 6a) que assumia stateless:
  - Localizar teste em `tests/` que bate `POST /auth/logout` SEM auth e espera 204
  - Atualizar para enviar cookie/Bearer válido (via `app.dependency_overrides[_get_current_user]`)
  - Adicionar 2 testes novos:
    - `test_audit_logged_on_auth_logout` — POST autenticado → row `auth.logout` no audit_log
    - `test_auth_logout_now_requires_auth` — POST sem auth → 401
  - **Atenção:** atualizar no MESMO commit feat — não deixar para polish (gap da Fase 5)
  - _Requisitos: R4.5, R13.17, R13.18, R13.20_

- [ ] 3.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 183 + 2 novos = **185 verdes** (mais o teste pré-existente atualizado, sem mudar o total)
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 4: Backend — Hook em MCP + `_summarize_arguments` + 2 testes

**Dependência:** Tarefa 2 completa.

- [ ] 4.1 Modificar `app/routers/mcp.py`:
  - Adicionar import: `import time`, `from app.services.audit import AuditEventType, log_event`
  - Adicionar função interna `_summarize_arguments(arguments: dict) -> dict` conforme spec:
    - `str` → `{"type": "string", "length": len(value)}`
    - `list` → `{"type": "array", "length": len(value)}`
    - `int/float/bool` → `{"type": type(value).__name__, "value": value}`
    - `None` → `{"type": "null"}`
    - outros → `{"type": type(value).__name__}`
  - **NÃO** incluir o valor cru de strings/listas (PII)
  - _Requisitos: R6.6, R6.7, NF2.1_

- [ ] 4.2 Modificar `call_tool` em `app/routers/mcp.py`:
  - Após as validações de protocolo (método, tool existe, params obrigatórios) — que NÃO logam — envolver o despacho em try/except medindo latência:
    ```python
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
  - _Requisitos: R6.1, R6.2, R6.3, R6.4, R6.5, R6.8_

- [ ] 4.3 Adicionar 2 testes em `tests/test_audit_hooks.py`:
  - `test_audit_logged_on_mcp_call_success` — POST `/mcp/call` com tool válida (mockar handler retornando dict), verificar row `mcp.call` com `success=True` e `latency_ms` presente; verificar que `event_data.tool_name` está correto e `arguments_summary` tem apenas `{type, length}`/`{type, value}` (sem strings cruas)
  - `test_audit_logged_on_mcp_call_failure` — mockar handler levantando `HTTPException(detail="...")`, verificar row `mcp.call` com `success=False` e `error_message` truncado a 500 chars (passar uma exceção com 600 chars)
  - _Requisitos: R13.12, R13.13_

- [ ] 4.4 Rodar `pytest` completo (sem `-k`, sem `-x`). Meta: 185 + 2 = **187 verdes**
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 5: Backend — Hook em memory (REST + MCP) + kwarg `source` + 2 testes

**Dependência:** Tarefa 2 completa.

- [ ] 5.1 Modificar `app/services/memory.py:save_memory`:
  - Adicionar kwarg `source: str = "rest"` na assinatura (após `tags`)
  - Adicionar import: `from app.services.audit import AuditEventType, log_event`
  - Antes do `return` final (após persistir Memory e fazer flush/refresh), chamar:
    ```python
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
    ```
  - **NÃO** incluir `content` cru no event_data (PII)
  - _Requisitos: R8.1, R8.2, R8.5, NF2.2_

- [ ] 5.2 Modificar `app/routers/memories.py:create_memory`:
  - Passar `source="rest"` na chamada `save_memory(...)`
  - _Requisitos: R8.4_

- [ ] 5.3 Modificar `app/routers/mcp.py:handle_save_memory`:
  - Passar `source="mcp"` na chamada `save_memory(...)`
  - _Requisitos: R8.3_

- [ ] 5.4 Adicionar 2 testes em `tests/test_audit_hooks.py`:
  - `test_audit_logged_on_memory_create_rest` — POST `/memories` autenticado com body válido → query audit_log e verificar row `memory.created` com `event_data.source == "rest"`, `tags` corretos, `content_length` correto
  - `test_audit_logged_on_memory_create_mcp` — POST `/mcp/call` com `tool=save_memory` e arguments válidos → query audit_log e verificar row `memory.created` com `event_data.source == "mcp"`. **Atenção:** este teste vai gerar 2 rows no audit (uma `mcp.call` + uma `memory.created`); verificar especificamente a `memory.created`
  - _Requisitos: R13.14, R13.15_

- [ ] 5.5 Rodar `pytest` completo. Meta: 187 + 2 = **189 verdes**
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 6: Backend — Hook em voice + dependência `db` + 1 teste

**Dependência:** Tarefa 2 completa.

- [ ] 6.1 Modificar `app/routers/voice.py:transcribe`:
  - Adicionar import: `from sqlalchemy.ext.asyncio import AsyncSession`, `from app.database import get_db`, `from app.services.audit import AuditEventType, log_event`
  - Adicionar dependência `db: AsyncSession = Depends(get_db)` na assinatura
  - Após `text = await transcribe_audio(...)` ter sucesso e antes do `return`, chamar:
    ```python
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
  - **NÃO** logar em caso de `GroqTranscriptionError` (path de falha não registra)
  - **NÃO** incluir a transcrição crua no event_data (PII)
  - _Requisitos: R9.1, R9.2, R9.3, R9.4, NF2.3_

- [ ] 6.2 Adicionar 1 teste em `tests/test_audit_hooks.py`:
  - `test_audit_logged_on_voice_transcribe_success` — mockar `transcribe_audio` retornando "texto teste", POST `/voice/transcribe` com áudio válido → row `voice.transcribed` com `audio_bytes`, `transcription_length`, `duration_ms`, `latency_ms`
  - _Requisitos: R13.16_

- [ ] 6.3 Rodar `pytest` completo. Meta: 189 + 1 = **190 verdes**
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 7: Backend — Hook em briefing + hook em webhook (sem testes — cobertos por integração manual)

**Dependência:** Tarefa 2 completa.

- [ ] 7.1 Modificar `app/services/briefing.py:generate_briefing`:
  - Adicionar import: `from app.services.audit import AuditEventType, log_event`
  - Após criar/persistir o objeto `Briefing` (após `db.add(briefing)` e `db.flush()`/`db.refresh()`), antes do return, chamar:
    ```python
    await log_event(
        db,
        user_id=user.id,
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
    ```
  - **NÃO** logar em caso de exceção (Anthropic 429, etc.) — `briefing.generated` é evento de sucesso
  - **NÃO** alterar `app/routers/webhooks.py:_briefing_background` — o `db.commit()` manual já existente cobre o flush do log
  - _Requisitos: R7.1, R7.2, R7.3_

- [ ] 7.2 Modificar `app/routers/webhooks.py:receive_graph_notification`:
  - Adicionar import: `from app.services.audit import AuditEventType, log_event`
  - Dentro do loop `for item in body.get("value", []):`, após `result = await webhook_service.process_notification(...)`, dentro do `if result is not None:`, antes dos `background_tasks.add_task`, chamar:
    ```python
    user_id, service_type, event_id = result
    await log_event(
        db,
        user_id=user_id,
        event_type=AuditEventType.WEBHOOK_RECEIVED,
        event_data={
            "resource": notification.resource,
            "change_type": notification.change_type,
            "subscription_id": str(notification.subscription_id),
        },
        success=True,
    )
    background_tasks.add_task(_reingest_background, user_id, service_type)
    if event_id is not None and service_type == ServiceType.CALENDAR:
        background_tasks.add_task(_briefing_background, user_id, event_id)
    ```
  - Se `result is None` (subscrição inválida), NÃO logar — user_id órfão violaria FK
  - _Requisitos: R10.1, R10.2, R10.3, R10.4_

- [ ] 7.3 Rodar `pytest` completo. Meta: **190 verdes** (sem novos testes nesta tarefa)
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 8: Backend — Endpoint `GET /audit` + schemas + setting + status update + 8 testes

**Dependência:** Tarefas 1-2 completas.

- [ ] 8.1 Adicionar setting em `app/config.py`:
  - `AUDIT_HISTORY_WINDOW_DAYS: int = 30` (antes de `model_config`)
  - _Requisitos: R12.1_

- [ ] 8.2 Modificar `app/schemas/status.py:StatusConfig`:
  - Adicionar campo `audit_history_window_days: int`
  - _Requisitos: R12.2_

- [ ] 8.3 Modificar `app/routers/status.py:get_status`:
  - Atualizar a construção de `StatusConfig` para incluir `audit_history_window_days=settings.AUDIT_HISTORY_WINDOW_DAYS`
  - _Requisitos: R12.3_

- [ ] 8.4 Criar `app/schemas/audit.py`:
  - `AuditLogItem(BaseModel)` com `model_config = ConfigDict(from_attributes=True)`, campos `id` (UUID), `event_type` (str), `event_data` (dict[str, Any]), `success` (bool), `error_message` (str | None), `latency_ms` (int | None), `created_at` (datetime)
  - `AuditLogListResponse(BaseModel)` com `items` (list[AuditLogItem]), `total` (int), `page` (int), `page_size` (int)
  - _Requisitos: R11.12, R11.13_

- [ ] 8.5 Criar `app/routers/audit.py`:
  - `APIRouter(prefix="/audit", tags=["audit"])`
  - Endpoint `GET ""` com `response_model=AuditLogListResponse`
  - Query params: `page` (int, default=1, ge=1), `page_size` (int, default=50, ge=1, le=200), `event_type` (list[str] | None, default=None — repeatable), `since` (datetime | None), `until` (datetime | None), `q` (str | None)
  - Auth via `Depends(get_current_user)`
  - Filtros:
    - `AuditLog.user_id == user.id` (sempre)
    - Se `event_type`: `AuditLog.event_type.in_(event_type)`
    - Se `since`: `AuditLog.created_at >= since`
    - Se `until`: `AuditLog.created_at <= until`
    - Se `q`: `(AuditLog.event_type.ilike(f"%{q}%")) | (func.cast(AuditLog.event_data, String).ilike(f"%{q}%"))`
  - `count_stmt` separado para `total`
  - `paged_stmt` com `order_by(AuditLog.created_at.desc())`, `offset((page - 1) * page_size)`, `limit(page_size)`
  - Importar `String` de `sqlalchemy` para o cast no filtro `q`
  - _Requisitos: R11.1–R11.11_

- [ ] 8.6 Modificar `app/main.py`:
  - Adicionar `from app.routers import audit` no import
  - Adicionar `app.include_router(audit.router)` junto aos demais
  - _Requisitos: R11.14_

- [ ] 8.7 Criar `tests/test_audit_endpoint.py` com 8 testes:
  - `test_audit_list_returns_paginated_items` — seed 5 events do mesmo user, GET `/audit?page=1&page_size=2` → response com 2 items, `total=5`, `page=1`, `page_size=2`
  - `test_audit_list_filters_by_event_type` — seed 3 mcp.call + 2 auth.login do mesmo user, GET `/audit?event_type=mcp.call` → 3 items, todos `event_type == "mcp.call"`
  - `test_audit_list_filters_by_event_type_multiple` — seed 3 mcp.call + 2 auth.login + 1 voice.transcribed, GET `/audit?event_type=mcp.call&event_type=voice.transcribed` → 4 items
  - `test_audit_list_filters_by_since_until` — seed 3 events em datas distintas (ex: hoje, ontem, semana passada), GET com `since` e `until` cobrindo apenas hoje e ontem → 2 items
  - `test_audit_list_q_searches_event_data` — seed event com `event_data={"tool_name": "search_emails", ...}`, GET `/audit?q=search_emails` → 1 hit
  - `test_audit_list_orders_desc_by_created_at` — seed 3 events em ordens trocadas, GET → response em ordem `created_at` decrescente
  - `test_audit_list_requires_auth` — GET sem cookie/Bearer → 401
  - `test_audit_list_isolates_per_user` — seed 3 events do user A, GET autenticado como user B → 0 items
  - Usar `app.dependency_overrides[get_current_user]` e `[get_db]` conforme padrão da Fase 6a
  - _Requisitos: R13.4–R13.11_

- [ ] 8.8 Rodar `pytest` completo. Meta: 190 + 8 = **198 verdes** (meta final backend)
  - _Requisitos: NF6.1, NF6.3_

## Tarefa 9: Frontend — Setup (shadcn `table`) + hook + componentes (badge + dialog) + 1 teste

**Dependência:** Tarefas 1-8 (backend) completas.

- [ ] 9.1 Adicionar componente shadcn/ui `table`: executar `npx shadcn@latest add table` em `frontend/`. Verificar criação de `frontend/src/components/ui/table.tsx`
  - _Requisitos: R14.1_

- [ ] 9.2 Modificar `frontend/vite.config.ts`:
  - Adicionar `"/audit": "http://localhost:8000",` ao objeto `proxy` (com comentário `// Fase 7`)
  - NÃO alterar proxies existentes (`/auth`, `/briefings`, `/status`, `/mcp`, `/voice`, `/memories`)
  - _Requisitos: R14.2_

- [ ] 9.3 Criar `frontend/src/hooks/useAuditLog.ts`:
  - Imports: `useQuery`, `keepPreviousData` (`@tanstack/react-query`), `api` (`@/lib/api`)
  - Interfaces exportadas: `AuditLogItem`, `AuditLogListResponse`, `AuditFilters`
  - Função `useAuditLog(filters: AuditFilters)`:
    - Monta `URLSearchParams` com `page`, `page_size`; repete `event_type` para cada item; adiciona `since`, `until`, `q` se presentes
    - `useQuery` com `queryKey: ["audit", filters]`, `queryFn` chamando `api.get<AuditLogListResponse>(\`/audit?${params.toString()}\`)`, `placeholderData: keepPreviousData`, `staleTime: 30_000`
  - _Requisitos: R14.3, R14.4, R14.5, R14.6_

- [ ] 9.4 Criar `frontend/src/components/AuditEventBadge.tsx`:
  - Imports: `Badge` (`@/components/ui/badge`), `cn` (`@/lib/utils`)
  - Constante `TYPE_STYLES: Record<string, string>` com 8 entradas (Tailwind literais conforme spec):
    - `auth.login` → `bg-green-500/15 text-green-700 dark:text-green-400`
    - `auth.logout` → `bg-slate-500/15 text-slate-700 dark:text-slate-400`
    - `auth.refresh` → `bg-blue-500/15 text-blue-700 dark:text-blue-400`
    - `mcp.call` → `bg-purple-500/15 text-purple-700 dark:text-purple-400`
    - `briefing.generated` → `bg-amber-500/15 text-amber-700 dark:text-amber-400`
    - `memory.created` → `bg-cyan-500/15 text-cyan-700 dark:text-cyan-400`
    - `voice.transcribed` → `bg-pink-500/15 text-pink-700 dark:text-pink-400`
    - `webhook.received` → `bg-indigo-500/15 text-indigo-700 dark:text-indigo-400`
  - Constante `FALLBACK_STYLE = "bg-muted text-muted-foreground"`
  - Componente recebe `eventType` e `className` (opcional); aplica classe via `cn(style, "font-mono text-xs", className)`
  - `Badge variant="secondary"` envolve o texto `eventType`
  - **Documentar no Explicação:** única exceção da fase ao princípio "cores via tokens shadcn" (análoga ao `bg-red-500` do RecordingIndicator da 6b)
  - _Requisitos: R15.1, R15.2, R15.3, R15.4, R15.8_

- [ ] 9.5 Criar `frontend/src/components/AuditDetailDialog.tsx`:
  - Imports: `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription` (`@/components/ui/dialog`), `AuditEventBadge`, `AuditLogItem` (`@/hooks/useAuditLog`)
  - Props: `item: AuditLogItem | null`, `onOpenChange: (open: boolean) => void`
  - `Dialog` aberto quando `item !== null` (passar `open={item !== null}`)
  - `DialogContent` com `max-w-2xl`
  - Conteúdo (apenas se `item`):
    - `DialogHeader` com flex containing `<AuditEventBadge>` e marker "falhou" se `!item.success`
    - `DialogTitle` font-mono text-sm com `new Date(item.created_at).toLocaleString("pt-BR")`
    - `DialogDescription` com latência (`{n} ms`) se presente
    - Bloco de erro (se `item.error_message`): div com classes `border-destructive/50 bg-destructive/10`, mostra "Erro" + texto
    - Bloco "Detalhes": `<pre>` com classes `bg-muted text-xs font-mono overflow-auto max-h-96`, conteúdo `JSON.stringify(item.event_data, null, 2)`
  - _Requisitos: R15.5, R15.6, R15.7_

- [ ] 9.6 Criar `frontend/src/__tests__/AuditEventBadge.test.tsx` com 1 cobertura:
  - Verificar que rendering com `eventType="auth.login"` aplica classe `text-green-700`
  - Verificar que rendering com `eventType="mcp.call"` aplica classe `text-purple-700`
  - Verificar que rendering com `eventType="unknown.type"` aplica classe `bg-muted` (fallback)
  - _Requisitos: R17.1_

- [ ] 9.7 Verificar `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R17.3_

## Tarefa 10: Frontend — `AuditPage` + integração no AppShell + 1 teste

**Dependência:** Tarefa 9 completa.

- [ ] 10.1 Criar `frontend/src/pages/AuditPage.tsx`:
  - Imports: `useEffect`, `useState`, `History` (lucide-react), `Input`, `Button`, `Table` family (`@/components/ui/table`), `AuditEventBadge`, `AuditDetailDialog`, `LoadingSkeleton`, `EmptyState`, `ErrorState`, `useAuditLog`, `AuditLogItem`
  - Constante `EVENT_TYPES` com os 8 valores
  - Estados locais: `page` (default 1), `search` (default ""), `debouncedSearch`, `selected` (`AuditLogItem | null`), `activeTypes` (`string[]`)
  - Constante `pageSize = 50`
  - `useEffect` com debounce 300ms para `setDebouncedSearch(search)` e `setPage(1)`
  - Chamar `useAuditLog({ page, pageSize, eventTypes: activeTypes.length > 0 ? activeTypes : undefined, q: debouncedSearch || undefined })`
  - `totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1`
  - Função `toggleType(type: string)`: toggla em `activeTypes` e reseta `page = 1`
  - Função `summarizeEventData(item: AuditLogItem): string` com switch:
    - `mcp.call` → `\`${data.tool_name ?? "?"}${data.success === false ? " (falhou)" : ""}\``
    - `briefing.generated` → `\`event=${data.event_id ?? "?"} model=${data.model_used ?? "?"}\``
    - `memory.created` → `\`source=${data.source ?? "?"} length=${data.content_length ?? "?"}\``
    - `voice.transcribed` → `\`${data.audio_bytes ?? "?"} bytes → ${data.transcription_length ?? "?"} chars\``
    - `webhook.received` → `\`${data.resource ?? "?"} ${data.change_type ?? ""}\``
    - `auth.login` → `\`${data.email ?? "?"}\``
    - default → `"—"`
  - Layout: título "Auditoria", input de busca, linha de 8 badges-toggle (com visual `opacity-60` inativo / `ring-2 ring-foreground/40` ativo), Table 5 colunas (Quando / Tipo / Resumo / Latência / Status), paginação Anterior/Próximo, `AuditDetailDialog`
  - Estados: loading → `LoadingSkeleton`; error → `ErrorState`; empty → `EmptyState`; list → Table
  - Click em row → `setSelected(item)`; close do Dialog → `setSelected(null)`
  - _Requisitos: R16.1–R16.11_

- [ ] 10.2 Modificar `frontend/src/App.tsx`:
  - Adicionar `<Route path="/audit" element={<AuditPage />} />` dentro do `<Routes>` autenticado
  - Adicionar import `import { AuditPage } from "@/pages/AuditPage"`
  - _Requisitos: R16.12_

- [ ] 10.3 Modificar `frontend/src/components/AppShell.tsx`:
  - Adicionar `History` ao import de `lucide-react`
  - Adicionar `{ to: "/audit", label: "Auditoria", icon: History }` ao array `navItems` **entre** "Briefings" e "Configurações"
  - NÃO alterar mais nada na AppShell
  - _Requisitos: R16.13, R16.14_

- [ ] 10.4 Criar `frontend/src/__tests__/AuditPage.test.tsx`:
  - Mockar `useAuditLog` retornando `isLoading: true` → verificar presença de LoadingSkeleton (`data-testid` ou className específica)
  - Mockar `useAuditLog` retornando 2 items mock → verificar presença de Table e badges
  - Verificar que click em row abre `AuditDetailDialog` (presença do label "Detalhes" ou do `<pre>` após click)
  - _Requisitos: R17.2_

- [ ] 10.5 Verificar `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R17.3_

- [ ] 10.6 Verificar `npm test` (`vitest run`) em `frontend/`. Todos os 11 smoke tests existentes + 2 novos = mínimo **13 verdes**
  - _Requisitos: R17.4, NF6.2_

## Tarefa 11: Checkpoint Final

**Dependência:** Tarefas 1-10 completas.

- [ ] 11.1 Rodar `pytest` no backend (sem `-k`, sem `-x`) — meta exata: **198 verdes** (180 baseline + 18 novos: 3 service + 8 endpoint + 7 hooks)
  - Se contagem divergir, investigar antes de marcar concluído
  - _Requisitos: NF6.1, NF6.3_

- [ ] 11.2 Rodar `npm test` no frontend — mínimo **13 verdes** (11 baseline + 2 novos)
  - _Requisitos: NF6.2_

- [ ] 11.3 Verificar que apenas os arquivos listados no escopo foram modificados:
  - **Modificações esperadas:**
    - `app/services/memory.py` — kwarg + log_event
    - `app/services/briefing.py` — log_event
    - `app/routers/auth.py` — 3 hooks + dep em logout
    - `app/routers/mcp.py` — try/except + summarize_arguments + handle_save_memory
    - `app/routers/memories.py` — kwarg source
    - `app/routers/voice.py` — dep db + log_event
    - `app/routers/webhooks.py` — log_event no loop
    - `app/routers/status.py` — campo novo no StatusConfig
    - `app/schemas/status.py` — campo novo
    - `app/config.py` — 1 setting
    - `app/main.py` — registrar audit.router
    - `app/models/__init__.py` — export AuditLog
    - `frontend/src/App.tsx` — rota /audit
    - `frontend/src/components/AppShell.tsx` — nav item
    - `frontend/vite.config.ts` — proxy /audit
  - **Arquivos NOVOS esperados:**
    - `app/models/audit.py`
    - `alembic/versions/005_add_audit_log.py`
    - `app/services/audit.py`
    - `app/routers/audit.py`
    - `app/schemas/audit.py`
    - `tests/test_audit_service.py`
    - `tests/test_audit_endpoint.py`
    - `tests/test_audit_hooks.py`
    - `frontend/src/components/ui/table.tsx` (shadcn)
    - `frontend/src/hooks/useAuditLog.ts`
    - `frontend/src/components/AuditEventBadge.tsx`
    - `frontend/src/components/AuditDetailDialog.tsx`
    - `frontend/src/pages/AuditPage.tsx`
    - `frontend/src/__tests__/AuditEventBadge.test.tsx`
    - `frontend/src/__tests__/AuditPage.test.tsx`
  - **Arquivos NÃO devem ter sido tocados:**
    - `app/services/embeddings.py`, `app/services/searxng.py`, `app/services/graph.py`, `app/services/cache.py`, `app/services/groq_voice.py`
    - `app/models/{user,cache,webhook,embedding,memory,briefing}.py`
    - `app/dependencies.py`
    - `frontend/src/{auth,theme}/*`
    - `frontend/src/pages/{Login,Dashboard,BriefingDetail,BriefingsList,Settings}Page.tsx`
  - _Requisitos: NF5.1, NF5.2, NF5.3, NF5.4, NF5.5, NF5.6_

- [ ] 11.4 Verificar que apenas a migration `005_add_audit_log.py` foi criada — `alembic/versions/` deve ter exatamente 5 arquivos (001, 002, 003, 004, 005)
  - _Requisitos: R1.3_

- [ ] 11.5 Verificar inventário fechado de eventos:
  - `grep -rn "AuditEventType\." app/` deve mostrar apenas referências aos 8 valores definidos
  - Nenhum `event_type` literal sendo passado direto a `log_event` (sempre via `AuditEventType.*`)
  - _Requisitos: NF1.1, NF1.2_

- [ ] 11.6 Verificar ausência de PII em event_data:
  - `grep -rn "log_event" app/` — para cada chamada, conferir que nenhum dos campos passados em `event_data` contém: o `query` cru de uma tool MCP, o `content` cru de memória, a `transcription` crua de voz, o `content` cru de briefing
  - O único uso de `len(...)` em vez de valor cru deve estar nos hooks de memory (`content_length`) e voice (`transcription_length`)
  - _Requisitos: NF2.1, NF2.2, NF2.3, NF2.4, NF2.5_

- [ ] 11.7 Verificar regra M1 da Fase 4.5:
  - `grep -n "db.commit" app/services/audit.py app/services/memory.py app/services/briefing.py` — não deve haver novos `db.commit()` nesses arquivos
  - _Requisitos: NF3.1, NF3.2, NF3.3_

## Notas

- Tarefas 1-8 são backend e devem ser completadas e testadas antes de iniciar o frontend (Tarefas 9-10)
- Cada tarefa termina com execução completa do `pytest` para garantir regressão zero — reportar contagem absoluta
- A meta exata de testes backend é **198 verdes** ao final da Tarefa 8 (e mantida nas demais)
- **Atualizar o teste pré-existente de `/auth/logout` no MESMO commit feat** (Tarefa 3.4) — não deixar para polish (gap da Fase 5)
- **Inventário fechado:** se durante a implementação algum ponto operacional não couber em nenhum dos 8 tipos, NÃO logar e reportar gap no checkpoint final para discussão pós-fase
- **Sem PII em event_data:** nunca incluir `query` cru de tool, `content` cru de memória, `transcription` crua de voz, `content` cru de briefing — apenas tamanhos e identificadores
- **Cores das badges via Tailwind literais** (8 cores distintas) é a única exceção justificada da fase ao princípio "cores via tokens shadcn" — documentar explicitamente no Explicação da Tarefa 9.4
- **Webhook hook:** registrar APENAS quando `result is not None` (caso contrário, FK violada)
- **Briefing hook:** dentro de `generate_briefing` (service), NÃO em `_briefing_background` (router) — o commit do router cobre o flush
- **MCP hook:** registra **falhas** (success=true/false) — único evento que faz isso; demais só path feliz
- **`/auth/logout` agora exige auth** — quebra teste pré-existente; atualizar no mesmo commit
- Propriedades formais de corretude estão definidas em `design.md`
- UI fixa em pt-BR — sem internacionalização
