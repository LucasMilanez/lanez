# Tarefas de Implementação — Lanez Fase 2: MCP Server

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

## Tarefa 1: Configuração e Infraestrutura

- [x] 1.1 Adicionar variável `SEARXNG_URL: str = "http://localhost:8080"` à classe Settings em `app/config.py`
- [x] 1.2 Adicionar seção SearXNG ao `.env.example` com a variável `SEARXNG_URL=http://localhost:8080` e comentário descritivo
- [x] 1.3 Adicionar serviço `searxng` ao `docker-compose.yml` com imagem searxng/searxng:latest, porta 8080:8080, environment SEARXNG_SECRET=lanez-searxng-secret e restart: unless-stopped

## Tarefa 2: Serviço SearXNG

- [x] 2.1 Criar `app/services/searxng.py` com classe SearXNGService: construtor aceitando httpx.AsyncClient opcional (timeout 10s), método async `close()` que fecha o client, método async `search(query, limit=10)` que consulta GET `{SEARXNG_URL}/search` com params `q=query, format=json`, retorna lista de `{title, url, content}` limitada a `limit` resultados, trata erros HTTP retornando lista vazia e logando o erro

## Tarefa 3: Extensão do GraphService (fetch_with_params)

- [x] 3.1 Modificar método `_request_graph()` em `app/services/graph.py` para aceitar parâmetro opcional `params: dict[str, str] | None = None` e passá-lo ao `self._client.get(url, headers=headers, params=params)`
- [x] 3.2 Adicionar método público `fetch_with_params(self, user, endpoint, params, db, redis)` ao GraphService em `app/services/graph.py`: verificar rate limit via `_check_rate_limit`, montar URL com `BASE_URL + endpoint`, fazer requisição via `_request_graph` com params, tratar 401 (refresh + retry 1x), propagar outros erros como HTTPException, retornar `resp.json()`. NÃO usar cache (nem Redis nem GraphCache)

## Tarefa 4: Router MCP — Estrutura Base

- [x] 4.1 Criar `app/routers/mcp.py` com APIRouter(prefix="/mcp", tags=["mcp"]), imports necessários (FastAPI, dependencies, services), definição das 5 ferramentas como constantes MCPTool com name, description (string fixa) e inputSchema, registro TOOLS_REGISTRY mapeando nome → handler, e TOOLS_MAP mapeando nome → MCPTool (para acesso ao inputSchema na validação de parâmetros obrigatórios)
- [x] 4.2 Implementar funções auxiliares de formatação JSON-RPC com request_id tipado como `str | int | None`: `jsonrpc_success(request_id, data)` retornando result com isError=false e dados serializados, `jsonrpc_error(request_id, code, message)` retornando campo error com código JSON-RPC, `jsonrpc_domain_error(request_id, message)` retornando result com isError=true
- [x] 4.3 Implementar dependency functions `get_graph_service()` e `get_searxng_service()` como async generators que criam e fecham os serviços (mesmo padrão da Fase 1)

## Tarefa 5: Router MCP — Endpoints

- [x] 5.1 Implementar endpoint GET /mcp (list_tools): protegido por Depends(get_current_user), retorna resposta JSON-RPC 2.0 com formato `{"jsonrpc": "2.0", "result": {"tools": [...]}}` contendo a lista das 5 ferramentas (name, description, inputSchema)
- [x] 5.2 Implementar endpoint POST /mcp/call (call_tool): protegido por Depends(get_current_user), recebe MCPCallRequest (jsonrpc, id: str | int | None, method, params), valida method=="tools/call" (senão -32601), verifica ferramenta existe no TOOLS_REGISTRY (senão -32601), valida parâmetros obrigatórios contra inputSchema["required"] da ferramenta (senão -32602 com mensagem "Parâmetro obrigatório ausente: '{param}'"), despacha para handler, captura HTTPException como domain_error e Exception como domain_error, retorna JSON-RPC success/error/domain_error conforme o caso
- [x] 5.3 Implementar endpoint GET /mcp/sse (mcp_sse): protegido por Depends(get_current_user), retorna StreamingResponse com media_type="text/event-stream", envia evento hello com capabilities, envia ping a cada 30s via asyncio.sleep, encerra quando cliente desconecta, inclui headers Cache-Control: no-cache e X-Accel-Buffering: no

## Tarefa 6: Handlers das Ferramentas MCP

