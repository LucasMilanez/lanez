# Documento de Requisitos — Lanez Fase 2: MCP Server

## Introdução

A Fase 2 do Lanez implementa o servidor MCP (Model Context Protocol) que expõe os dados do Microsoft 365 como ferramentas consumíveis por AI assistants (Claude Desktop, Cursor). O protocolo é JSON-RPC 2.0 sobre HTTP/SSE. São expostas 5 ferramentas: consulta de eventos do calendário, busca de emails, listagem de páginas do OneNote, busca de arquivos no OneDrive e busca web via SearXNG. Esta fase reutiliza toda a infraestrutura da Fase 1 (autenticação JWT, GraphService, cache Redis, PostgreSQL) e não adiciona novos modelos de dados.

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Servidor_MCP**: Módulo responsável por implementar o protocolo MCP via JSON-RPC 2.0
- **Cliente_MCP**: AI assistant (Claude Desktop, Cursor) que consome as ferramentas MCP
- **Cliente_Graph**: Módulo GraphService responsável por consumir a Microsoft Graph API
- **Cliente_SearXNG**: Módulo SearXNGService responsável por consultar o motor de busca SearXNG
- **JSON-RPC**: Protocolo de chamada remota usando JSON, versão 2.0
- **SSE**: Server-Sent Events — protocolo de streaming unidirecional do servidor para o cliente
- **Ferramenta_MCP**: Função exposta pelo Servidor_MCP que pode ser invocada por um Cliente_MCP
- **Erro_Protocolo**: Erro no nível do protocolo JSON-RPC (JSON inválido, método inexistente)
- **Erro_Domínio**: Erro no nível da lógica de negócio (Graph API falhou, rate limit excedido)
- **Tool_Poisoning**: Ataque onde descriptions de ferramentas são manipuladas para induzir comportamento malicioso no AI assistant
- **SearXNG**: Motor de busca web self-hosted, open source
- **Graph_API**: Microsoft Graph API v1.0

## Requisitos

### Requisito 1: Listagem de Ferramentas MCP

**User Story:** Como cliente MCP, quero listar as ferramentas disponíveis no servidor, para que eu saiba quais operações posso executar e quais parâmetros cada uma aceita.

#### Critérios de Aceitação

1. WHEN uma requisição GET /mcp é recebida com um JWT válido, THE Servidor_MCP SHALL retornar uma resposta JSON-RPC 2.0 com formato `{"jsonrpc": "2.0", "result": {"tools": [...]}}` contendo a lista completa das 5 ferramentas disponíveis com nome, description e inputSchema
2. THE Servidor_MCP SHALL incluir na lista as ferramentas: get_calendar_events, search_emails, get_onenote_pages, search_files e web_search
3. FOR ALL ferramentas listadas, THE Servidor_MCP SHALL retornar descriptions que são strings fixas definidas no código-fonte, nunca geradas dinamicamente a partir de dados externos
4. IF o JWT for inválido, expirado ou ausente, THEN THE Servidor_MCP SHALL retornar status HTTP 401

### Requisito 2: Execução de Ferramentas MCP via JSON-RPC 2.0

**User Story:** Como cliente MCP, quero executar ferramentas via protocolo JSON-RPC 2.0, para que eu possa acessar dados do Microsoft 365 e busca web de forma padronizada.

#### Critérios de Aceitação

1. WHEN uma requisição POST /mcp/call é recebida com JSON-RPC válido e JWT válido, THE Servidor_MCP SHALL despachar a chamada para o handler da ferramenta correspondente
2. WHEN a execução da ferramenta é bem-sucedida, THE Servidor_MCP SHALL retornar uma resposta JSON-RPC 2.0 com campo `result` contendo `content` (lista com tipo "text" e dados serializados) e `isError: false`
3. THE Servidor_MCP SHALL incluir `jsonrpc: "2.0"` e o `id` correspondente à requisição em toda resposta. O campo `id` SHALL aceitar valores do tipo string, inteiro ou null, conforme a especificação JSON-RPC 2.0
4. WHEN a requisição contém `method` diferente de "tools/call", THE Servidor_MCP SHALL retornar erro JSON-RPC com código -32601
5. IF o JWT for inválido, expirado ou ausente, THEN THE Servidor_MCP SHALL retornar status HTTP 401

### Requisito 3: Tratamento de Erros JSON-RPC

**User Story:** Como cliente MCP, quero que erros sejam reportados de forma padronizada, para que eu possa distinguir entre erros de protocolo e erros de domínio e tomar a ação correta.

#### Critérios de Aceitação

