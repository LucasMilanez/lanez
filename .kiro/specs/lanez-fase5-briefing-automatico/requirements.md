# Documento de Requisitos — Lanez Fase 5: Briefing Automático de Reunião

## Introdução

A Fase 5 do Lanez implementa geração automática de briefings para reuniões de trabalho. Quando um evento é criado ou alterado no Outlook calendar do usuário (via webhook do Microsoft Graph), o sistema coleta contexto multi-fonte (evento, emails com participantes, OneNote, OneDrive, memórias), envia ao Claude Haiku 4.5 com prompt caching ativo, e persiste o briefing estruturado em Markdown na tabela `briefings`. O briefing é exposto via endpoint REST (`GET /briefings/{event_id}`) para consumo pelo painel React (Fase 6) e via ferramenta MCP `get_briefing` para Claude Desktop. Esta é a primeira fase com integração externa de LLM (Anthropic) — atenção especial a custos (prompt caching), determinismo em testes (sempre mock) e idempotência por `(user_id, event_id)`.

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Servidor_MCP**: Módulo responsável por implementar o protocolo MCP via JSON-RPC 2.0
- **Cliente_MCP**: AI assistant (Claude Desktop, Cursor) que consome as ferramentas MCP
- **Briefing_Idempotente**: Contrato de que para um dado par `(user_id, event_id)`, `generate_briefing` retorna o existente se já houver registro — nunca gera duplicatas. Webhooks podem chegar duplicados; a idempotência garante que apenas 1 row é inserida.
- **Prompt_Caching_Ephemeral**: Mecanismo da Anthropic API onde o system prompt é marcado com `cache_control: {"type": "ephemeral"}`. O cache TTL padrão é 5 minutos — a partir do 2º briefing dentro da janela, o system prompt (~2k tokens) é lido do cache, reduzindo custo em ~90% para input tokens cacheados.
- **Coleta_Multi_Fonte**: Processo de coletar contexto de 5 fontes independentes (evento, emails, OneNote, OneDrive, memórias) para compor o user prompt. Se uma fonte falha, as demais continuam — degradação graciosa.
- **Cache_Read_Tokens**: Tokens do system prompt lidos do cache Anthropic (custo reduzido). Campo `cache_read_input_tokens` na resposta da API.
- **Cache_Write_Tokens**: Tokens do system prompt escritos no cache Anthropic na primeira chamada. Campo `cache_creation_input_tokens` na resposta da API.
- **Background_Task_Isolada**: Função executada via `BackgroundTasks` do FastAPI que cria sua própria sessão de banco (`AsyncSessionLocal()`) fora do dependency `get_db`, e portanto faz commit manual ao final — única exceção justificada à regra M1 da Fase 4.5.

## Requisitos

### Requisito R1: Configuração e Schema Pydantic

**User Story:** Como desenvolvedor, quero que a aplicação exija a chave da Anthropic API e exponha configuração de janela histórica, para que o sistema de briefing funcione corretamente e seja configurável.

#### Critérios de Aceitação

1. THE Sistema SHALL adicionar campo `ANTHROPIC_API_KEY: str` (obrigatório, sem default) à classe `Settings` em `app/config.py` — a aplicação falha na inicialização se não estiver definido em `.env`
2. THE Sistema SHALL adicionar campo `BRIEFING_HISTORY_WINDOW_DAYS: int = 90` à classe `Settings` em `app/config.py` — configurável via variável de ambiente
3. THE Sistema SHALL criar `app/schemas/briefing.py` com classe `BriefingResponse(BaseModel)` contendo campos: id (UUID), event_id (str), event_subject (str), event_start (datetime), event_end (datetime), attendees (list[str]), content (str), generated_at (datetime), model_used (str), input_tokens (int), cache_read_tokens (int), cache_write_tokens (int), output_tokens (int)
4. THE Sistema SHALL adicionar `anthropic>=0.40.0` em `requirements.txt`
5. THE Sistema SHALL adicionar `ANTHROPIC_API_KEY` em `.env.example` com comentário sobre onde obter a chave

### Requisito R2: Modelo SQLAlchemy e Migration

