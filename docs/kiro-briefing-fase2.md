# Lanez — Briefing Fase 2 para KIRO

## O que é o Lanez

MCP Server pessoal que conecta AI assistants (Claude Desktop, Cursor) aos dados do Microsoft 365 do usuário — emails, calendário, OneNote, OneDrive — com busca semântica, memória persistente e briefing automático de reuniões.

**Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source a ~$1-2/mês.**

---

## O que a Fase 1 entregou (já existe — não reescrever)

```
app/
├── main.py              ← FastAPI + lifespan (Redis, DB, webhook renewal loop)
├── config.py            ← Settings (Pydantic BaseSettings)
├── database.py          ← AsyncSession, get_db(), get_redis()
├── dependencies.py      ← get_current_user() (valida JWT)
├── models/
│   ├── user.py          ← User com microsoft_access_token, microsoft_refresh_token (Fernet encrypted)
│   ├── cache.py         ← GraphCache
│   └── webhook.py       ← WebhookSubscription
├── routers/
│   ├── auth.py          ← OAuth flow completo (GET /auth/microsoft, /auth/callback, POST /auth/refresh)
│   ├── graph.py         ← GET /graph/{service} (calendar, mail, onenote, onedrive)
│   └── webhooks.py      ← POST /webhooks/graph, GET /webhooks/subscriptions
├── schemas/
│   ├── auth.py
│   └── graph.py         ← ServiceType enum, GraphDataResponse, WebhookNotification
└── services/
    ├── cache.py         ← CacheService (Redis get/set/invalidate)
    ├── graph.py         ← GraphService.fetch_data() — cache + rate limit + backoff + token refresh
    └── webhook.py       ← WebhookService — create/renew/process subscriptions
```

**Atributos corretos do modelo User** (atenção — são propriedades com decrypt automático):
- `user.microsoft_access_token` — NÃO `user.access_token`
- `user.microsoft_refresh_token` — NÃO `user.refresh_token`

**Variáveis já em `app/config.py`:**
```
MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID
MICROSOFT_REDIRECT_URI, WEBHOOK_NOTIFICATION_URL
SECRET_KEY, WEBHOOK_CLIENT_STATE
DATABASE_URL, REDIS_URL, CORS_ORIGINS
```

---

## Fase 2 — MCP Server (escopo desta entrega)

### Objetivo

Servidor MCP funcional consumível pelo Claude Desktop e qualquer cliente MCP. Expõe os dados do Microsoft 365 como ferramentas via protocolo JSON-RPC 2.0 sobre HTTP/SSE.

---

## O que implementar

### 1. Adicionar `fetch_with_params()` ao `GraphService` (`app/services/graph.py`)

O método existente `fetch_data()` busca o endpoint padrão por serviço sem filtros. Para as ferramentas MCP (busca por data, query de texto), precisamos de um método que aceite parâmetros de query customizados.

**Modificações em `app/services/graph.py`:**

a) Adicionar parâmetro opcional `params` ao método `_request_graph()`:
```python
async def _request_graph(
    self,
    url: str,
    access_token: str,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(1, _BACKOFF_MAX_RETRIES + 1):
        resp = await self._client.get(url, headers=headers, params=params)
        # ... resto do método sem alteração
```

b) Adicionar método público `fetch_with_params()`:
```python
async def fetch_with_params(
    self,
    user: User,
    endpoint: str,
    params: dict[str, str],
    db: AsyncSession,
    redis: aioredis.Redis,
) -> dict:
    """Consulta endpoint Graph API com parâmetros customizados. Sem cache."""
    await self._check_rate_limit(redis, user.id)

    url = f"{self.BASE_URL}{endpoint}"
    access_token = user.microsoft_access_token

    resp = await self._request_graph(url, access_token, params=params)

    if resp.status_code == 401:
        new_token = await self._refresh_access_token(user, db)
        resp = await self._request_graph(url, new_token, params=params)
        if resp.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Token inválido. Re-autentique em /auth/microsoft.",
            )

    if resp.status_code != 200:
        logger.error(
            "Graph API erro %d endpoint=%s [token=REDACTED]",
            resp.status_code,
            endpoint,
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro na Graph API: {resp.status_code}",
        )

    return resp.json()
```

---

### 2. Criar `app/services/searxng.py`

Cliente HTTP para o SearXNG (busca web self-hosted).