1. IF a ferramenta solicitada não existir no registro de ferramentas, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC com código -32601 (Method Not Found) no campo `error`
2. IF os argumentos da ferramenta forem inválidos ou ausentes conforme o campo `required` do `inputSchema` da ferramenta, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC com código -32602 (Invalid Params) no campo `error` ANTES de despachar para o handler da ferramenta
3. IF a execução da ferramenta falhar por erro de domínio (Graph API, rate limit, SearXNG), THEN THE Servidor_MCP SHALL retornar resposta com campo `result` contendo `isError: true` e mensagem descritiva
4. FOR ALL respostas do Servidor_MCP, THE resposta SHALL conter exatamente um dos campos `result` ou `error`, nunca ambos simultaneamente
5. THE Servidor_MCP SHALL usar os códigos de erro JSON-RPC padrão: -32700 (Parse Error), -32600 (Invalid Request), -32601 (Method Not Found), -32602 (Invalid Params), -32603 (Internal Error)

### Requisito 4: Conexão SSE Keepalive

**User Story:** Como cliente MCP, quero manter uma conexão SSE com o servidor, para que eu possa receber notificações e manter a sessão ativa.

#### Critérios de Aceitação

1. WHEN uma requisição GET /mcp/sse é recebida com JWT válido, THE Servidor_MCP SHALL iniciar uma conexão SSE com media type "text/event-stream"
2. WHEN a conexão SSE é estabelecida, THE Servidor_MCP SHALL enviar imediatamente um evento `{"type": "hello", "capabilities": {"tools": {}}}`
3. WHILE a conexão SSE estiver ativa, THE Servidor_MCP SHALL enviar um evento `{"type": "ping"}` a cada 30 segundos
4. WHEN o cliente desconectar, THE Servidor_MCP SHALL encerrar o generator de eventos graciosamente
5. IF o JWT for inválido, expirado ou ausente, THEN THE Servidor_MCP SHALL retornar status HTTP 401
6. THE Servidor_MCP SHALL incluir os headers `Cache-Control: no-cache` e `X-Accel-Buffering: no` na resposta SSE

### Requisito 5: Ferramenta get_calendar_events

**User Story:** Como usuário via AI assistant, quero buscar eventos do meu calendário por intervalo de datas, para que o assistant possa me informar sobre minha agenda.

#### Critérios de Aceitação

1. WHEN a ferramenta get_calendar_events é chamada com parâmetros `start` e `end` (formato YYYY-MM-DD), THE Cliente_Graph SHALL consultar o endpoint /me/events da Graph_API com filtro de datas usando `fetch_with_params`
2. THE Cliente_Graph SHALL selecionar os campos: subject, start, end, location, organizer, attendees
3. THE Cliente_Graph SHALL ordenar os resultados por start/dateTime ascendente
4. THE Cliente_Graph SHALL limitar os resultados a no máximo 50 eventos
5. IF os parâmetros `start` ou `end` estiverem ausentes, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602

### Requisito 6: Ferramenta search_emails

**User Story:** Como usuário via AI assistant, quero buscar emails por texto livre, para que o assistant possa encontrar mensagens relevantes.

#### Critérios de Aceitação

1. WHEN a ferramenta search_emails é chamada com parâmetro `query`, THE Cliente_Graph SHALL consultar o endpoint /me/messages da Graph_API com `$search` usando `fetch_with_params`
2. THE Cliente_Graph SHALL selecionar os campos: subject, from, receivedDateTime, bodyPreview, isRead
3. THE Cliente_Graph SHALL limitar os resultados a `min(limit, 50)` onde limit tem valor padrão 10
4. IF o parâmetro `query` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602

### Requisito 7: Ferramenta get_onenote_pages

**User Story:** Como usuário via AI assistant, quero listar páginas do OneNote opcionalmente filtrando por título, para que o assistant possa acessar minhas anotações.

#### Critérios de Aceitação

1. WHEN a ferramenta get_onenote_pages é chamada, THE Cliente_Graph SHALL consultar o endpoint /me/onenote/pages da Graph_API usando `fetch_with_params`
2. THE Cliente_Graph SHALL selecionar os campos: title, createdDateTime, lastModifiedDateTime, parentNotebook
3. IF o parâmetro `query` for fornecido, THEN THE Cliente_Graph SHALL adicionar filtro `contains(title, query)` à requisição
4. THE Cliente_Graph SHALL limitar os resultados a no máximo 50 páginas
5. THE ferramenta get_onenote_pages SHALL aceitar todos os parâmetros como opcionais (nenhum obrigatório)

### Requisito 8: Ferramenta search_files

**User Story:** Como usuário via AI assistant, quero buscar arquivos no OneDrive por nome ou conteúdo, para que o assistant possa encontrar meus documentos.

#### Critérios de Aceitação

1. WHEN a ferramenta search_files é chamada com parâmetro `query`, THE Cliente_Graph SHALL consultar o endpoint /me/drive/root/search(q='{query}') da Graph_API usando `fetch_with_params`
2. THE Cliente_Graph SHALL selecionar os campos: name, size, lastModifiedDateTime, webUrl, file, folder
3. THE Cliente_Graph SHALL limitar os resultados a no máximo 25 arquivos
4. IF o parâmetro `query` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602