**User Story:** Como desenvolvedor, quero um modelo de dados para armazenar briefings gerados com telemetria de tokens e constraint de unicidade, para que briefings sejam persistidos de forma idempotente e auditável.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/models/briefing.py` com classe `Briefing(Base)` e `__tablename__ = "briefings"` contendo colunas: id (UUID PK default uuid4), user_id (UUID FK users.id ON DELETE CASCADE), event_id (String(255) not null), event_subject (String(500) not null), event_start (DateTime timezone not null), event_end (DateTime timezone not null), attendees (ARRAY(String) not null default list), content (Text not null), model_used (String(64) not null), input_tokens (Integer not null default 0), cache_read_tokens (Integer not null default 0), cache_write_tokens (Integer not null default 0), output_tokens (Integer not null default 0), generated_at (DateTime timezone not null)
2. THE Sistema SHALL definir `UniqueConstraint("user_id", "event_id", name="uq_briefing_user_event")` na tabela briefings — garantindo idempotência
3. THE Sistema SHALL definir `Index("ix_briefings_user_event_start", "user_id", "event_start")` para consultas por janela temporal
4. THE Sistema SHALL importar `Briefing` em `app/models/__init__.py` e adicioná-lo ao `__all__` em ordem alfabética
5. THE Sistema SHALL criar migração `alembic/versions/004_add_briefings.py` com revision `004_briefings`, down_revision `003_memories`, usando `server_default` (não `default`) em todas as colunas com valor padrão
6. THE migração SHALL usar `server_default=sa.text("gen_random_uuid()")` para id, `server_default=sa.text("ARRAY[]::varchar[]")` para attendees, e `server_default=sa.text("0")` para colunas de tokens
7. THE migração SHALL implementar `downgrade()` simétrico que remove índice e tabela

### Requisito R3: Cliente Anthropic

**User Story:** Como sistema, quero um cliente encapsulado para o Claude Haiku 4.5 com prompt caching ativo e captura de telemetria de tokens, para que a geração de briefings seja eficiente em custo e monitorável.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/services/anthropic_client.py` com função `generate_briefing_text(system_prompt: str, user_content: str) -> BriefingResult`
2. THE cliente SHALL usar modelo `claude-haiku-4-5-20251001` com `max_tokens=1500`
3. THE cliente SHALL marcar o system prompt com `cache_control: {"type": "ephemeral"}` na estrutura `system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]`
4. THE cliente SHALL capturar `response.usage.cache_read_input_tokens` (default 0 se ausente) e `response.usage.cache_creation_input_tokens` (default 0 se ausente) no `BriefingResult`
5. THE cliente SHALL expor `BriefingResult` com campos: content (str), model (str), input_tokens (int), cache_read_tokens (int), cache_write_tokens (int), output_tokens (int)
6. THE cliente SHALL usar singleton `AsyncAnthropic` inicializado com `settings.ANTHROPIC_API_KEY`
7. THE Sistema SHALL adicionar `anthropic>=0.40.0` em `requirements.txt`

### Requisito R4: Coleta de Contexto Multi-Fonte

**User Story:** Como sistema, quero coletar contexto de 5 fontes independentes (evento, emails com participantes, OneNote, OneDrive, memórias) para compor o prompt do briefing, degradando graciosamente se alguma fonte falhar.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/services/briefing_context.py` com função `collect_briefing_context(db, redis, graph, user, event_data, history_window_days) -> dict` — recebe o evento já resolvido (dict), não busca o evento
2. THE função SHALL extrair lista de emails dos `event_data["attendees"][].emailAddress.address`
3. THE função SHALL buscar até 10 emails recentes (últimos `history_window_days` dias) via Graph API e filtrar em Python mantendo apenas emails onde `from.emailAddress.address` ou algum `toRecipients[].emailAddress.address` está na lista de attendees do evento
4. THE função SHALL buscar até 5 páginas OneNote via `semantic_search(db, user.id, query=event_subject, limit=5, services=["onenote"])`
5. THE função SHALL buscar até 5 arquivos OneDrive via `semantic_search(db, user.id, query=event_subject, limit=5, services=["onedrive"])`
6. THE função SHALL buscar até 5 memórias via `recall_memory(db, user.id, query=f"{event_subject} {' '.join(attendees)}", limit=5)`
7. IF qualquer das 4 fontes complementares falhar (exceção), THEN THE função SHALL logar warning e retornar lista vazia para essa fonte — nunca propagar exceção. O briefing deve ser gerado mesmo com contexto parcial
8. THE função SHALL retornar dict com chaves: event (passthrough do event_data recebido), emails_with_attendees, onenote_pages, onedrive_files, memories

### Requisito R5: Orquestrador generate_briefing

**User Story:** Como sistema, quero um orquestrador que coordene coleta de contexto, chamada ao LLM e persistência do briefing de forma idempotente, para que webhooks duplicados não gerem briefings duplicados.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/services/briefing.py` com constante `SYSTEM_PROMPT` (prompt fixo em pt-BR) e função `generate_briefing(db, redis, graph, user, event_id) -> Briefing`
2. WHEN `generate_briefing` é chamado e já existe Briefing para `(user_id, event_id)`, THEN THE função SHALL retornar o existente sem chamar a Anthropic API — idempotência
3. THE função SHALL buscar o evento via Graph API como pré-condição obrigatória ANTES de chamar `collect_briefing_context` — se o evento não for encontrado (Graph 404 ou resposta vazia), levantar `HTTPException(404)` imediatamente
4. THE função SHALL passar o evento resolvido a `collect_briefing_context` (que coleta apenas as 4 fontes complementares) e renderizar `user_content` no formato Markdown especificado no design
5. THE função SHALL chamar `generate_briefing_text(SYSTEM_PROMPT, user_content)` e criar instância de `Briefing` com dados do evento + content + telemetria de tokens
6. THE função SHALL usar `db.add(briefing); await db.flush(); await db.refresh(briefing)` — NÃO `commit()` (regra M1 da Fase 4.5 — commit é responsabilidade do boundary)