```python
"""Cliente para o SearXNG — busca web self-hosted."""

from __future__ import annotations

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)
_TIMEOUT = 10.0


class SearXNGService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Busca na web e retorna lista de {title, url, content}."""
        params = {"q": query, "format": "json"}
        try:
            resp = await self._client.get(
                f"{settings.SEARXNG_URL}/search", params=params
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])[:limit]
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                for r in results
            ]
        except httpx.HTTPError as exc:
            logger.error("Erro SearXNG: %s", exc)
            return []
```

---

### 3. Criar `app/routers/mcp.py`

Router principal do MCP Server. Implementa JSON-RPC 2.0 sobre HTTP com SSE.

**Endpoints:**
- `GET /mcp` — lista ferramentas (requer JWT)
- `POST /mcp/call` — executa ferramenta (requer JWT)
- `GET /mcp/sse` — conexão SSE keepalive (requer JWT)

**5 ferramentas a expor:**

| Nome | Parâmetros | Fonte |
|---|---|---|
| `get_calendar_events` | `start: str (YYYY-MM-DD)`, `end: str (YYYY-MM-DD)` | Graph API `/me/events` com `$filter` de datas |
| `search_emails` | `query: str`, `limit: int = 10` | Graph API `/me/messages` com `$search` |
| `get_onenote_pages` | `notebook: str?`, `query: str?` | Graph API `/me/onenote/pages` com `$filter` por título |
| `search_files` | `query: str` | Graph API `/me/drive/root/search(q='{query}')` |
| `web_search` | `query: str` | SearXNG `/search?format=json` |

**Parâmetros Graph API por ferramenta:**

`get_calendar_events`:
```python
params = {
    "$filter": f"start/dateTime ge '{start}T00:00:00Z' and end/dateTime le '{end}T23:59:59Z'",
    "$orderby": "start/dateTime",
    "$select": "subject,start,end,location,organizer,attendees",
    "$top": "50",
}
endpoint = "/me/events"
```

`search_emails`:
```python
params = {
    "$search": f'"{query}"',
    "$top": str(min(limit, 50)),
    "$select": "subject,from,receivedDateTime,bodyPreview,isRead",
}
endpoint = "/me/messages"
```

`get_onenote_pages`:
```python
params = {
    "$top": "50",
    "$select": "title,createdDateTime,lastModifiedDateTime,parentNotebook",
}
if query:
    params["$filter"] = f"contains(title, '{query}')"
endpoint = "/me/onenote/pages"
```

`search_files`:
```python
params = {
    "$top": "25",
    "$select": "name,size,lastModifiedDateTime,webUrl,file,folder",
}
endpoint = f"/me/drive/root/search(q='{query}')"
```

**Estrutura JSON-RPC das respostas:**

Sucesso:
```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "result": {
    "content": [{"type": "text", "text": "<json.dumps(data)>"}],
    "isError": false
  }
}
```

Erro de protocolo (ferramenta não existe, JSON inválido):
```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "error": {"code": -32601, "message": "Ferramenta 'xyz' não encontrada"}
}
```

Erro de domínio (Graph API falhou, rate limit):
```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "result": {
    "content": [{"type": "text", "text": "Erro: <mensagem>"}],
    "isError": true
  }
}
```

**Códigos de erro JSON-RPC padrão:**
```
-32700  PARSE_ERROR      JSON inválido
-32600  INVALID_REQUEST  request mal formado
-32601  METHOD_NOT_FOUND ferramenta não existe
-32602  INVALID_PARAMS   parâmetros inválidos
-32603  INTERNAL_ERROR   erro interno
```

**Endpoint SSE:**
```python
@router.get("/sse")
async def mcp_sse(request: Request, _user: User = Depends(get_current_user)):
    async def event_generator():
        yield f"data: {json.dumps({'type': 'hello', 'capabilities': {'tools': {}}})}\n\n"
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

**Dependency pattern** (mesmo padrão da Fase 1):
```python
async def get_graph_service() -> AsyncGenerator[GraphService, None]:
    service = GraphService()
    try:
        yield service
    finally:
        await service.close()

async def get_searxng_service() -> AsyncGenerator[SearXNGService, None]:
    service = SearXNGService()
    try:
        yield service
    finally:
        await service.close()
```

---

### 4. Atualizar `app/config.py`

Adicionar variável:
```python
SEARXNG_URL: str = "http://localhost:8080"
```

---

### 5. Atualizar `app/main.py`

Adicionar import e registro do router MCP:
```python
from app.routers import auth, graph, mcp, webhooks

