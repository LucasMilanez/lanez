# Tarefas de Implementação — Lanez Fase 5: Briefing Automático de Reunião

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

## Tarefa 1: Config + Schema Pydantic + requirements.txt

- [x] 1.1 Adicionar `ANTHROPIC_API_KEY: str` (obrigatório, sem default) e `BRIEFING_HISTORY_WINDOW_DAYS: int = 90` à classe `Settings` em `app/config.py`. Adicionar entrada `ANTHROPIC_API_KEY=` em `.env.example` com comentário `# Obter em https://console.anthropic.com/`
- [x] 1.2 Criar `app/schemas/briefing.py` com classe `BriefingResponse(BaseModel)` contendo campos: id (UUID), event_id (str), event_subject (str), event_start (datetime), event_end (datetime), attendees (list[str]), content (str), generated_at (datetime), model_used (str), input_tokens (int), cache_read_tokens (int), cache_write_tokens (int), output_tokens (int). Imports: `from datetime import datetime`, `from uuid import UUID`, `from pydantic import BaseModel`
- [x] 1.3 Adicionar `anthropic>=0.40.0` em `requirements.txt` (ao final do arquivo, mantendo ordem alfabética se existir)
- [x] 1.4 Adicionar `ANTHROPIC_API_KEY=test-key-not-real` em `conftest.py` ou `.env.test` conforme padrão existente no projeto (verificar como `MICROSOFT_CLIENT_ID` e similares são mockados nos testes e seguir o mesmo padrão)

## Tarefa 2: Modelo + Models Init + Migration 004

- [x] 2.1 Criar `app/models/briefing.py` com classe `Briefing(Base)`: `__tablename__ = "briefings"`, colunas id (Mapped[uuid.UUID] Uuid PK default uuid4), user_id (Mapped[uuid.UUID] Uuid FK "users.id" ondelete="CASCADE" nullable=False), event_id (Mapped[str] String(255) nullable=False), event_subject (Mapped[str] String(500) nullable=False), event_start (Mapped[datetime] DateTime(timezone=True) nullable=False), event_end (Mapped[datetime] DateTime(timezone=True) nullable=False), attendees (Mapped[list[str]] ARRAY(String) nullable=False default=list), content (Mapped[str] Text nullable=False), model_used (Mapped[str] String(64) nullable=False), input_tokens (Mapped[int] Integer nullable=False default=0), cache_read_tokens (Mapped[int] Integer nullable=False default=0), cache_write_tokens (Mapped[int] Integer nullable=False default=0), output_tokens (Mapped[int] Integer nullable=False default=0), generated_at (Mapped[datetime] DateTime(timezone=True) nullable=False). `__table_args__` com UniqueConstraint("user_id", "event_id", name="uq_briefing_user_event") e Index("ix_briefings_user_event_start", "user_id", "event_start")
- [x] 2.2 Atualizar `app/models/__init__.py`: importar `Briefing` de `app.models.briefing` e adicionar ao `__all__` em ordem alfabética (entre `Base` e `Embedding`)
- [x] 2.3 Criar `alembic/versions/004_add_briefings.py` com revision="004_briefings", down_revision="003_memories". Upgrade: criar tabela `briefings` com id (Uuid PK server_default=sa.text("gen_random_uuid()")), user_id (Uuid FK users.id CASCADE not null), event_id (String(255) not null), event_subject (String(500) not null), event_start (DateTime(timezone=True) not null), event_end (DateTime(timezone=True) not null), attendees (ARRAY(String) not null server_default=sa.text("ARRAY[]::varchar[]")), content (Text not null), model_used (String(64) not null), input_tokens (Integer not null server_default=sa.text("0")), cache_read_tokens (Integer not null server_default=sa.text("0")), cache_write_tokens (Integer not null server_default=sa.text("0")), output_tokens (Integer not null server_default=sa.text("0")), generated_at (DateTime(timezone=True) not null). Criar UniqueConstraint e Index. Downgrade: drop index + drop table

## Tarefa 3: Anthropic Client + testes