### Requisito 9: Ferramenta web_search

**User Story:** Como usuário via AI assistant, quero buscar informações na web, para que o assistant possa complementar dados do Microsoft 365 com informações públicas.

#### Critérios de Aceitação

1. WHEN a ferramenta web_search é chamada com parâmetro `query`, THE Cliente_SearXNG SHALL consultar o SearXNG via GET /search com formato JSON
2. THE Cliente_SearXNG SHALL retornar uma lista de resultados contendo title, url e content
3. THE Cliente_SearXNG SHALL limitar os resultados a no máximo 10 itens
4. IF o SearXNG retornar erro HTTP ou timeout, THEN THE Cliente_SearXNG SHALL retornar lista vazia e registrar o erro em log — o Servidor_MCP retornará sucesso com lista vazia (isError: false)
5. IF o parâmetro `query` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602

### Requisito 10: Consulta Parametrizada à Graph API (fetch_with_params)

**User Story:** Como desenvolvedor, quero um método no GraphService que aceite parâmetros de query customizados, para que as ferramentas MCP possam fazer consultas filtradas à Graph API.

#### Critérios de Aceitação

1. THE Cliente_Graph SHALL expor um método `fetch_with_params` que aceita endpoint, parâmetros de query, User, AsyncSession e Redis
2. THE método `fetch_with_params` SHALL verificar o rate limit do usuário antes de fazer a requisição à Graph_API
3. IF a Graph_API retornar status HTTP 401, THEN THE método `fetch_with_params` SHALL tentar renovar o access_token e repetir a requisição uma vez
4. THE método `fetch_with_params` SHALL NOT armazenar resultados no cache Redis nem no GraphCache
5. THE método `_request_graph` existente SHALL aceitar um parâmetro opcional `params` para passar query parameters à Graph_API

### Requisito 11: Serviço SearXNG

**User Story:** Como desenvolvedor, quero um cliente HTTP para o SearXNG, para que a ferramenta web_search possa consultar o motor de busca self-hosted.

#### Critérios de Aceitação

1. THE Sistema SHALL fornecer uma classe SearXNGService com método `search(query, limit)` que consulta o SearXNG
2. THE Cliente_SearXNG SHALL usar timeout de 10 segundos para requisições ao SearXNG
3. IF o SearXNG retornar erro HTTP, THEN THE Cliente_SearXNG SHALL retornar lista vazia e registrar o erro em log
4. THE Cliente_SearXNG SHALL ler a URL do SearXNG da variável de configuração `SEARXNG_URL`
5. THE Cliente_SearXNG SHALL seguir o padrão de dependency injection com async generator (mesmo padrão do GraphService)

### Requisito 12: Configuração SearXNG

**User Story:** Como desenvolvedor, quero que a URL do SearXNG seja configurável via variável de ambiente, para que o sistema funcione em diferentes ambientes.

#### Critérios de Aceitação

1. THE Sistema SHALL adicionar a variável `SEARXNG_URL` ao módulo config.py com valor padrão "http://localhost:8080"
2. THE Sistema SHALL documentar a variável `SEARXNG_URL` no arquivo .env.example
3. THE Sistema SHALL adicionar o serviço SearXNG ao docker-compose.yml com imagem searxng/searxng:latest na porta 8080

### Requisito 13: Registro do Router MCP

**User Story:** Como desenvolvedor, quero que o router MCP seja registrado na aplicação FastAPI, para que os endpoints MCP estejam acessíveis.

#### Critérios de Aceitação

1. THE Sistema SHALL registrar o router MCP no app FastAPI via `app.include_router(mcp.router)`
2. THE router MCP SHALL usar o prefixo `/mcp` para todos os seus endpoints
3. THE router MCP SHALL usar a tag "mcp" para documentação OpenAPI

### Requisito 14: Segurança dos Endpoints MCP

**User Story:** Como operador do sistema, quero que todos os endpoints MCP sejam protegidos por autenticação JWT, para que apenas usuários autenticados possam acessar as ferramentas.

#### Critérios de Aceitação

1. FOR ALL endpoints do router MCP (GET /mcp, POST /mcp/call, GET /mcp/sse), THE Sistema SHALL exigir um JWT válido via a dependency `get_current_user`
2. THE Servidor_MCP SHALL NOT aceitar parâmetros `endpoint` ou `url` livres nas ferramentas (prevenção de exfiltração de dados)
3. FOR ALL operações de log do Servidor_MCP, THE Sistema SHALL omitir valores de tokens, substituindo-os por `[token=REDACTED]`
4. THE Servidor_MCP SHALL usar descriptions de ferramentas como strings fixas no código-fonte, nunca geradas dinamicamente (proteção contra tool poisoning)