- [x] 6.1 Implementar handler `handle_get_calendar_events(arguments, user, db, redis, graph, searxng)`: validar parâmetros start e end (obrigatórios, formato YYYY-MM-DD), montar params com $filter de datas, $orderby, $select e $top=50, chamar graph.fetch_with_params com endpoint="/me/events", retornar dados
- [x] 6.2 Implementar handler `handle_search_emails(arguments, user, db, redis, graph, searxng)`: validar parâmetro query (obrigatório), extrair limit (padrão 10, máximo 50), montar params com $search, $top e $select, chamar graph.fetch_with_params com endpoint="/me/messages", retornar dados
- [x] 6.3 Implementar handler `handle_get_onenote_pages(arguments, user, db, redis, graph, searxng)`: extrair parâmetros opcionais notebook e query, montar params com $top=50 e $select, adicionar $filter com contains(title, query) se query fornecido, chamar graph.fetch_with_params com endpoint="/me/onenote/pages", retornar dados
- [x] 6.4 Implementar handler `handle_search_files(arguments, user, db, redis, graph, searxng)`: validar parâmetro query (obrigatório), montar params com $top=25 e $select, chamar graph.fetch_with_params com endpoint="/me/drive/root/search(q='{query}')", retornar dados
- [x] 6.5 Implementar handler `handle_web_search(arguments, user, db, redis, graph, searxng)`: validar parâmetro query (obrigatório), chamar searxng.search(query), retornar resultados

## Tarefa 7: Integração na Aplicação Principal

- [x] 7.1 Atualizar `app/main.py` para importar o router mcp (`from app.routers import auth, graph, mcp, webhooks`) e registrá-lo via `app.include_router(mcp.router)`

## Tarefa 8: Testes de Propriedade

- [x] 8.1 Escrever property-based test para formato de respostas JSON-RPC: gerar nomes de ferramentas, IDs aleatórios (str, int, None) e argumentos aleatórios, verificar que toda resposta contém `jsonrpc: "2.0"` e `id` correspondente, e contém exatamente um dos campos `result` ou `error` (Propriedade 1)
- [x] 8.2 Escrever property-based test para imutabilidade de descriptions: chamar list_tools múltiplas vezes, verificar que descriptions são sempre idênticas às constantes definidas no código (Propriedade 2)
- [x] 8.3 Escrever property-based test para separação de erros protocolo vs domínio: gerar cenários de erro (nomes inválidos → -32601 no campo error; parâmetros obrigatórios ausentes → -32602 no campo error; exceções simuladas → isError true no result), verificar que nunca há ambos os campos simultaneamente (Propriedade 3)
- [x] 8.4 Escrever property-based test para fetch_with_params sem cache: mock do CacheService, chamar fetch_with_params com parâmetros aleatórios, verificar que cache.get() e cache.set() nunca são invocados (Propriedade 4)
- [x] 8.5 Escrever property-based test para rate limit compartilhado: verificar que fetch_data e fetch_with_params usam a mesma chave Redis "lanez:ratelimit:{user_id}" (Propriedade 5)

## Tarefa 9: Testes de Casos de Borda

- [x] 9.1 Escrever teste para ferramenta inexistente: POST /mcp/call com name="nao_existe", verificar resposta JSON-RPC error com código -32601 (Caso de Borda 1)
- [x] 9.2 Escrever teste para argumentos ausentes: chamar get_calendar_events sem start/end, verificar resposta JSON-RPC error com código -32602 (Caso de Borda 2)
- [x] 9.3 Escrever teste para SearXNG indisponível: mock httpx retornando erro/timeout, chamar web_search, verificar domain error com isError=true (Caso de Borda 3)
- [x] 9.4 Escrever teste para token expirado durante chamada MCP: mock Graph API retornando 401, verificar que fetch_with_params tenta refresh e retry (Caso de Borda 4)
- [x] 9.5 Escrever teste para rate limit excedido via MCP: simular rate limit excedido, chamar ferramenta, verificar domain error com isError=true (Caso de Borda 5)
- [x] 9.6 Escrever teste para desconexão SSE: simular desconexão do cliente, verificar que generator encerra graciosamente (Caso de Borda 6)
- [x] 9.7 Escrever teste para method diferente de tools/call: POST /mcp/call com method="tools/list", verificar resposta JSON-RPC error com código -32601 (Caso de Borda 7)
- [x] 9.8 Escrever teste para JWT ausente nos endpoints MCP: enviar GET /mcp, POST /mcp/call e GET /mcp/sse sem Authorization header, verificar HTTP 401 em todos (Caso de Borda 8)