# na seção de routers:
app.include_router(mcp.router)
```

---

### 6. Atualizar `.env.example`

Adicionar seção SearXNG:
```env
# --- SearXNG (busca web self-hosted) ---
# URL do container SearXNG (docker-compose sobe em http://localhost:8080)
SEARXNG_URL=http://localhost:8080
```

---

### 7. Atualizar `docker-compose.yml`

Adicionar serviço SearXNG:
```yaml
searxng:
  image: searxng/searxng:latest
  ports:
    - "8080:8080"
  environment:
    - SEARXNG_SECRET=lanez-searxng-secret
  restart: unless-stopped
```

---

## Modelos de dados (Fase 2 — nenhum novo modelo necessário)

A Fase 2 não adiciona tabelas. Usa o `User` e `GraphCache` da Fase 1.

---

## Variáveis de ambiente novas

```env
SEARXNG_URL=http://localhost:8080
```

---

## Estrutura de pastas — o que muda

```
app/
├── services/
│   └── searxng.py       ← NOVO
└── routers/
    └── mcp.py           ← NOVO

# Modificados:
app/services/graph.py    ← adicionar fetch_with_params() + params em _request_graph()
app/config.py            ← adicionar SEARXNG_URL
app/main.py              ← registrar mcp.router
.env.example             ← adicionar SEARXNG_URL
docker-compose.yml       ← adicionar serviço searxng
```

---

## Decisões técnicas (não questionar)

- **HTTP/SSE em vez de stdio** — Lanez já é FastAPI; rodar como subprocess duplicaria conexões DB e Redis
- **JWT obrigatório em todos os endpoints MCP** — reuso do `get_current_user` já existente
- **`fetch_with_params` sem cache** — queries parametrizadas (datas, textos livres) não compartilham chave de cache com `fetch_data`; cache aqui criaria falsos positivos
- **Erros de domínio como `isError: true` no result** — erros de protocolo usam o campo `error`; clientes MCP tratam diferente
- **Descriptions de ferramentas são strings fixas no código** — não geradas dinamicamente a partir de dados externos (proteção contra tool poisoning)
- **`get_searxng_service` como async generator** — fecha `httpx.AsyncClient` após cada request; mesmo padrão do `get_graph_service` e `get_webhook_service`

---

## Segurança — o que NÃO fazer

- Não aceitar `endpoint` ou `url` como parâmetro livre de ferramenta (exfiltração de dados)
- Não gerar `description` de ferramenta dinamicamente a partir de input externo (tool poisoning)
- Não logar tokens de acesso (usar `[token=REDACTED]`)
- Não expor endpoints MCP sem autenticação JWT

---

## O que NÃO implementar nesta fase

- Embeddings e busca semântica (Fase 3)
- Memória persistente (Fase 4)
- Briefing automático de reunião (Fase 5)
- Painel React e voz (Fase 6)
- Audit trail (Fase 7)

---

## Entregáveis esperados da Fase 2

1. `app/services/searxng.py` — cliente SearXNG funcional
2. `app/routers/mcp.py` — 3 endpoints (GET /mcp, POST /mcp/call, GET /mcp/sse) com 5 ferramentas
3. `app/services/graph.py` atualizado — `fetch_with_params()` + `params` em `_request_graph()`
4. `app/config.py` atualizado — `SEARXNG_URL`
5. `app/main.py` atualizado — `mcp.router` registrado
6. `.env.example` atualizado — `SEARXNG_URL` documentado
7. `docker-compose.yml` atualizado — serviço `searxng`

---

## Verificação funcional (como testar após a entrega)

```bash
# 1. Listar ferramentas
curl -s http://localhost:8000/mcp \
  -H "Authorization: Bearer SEU_JWT" | python -m json.tool

# Esperado: lista com get_calendar_events, search_emails, get_onenote_pages, search_files, web_search

# 2. Chamar get_calendar_events
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer SEU_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "tools/call",
    "params": {
      "name": "get_calendar_events",
      "arguments": {"start": "2026-04-24", "end": "2026-04-30"}
    }
  }' | python -m json.tool

# 3. Conexão SSE (deve ficar aberta)
curl -N http://localhost:8000/mcp/sse \
  -H "Authorization: Bearer SEU_JWT" \
  -H "Accept: text/event-stream"
# Esperado: data: {"type": "hello", ...} e pings a cada 30s

# 4. Ferramenta inexistente — deve retornar erro JSON-RPC -32601
curl -s -X POST http://localhost:8000/mcp/call \
  -H "Authorization: Bearer SEU_JWT" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"t","method":"tools/call","params":{"name":"nao_existe","arguments":{}}}' \
  | python -m json.tool
```