### Requisito R6: Webhook Handler para Calendar

**User Story:** Como sistema, quero que notificações de webhook para eventos de calendar disparem a geração de briefing em background, para que briefings sejam gerados automaticamente quando reuniões são criadas ou alteradas.

#### Critérios de Aceitação

1. THE Sistema SHALL modificar `process_notification` em `app/services/webhook.py` para retornar `tuple[UUID, ServiceType, str | None] | None` — terceiro elemento é `event_id` extraído do `notification.resource` quando serviço é CALENDAR
2. THE extração SHALL usar `notification.resource.split("/Events/")` — se `len(parts) == 2`, `event_id = parts[1]`; caso contrário `event_id = None`
3. FOR serviços que não são CALENDAR, THE terceiro elemento SHALL ser `None`
4. THE Sistema SHALL modificar `receive_graph_notification` em `app/routers/webhooks.py` para desempacotar a 3-tupla e, quando `event_id is not None and service_type == ServiceType.CALENDAR`, adicionar `background_tasks.add_task(_briefing_background, user_id, event_id)`
5. THE função `_briefing_background` SHALL criar sessão própria via `AsyncSessionLocal()`, buscar User, chamar `generate_briefing`, e fazer `await db.commit()` ao final — única exceção justificada à regra M1 (sessão fora do `get_db`)
6. IF qualquer erro ocorrer em `_briefing_background`, THEN THE função SHALL logar exceção sem propagar — webhook já respondeu 202
7. THE modificação SHALL manter compatibilidade com `_reingest_background` que continua usando apenas `(user_id, service_type)`

### Requisito R7: Endpoint REST

**User Story:** Como cliente (futuro painel React da Fase 6), quero um endpoint REST para consultar o briefing de um evento específico, para exibir o briefing ao usuário antes da reunião.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/routers/briefings.py` com router `APIRouter(prefix="/briefings", tags=["briefings"])`
2. THE router SHALL expor `GET /{event_id}` com `response_model=BriefingResponse` que retorna o briefing do usuário autenticado para o evento especificado
3. IF não houver briefing para o `(user_id, event_id)`, THEN THE endpoint SHALL retornar HTTP 404 com detail "Briefing não encontrado"
4. THE endpoint SHALL usar `Depends(get_current_user)` para autenticação e `Depends(get_db)` para sessão
5. THE Sistema SHALL registrar o router em `app/main.py` junto aos demais routers

### Requisito R8: Ferramenta MCP get_briefing

**User Story:** Como cliente MCP (Claude Desktop), quero uma ferramenta para recuperar o briefing de uma reunião, para que o AI assistant possa preparar o usuário antes de um meeting.

#### Critérios de Aceitação

1. THE Servidor_MCP SHALL expor uma 9ª ferramenta chamada `get_briefing` com description fixa descrevendo recuperação de briefing automático para evento de calendar
2. THE ferramenta SHALL aceitar parâmetro obrigatório `event_id` (string) — ID do evento no formato Microsoft Graph
3. WHEN a ferramenta é chamada, THE handler SHALL consultar `Briefing` por `(user_id, event_id)` e retornar dict com id, event_id, event_subject, event_start, event_end, attendees, content, generated_at
4. IF não houver briefing para o evento, THEN THE handler SHALL levantar `HTTPException(404)` que o dispatcher converte em `jsonrpc_domain_error`
5. THE ferramenta SHALL ser adicionada ao `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS` — total passa de 8 para 9 ferramentas
6. WHEN GET /mcp é chamado, THE Servidor_MCP SHALL retornar lista com 9 ferramentas incluindo `get_briefing`
7. THE Sistema SHALL atualizar teste existente `test_mcp_list_tools_returns_8_including_semantic_search` para verificar 9 ferramentas com `get_briefing` no set esperado