- [x] 3.1 Criar `app/services/anthropic_client.py` com: constantes `_MODEL_ID = "claude-haiku-4-5-20251001"` e `_MAX_TOKENS = 1500`; dataclass ou classe `BriefingResult` com campos content (str), model (str), input_tokens (int), cache_read_tokens (int), cache_write_tokens (int), output_tokens (int); função `get_anthropic_client() -> AsyncAnthropic` (singleton via global `_client`); função async `generate_briefing_text(system_prompt: str, user_content: str) -> BriefingResult` que chama `client.messages.create(model=_MODEL_ID, max_tokens=_MAX_TOKENS, system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}], messages=[{"role": "user", "content": user_content}])` e retorna BriefingResult com content=response.content[0].text, model=response.model, input_tokens=response.usage.input_tokens, cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0, cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0, output_tokens=response.usage.output_tokens
- [x] 3.2 Criar `tests/test_anthropic_client.py` com: `test_anthropic_client_uses_cache_control` — mockar `AsyncAnthropic.messages.create` via `unittest.mock.AsyncMock`, chamar `generate_briefing_text("system", "user")`, capturar kwargs da chamada, verificar que `kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}`; `test_anthropic_client_captures_cache_tokens` — mockar response com `usage.cache_read_input_tokens=100` e `usage.cache_creation_input_tokens=50`, chamar `generate_briefing_text`, verificar que `result.cache_read_tokens == 100` e `result.cache_write_tokens == 50`

## Tarefa 4: Service de coleta de contexto + testes

- [x] 4.1 Criar `app/services/briefing_context.py` com função async `collect_briefing_context(db, redis, graph, user, event_data, history_window_days) -> dict`. Recebe evento já resolvido (dict) como parâmetro — NÃO busca o evento. Extrair attendees de event_data["attendees"][].emailAddress.address e subject de event_data["subject"]. Implementar coleta de 4 fontes complementares com try/except individual: (1) emails via graph.fetch_with_params /me/messages com $top=10, $orderby=receivedDateTime desc, $filter=receivedDateTime ge {hoje - history_window_days}, filtrar em Python por attendees (from.emailAddress.address ou toRecipients[].emailAddress.address in attendees); (2) onenote via semantic_search(db, user.id, query=subject, limit=5, services=["onenote"]); (3) onedrive via semantic_search(db, user.id, query=subject, limit=5, services=["onedrive"]); (4) memories via recall_memory(db, user.id, query=f"{subject} {' '.join(attendees)}", limit=5). Retornar dict com chaves event (passthrough de event_data), emails_with_attendees, onenote_pages, onedrive_files, memories. Se fonte falhar: logger.warning + lista vazio
- [x] 4.2 Criar `tests/test_edge_cases_briefing.py` com: `test_briefing_context_collects_event` — passar event_data válido a collect_briefing_context, verificar que o dict retornado contém event com os dados passados; `test_briefing_context_filters_emails_by_attendees` — mockar graph retornando 5 emails (3 com attendees em from/to, 2 sem), verificar que resultado contém apenas os 3 relevantes; `test_briefing_context_handles_partial_failure` — mockar 1 das 4 fontes complementares para levantar Exception, verificar que as outras 3 retornam dados e nenhuma exceção propaga
- [x] 4.3 Criar `tests/test_property_briefing_attendees.py` com property test `test_property_briefing_context_attendee_filter`: usar Hypothesis para gerar listas de emails (attendees) e listas de emails simulados com from/to aleatórios; aplicar a lógica de filtro (manter email se from ou algum to está nos attendees); verificar invariante bidirecional — todo email no resultado tem pelo menos 1 attendee em from/to, e todo email fora do resultado não tem nenhum attendee em from/to. Usar `@settings(max_examples=100, deadline=None)`

## Tarefa 5: Service orquestrador + testes

- [x] 5.1 Criar `app/services/briefing.py` com: constante `SYSTEM_PROMPT` (prompt fixo em pt-BR conforme briefing seção 5.7); função async `generate_briefing(db, redis, graph, user, event_id) -> Briefing` que: (1) verifica existência via SELECT Briefing WHERE user_id + event_id — se existe retorna o existente; (2) busca evento via graph.fetch_with_params(user, f"/me/events/{event_id}", params, db, redis) com $select=subject,start,end,location,bodyPreview,attendees — se não encontrado (None ou vazio) levanta HTTPException(404); (3) chama collect_briefing_context(db, redis, graph, user, event_data, settings.BRIEFING_HISTORY_WINDOW_DAYS) passando evento resolvido; (4) renderiza user_content no formato Markdown especificado; (5) chama generate_briefing_text(SYSTEM_PROMPT, user_content); (6) cria Briefing com dados do evento + content + telemetria; (7) db.add + await db.flush() + await db.refresh(briefing); (8) retorna Briefing
- [x] 5.2 Adicionar em `tests/test_edge_cases_briefing.py`: `test_briefing_idempotent` — mockar db.execute para retornar Briefing existente na primeira query, chamar generate_briefing, verificar que generate_briefing_text NÃO foi chamado e retorna o existente; `test_briefing_uses_flush_not_commit` — mockar todas as dependências, chamar generate_briefing para evento novo, verificar que db.flush foi chamado e db.commit NÃO foi chamado

## Tarefa 6: Webhook handler

- [x] 6.1 Modificar `app/services/webhook.py::process_notification`: alterar retorno de `tuple[UUID, ServiceType] | None` para `tuple[UUID, ServiceType, str | None] | None`. Após determinar service_type, extrair event_id: `if service_type == ServiceType.CALENDAR: parts = notification.resource.split("/Events/"); event_id = parts[1] if len(parts) == 2 else None` — para outros serviços, `event_id = None`. Retornar `(user_id, service_type, event_id)`
- [x] 6.2 Modificar `app/routers/webhooks.py::receive_graph_notification`: desempacotar 3-tupla `(user_id, service_type, event_id) = result`. Manter `_reingest_background` inalterado (usa apenas user_id e service_type). Adicionar: `if event_id is not None and service_type == ServiceType.CALENDAR: background_tasks.add_task(_briefing_background, user_id, event_id)`. Criar função `_briefing_background(user_id: uuid.UUID, event_id: str)` que: cria sessão via AsyncSessionLocal(), busca User, chama generate_briefing, faz await db.commit() ao final (com comentário explicando exceção M1), loga exceção sem propagar. Import: generate_briefing de app.services.briefing, User de app.models.user, AsyncSessionLocal de app.database, get_redis de app.database
- [x] 6.3 Criar/adicionar em `tests/test_webhook_service.py`: `test_webhook_extracts_event_id_for_calendar` — mockar notificação com resource="Users/abc-123/Events/event-xyz-456", chamar process_notification, verificar que retorno[2] == "event-xyz-456"; `test_webhook_returns_none_event_id_for_non_calendar` — mockar notificação para mail/onenote/onedrive, verificar que retorno[2] is None
- [x] 6.4 Verificar regressão: rodar suíte existente. Se `_reingest_background` quebrar pela ausência de commit em `ingest_item` (limpeza da Fase 4.5), adicionar `await db.commit()` ao final de `_reingest_background` em `app/routers/webhooks.py` (mesmo padrão de `_briefing_background`)

## Tarefa 7: Router REST + registro

- [x] 7.1 Criar `app/routers/briefings.py` com: `router = APIRouter(prefix="/briefings", tags=["briefings"])`; endpoint `@router.get("/{event_id}", response_model=BriefingResponse)` com função `get_briefing_by_event(event_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> BriefingResponse` que faz SELECT Briefing WHERE user_id == user.id AND event_id == event_id, retorna BriefingResponse se encontrado ou HTTPException(404, detail="Briefing não encontrado") se None
- [x] 7.2 Registrar router em `app/main.py`: `from app.routers.briefings import router as briefings_router` e `app.include_router(briefings_router)` junto aos demais routers
- [x] 7.3 Adicionar em `tests/test_edge_cases_briefing.py`: `test_briefings_endpoint_returns_briefing` — criar Briefing em DB de teste (ou mockar), GET /briefings/{event_id} com auth header, verificar 200 + campos do BriefingResponse; `test_briefings_endpoint_404_when_missing` — GET /briefings/inexistente com auth header, verificar 404

## Tarefa 8: Tool MCP get_briefing

- [x] 8.1 Adicionar em `app/routers/mcp.py`: constante `TOOL_GET_BRIEFING` como MCPTool com name="get_briefing", description descrevendo recuperação de briefing automático para evento de calendar (incluindo exemplo de uso), inputSchema com event_id (string, required, description "ID do evento no Outlook (formato Microsoft Graph)"); handler `handle_get_briefing(arguments, user, db, redis, graph, searxng) -> dict` que faz SELECT Briefing WHERE user_id == user.id AND event_id == arguments["event_id"], retorna dict com id (str), event_id, event_subject, event_start (isoformat), event_end (isoformat), attendees, content, generated_at (isoformat) — ou HTTPException(404) se None
- [x] 8.2 Registrar nas 3 estruturas: adicionar `"get_briefing": handle_get_briefing` ao `TOOLS_REGISTRY`, `"get_briefing": TOOL_GET_BRIEFING` ao `TOOLS_MAP`, e `TOOL_GET_BRIEFING` ao `ALL_TOOLS` — total 9 ferramentas
- [x] 8.3 Atualizar `tests/test_edge_cases_mcp.py`: renomear `test_mcp_list_tools_returns_8_including_semantic_search` para `test_mcp_list_tools_returns_9_including_get_briefing`, atualizar expected count para 9 e adicionar "get_briefing" ao expected set de nomes
- [x] 8.4 Adicionar em `tests/test_edge_cases_mcp.py`: `test_mcp_get_briefing_404_when_missing` — POST /mcp/call com name="get_briefing" e arguments={"event_id": "inexistente"}, verificar resposta JSON-RPC com error (domain error 404)
