# Lanez — Briefing Fase 6a para KIRO

## Contexto crítico para esta fase

Esta é a **primeira fase frontend** do projeto. O auditor (Claude Code) sabe que sua execução em frontend tende a divergir do briefing — improvisar designs, criar componentes próprios em vez de usar a biblioteca, esquecer estados de loading/erro/vazio, e expandir escopo. **Este briefing é deliberadamente prescritivo**: arquitetura, biblioteca de componentes, layout, cores e estrutura de hooks já foram decididos. Sua tarefa é executar com fidelidade, não redesenhar.

**Regra geral:** quando este briefing especifica um nome de arquivo, um componente shadcn ou uma rota, é exatamente esse. Sem renomear, sem substituir por equivalente "mais moderno", sem adicionar bibliotecas extras.

---

## O que é o Lanez

MCP Server pessoal que conecta AI assistants aos dados do Microsoft 365. Branch `main` em sincronia com `origin/main`, suíte 136/136 verde no commit `9324058`.

---

## O que as Fases 1-5 entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan, CORS já configurado para http://localhost:5173
├── config.py            ← Settings (CORS_ORIGINS, ANTHROPIC_API_KEY, BRIEFING_HISTORY_WINDOW_DAYS, ...)
├── database.py          ← AsyncSessionLocal, get_db (commit/rollback no boundary), get_redis
├── dependencies.py      ← get_current_user (atualmente apenas Bearer via OAuth2PasswordBearer)
├── models/
│   ├── user.py          ← User (email, tokens criptografados, token_expires_at, last_sync_at)
│   ├── cache.py
│   ├── webhook.py       ← WebhookSubscription
│   ├── embedding.py     ← Embedding (Vector(384), HNSW), com service_type
│   ├── memory.py        ← Memory (Vector(384), HNSW, GIN tags)
│   └── briefing.py      ← Briefing (event_id, event_subject, event_start, attendees, content, tokens)
├── routers/
│   ├── auth.py          ← /auth/microsoft, /auth/callback (retorna JSON), /auth/refresh
│   ├── graph.py
│   ├── webhooks.py
│   ├── mcp.py           ← 9 ferramentas
│   └── briefings.py     ← GET /briefings/{event_id}
└── services/
    ├── anthropic_client.py
    ├── briefing.py / briefing_context.py
    ├── embeddings.py
    ├── graph.py
    ├── memory.py
    ├── webhook.py
    ├── cache.py
    └── searxng.py
```

**Reutilizar das fases anteriores:**
- `get_current_user` em `app/dependencies.py` — vai ser estendido para aceitar cookie + Bearer
- `Briefing`, `WebhookSubscription`, `Embedding`, `Memory` — modelos consultados por endpoints novos do dashboard
- `CORS_ORIGINS` em `app/config.py` — já tem `http://localhost:5173` como default
- `TokenResponse` schema em `app/schemas/auth.py` — usado pelo callback atual; mantido

---

## Fase 6a — Painel React (somente leitura, sem voz)

### Objetivo

Painel web em React que permite ao usuário: (1) autenticar via Microsoft 365 e ter sessão persistente no browser via cookie HttpOnly, (2) ver status das integrações no dashboard, (3) navegar e ler briefings gerados, (4) consultar configurações atuais do sistema. **Sem voz, sem audit trail, sem edição de settings.** Frontend roda local em dev (Vite `:5173`), backend continua em `:8000`.

### O que NÃO entra na 6a

- Pipeline de voz (`POST /voice/transcribe`, Groq Whisper, botão de mic) — **Fase 6b**
- Página `/audit` e backend de audit log — **Fase 7**
- Edição de settings (apenas leitura nesta fase)
- Deploy em Vercel/Hetzner (rodar local é o suficiente)
- Internacionalização (UI em pt-BR fixo)
- PWA / offline support
- Tela de signup ou multi-tenant — Lanez é single-user

### Decisões técnicas (já aprovadas pelo usuário)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Auth do painel | Cookie HttpOnly + SameSite=Lax + Secure (em produção) | Evita XSS contra JWT em localStorage. Reaproveita JWT já emitido pelo callback OAuth |
| Backwards compat | `/auth/callback` ganha modo dual: com `return_url` → cookie + redirect; sem → JSON (atual) | Não quebra MCP/curl. Painel sempre passa `return_url` |
| Stack frontend | Vite + React 18 + TypeScript + Tailwind 3.4 + shadcn/ui + TanStack Query v5 + React Router v6 | Stack open source, sem custo. shadcn/ui dá componentes prontos e consistentes — KIRO não precisa desenhar |
| Diretório | `frontend/` no root do repo | Mono-repo simples. Backend em `app/`, frontend em `frontend/` |
| Estilo de componente | shadcn/ui (Radix + Tailwind) — adicionados via `npx shadcn@latest add <component>` | Componentes vivem em `frontend/src/components/ui/` e são copiados, não importados como dependência |
| Gerenciamento de servidor-state | TanStack Query (não Redux, não Zustand para servidor) | Cache, retry, refetch já resolvidos. Nenhum store global de estado de servidor é necessário |
| Cliente-state | React Context para auth (`useAuth`) — só isso | Não introduzir Zustand/Jotai |
| Charts | Recharts | Para gráfico de uso de tokens no dashboard |
| Markdown render | `react-markdown` + `remark-gfm` | Conteúdo do briefing é Markdown gerado pelo Haiku (com tabelas, listas) |
| Tema | Light / Dark / System — toggle no TopBar, persistido em `localStorage` | shadcn/ui já suporta via CSS variables; sem libs extras (não usar `next-themes`) |
| Testes | Vitest + React Testing Library — apenas smoke tests (5-8 testes) | Cobertura mínima de "renderiza sem crashar" + "auth gate funciona". Sem cobertura aspiracional |
| Tooling | ESLint + Prettier configurados, mas sem CI travando build em warnings | Solo dev, sem time |

---

## Parte B — Mudanças no Backend

Esta fase exige 5 mudanças no backend para suportar o painel. **Implemente-as primeiro**, com testes, antes de começar o frontend.

### Pré-flight obrigatório — validar nomes de coluna

Antes de escrever qualquer query nova (6a.B.4 e 6a.B.5), abra os arquivos de modelo e confirme os nomes **reais** das colunas. O briefing assume nomes que podem divergir do código atual:

```bash
# Inspecionar e listar colunas e tipos:
grep -n "Column\|Mapped\[" app/models/briefing.py app/models/embedding.py app/models/webhook.py app/models/memory.py
```

Confirmar especificamente:

| Campo assumido no briefing | Onde aparece | Ação |
|---|---|---|
| `Briefing.user_id` | 6a.B.4, 6a.B.5 | Confirmar nome real (pode ser `user_id` ou outro) |
| `Embedding.service` (Enum com `.value`) | 6a.B.5 (group_by) | Confirmar se o campo é `service` **ou** `service_type`, e se é `Enum` ou `String`. Se for `String`, remover `.value` |
| `Embedding.user_id` | 6a.B.5 | Confirmar |
| `WebhookSubscription.service` (Enum com `.value`) | 6a.B.5 | Mesma verificação que `Embedding.service` |
| `WebhookSubscription.user_id` / `expires_at` | 6a.B.5 | Confirmar |
| `Memory.user_id` | 6a.B.5 | Confirmar |
| `Briefing.input_tokens / output_tokens / cache_read_tokens / cache_write_tokens / generated_at / event_start / event_subject / event_id / attendees / content` | 6a.B.4, 6a.B.5 | Confirmar todos antes de escrever |

Se algum nome divergir, **ajustar o código gerado para o nome real**, não inventar migrations para renomear. Reportar as divergências encontradas no bloco "Explicação — Tarefa 1" antes de seguir.

### 6a.B.1 Auth dual (Cookie + Bearer) — `app/dependencies.py`

Atualmente `get_current_user` aceita apenas `Authorization: Bearer <jwt>` via `OAuth2PasswordBearer`. Para o painel, o cookie HttpOnly precisa ser aceito também. Manter Bearer para MCP e curl.

**Implementação exata:**

```python
"""Dependency de autenticação — aceita JWT via cookie HttpOnly OU Authorization Bearer."""

from fastapi import Cookie, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

_COOKIE_NAME = "lanez_session"
_JWT_ALGORITHM = "HS256"


def _extract_token(request: Request) -> str | None:
    """Extrai JWT do cookie HttpOnly OU do header Authorization Bearer.

    Cookie tem prioridade (painel é o consumidor primário). Bearer é
    o fallback para MCP e ferramentas CLI.
    """
    cookie_token = request.cookies.get(_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Valida JWT (cookie ou Bearer) e retorna User. 401 se inválido/expirado."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request)
    if token is None:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
```

**Atenção:** o nome do cookie é `lanez_session`. Use exatamente isso em todos os lugares (login, logout, frontend).

**Removido:** `oauth2_scheme = OAuth2PasswordBearer(...)` no topo do arquivo. Ele não é mais usado.

**Antes de remover, executar:**

```bash
grep -rn "oauth2_scheme" app/ tests/
```

Listar todos os callsites encontrados. Para cada arquivo que importa `oauth2_scheme` de `app.dependencies` (eram só decorativos para Swagger / cadeado no /docs): remover o import e quaisquer `Depends(oauth2_scheme)` em assinaturas de endpoint. Confirmar que o cadeado do Swagger continua aparecendo via `WWW-Authenticate: Bearer` retornado em 401 e/ou via `securitySchemes` global do FastAPI — não há perda funcional.

### 6a.B.2 Callback OAuth modo dual — `app/routers/auth.py`

`/auth/microsoft` aceita query param opcional `return_url`. Se presente, é armazenado no Redis junto com `code_verifier` e `state`. No `/auth/callback`, se houve `return_url` para esse `state`, retornar `RedirectResponse` para `return_url` com `Set-Cookie: lanez_session=<jwt>; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800`. Se não houve `return_url`, manter o comportamento atual (retornar `TokenResponse` JSON).

**Mudanças exatas:**

1. Em `auth_microsoft` — aceitar `return_url: str | None = Query(default=None)`. Validar que `return_url` está numa allowlist (`settings.CORS_ORIGINS` separado por vírgula) — qualquer URL fora disso é rejeitada com 400. Armazenar no Redis: `await redis.set(f"oauth:state:{state}", json.dumps({"code_verifier": code_verifier, "return_url": return_url}), ex=600)` (passa de string pura para JSON).

2. Em `auth_callback` — após consumir o state do Redis, **preservar o guard existente** para `state` ausente/expirado:

```python
raw = await redis.get(f"oauth:state:{state}")
if raw is None:
    raise HTTPException(status_code=400, detail="state inválido ou expirado")
state_data = json.loads(raw)
code_verifier = state_data["code_verifier"]
```

Após emitir o JWT (`internal_jwt = _create_jwt(str(user.id))`), bifurcar:

```python
if state_data.get("return_url"):
    response = RedirectResponse(url=state_data["return_url"], status_code=302)
    response.set_cookie(
        key="lanez_session",
        value=internal_jwt,
        max_age=7 * 24 * 60 * 60,  # 7 dias
        httponly=True,
        samesite="lax",
        secure=False,  # True em produção (HTTPS)
        path="/",
    )
    return response

# Sem return_url: comportamento legado mantido
return TokenResponse(...)
```

**Nota:** `secure=False` em dev (HTTP localhost). Em produção precisa virar `True`. Adicionar comentário no código: `# TODO Fase 6c (deploy): secure=True quando atrás de HTTPS`.

**Não condicionar `secure` por `request.url.scheme == "https"` "por elegância"** — isso falha quando o app está atrás de proxy/TLS terminator. Mantenha o literal `False` com TODO; será virado para `True` por config na fase de deploy.

**Não trocar `samesite="lax"` por `"strict"` "por segurança"** — o login dispara via `window.location.href` (top-level navigation) e `Lax` é o que permite o cookie ser enviado no redirect de retorno. `Strict` quebra o fluxo.

3. Validação de allowlist do `return_url`:

```python
def _is_allowed_return_url(url: str) -> bool:
    """Valida que return_url começa com uma origem listada em CORS_ORIGINS."""
    allowed = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    return any(url.startswith(origin) for origin in allowed)
```

Chamar em `auth_microsoft` antes de armazenar; se retornar False, `raise HTTPException(400, "return_url não permitido")`.

### 6a.B.3 Endpoints de sessão — `app/routers/auth.py`

Adicionar **dois endpoints novos** ao mesmo router:

```python
@router.get("/me", response_model=UserMeResponse)
async def auth_me(current_user: User = Depends(get_current_user)) -> UserMeResponse:
    """Retorna dados básicos do usuário autenticado. Usado pelo painel para
    decidir se mostra /login ou /dashboard."""
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        token_expires_at=current_user.token_expires_at,
        last_sync_at=current_user.last_sync_at,
        created_at=current_user.created_at,
    )


@router.post("/logout", status_code=204)
async def auth_logout() -> Response:
    """Limpa o cookie de sessão. Idempotente — sempre retorna 204."""
    response = Response(status_code=204)
    response.delete_cookie(key="lanez_session", path="/")
    return response
```

**Schema novo** em `app/schemas/auth.py` (acrescentar — não substituir os existentes):

```python
class UserMeResponse(BaseModel):
    id: UUID
    email: str
    token_expires_at: datetime
    last_sync_at: datetime | None
    created_at: datetime
```

### 6a.B.4 Endpoint `GET /briefings` (lista) — `app/routers/briefings.py`

O endpoint atual `GET /briefings/{event_id}` retorna um briefing específico. Adicionar **endpoint de listagem paginada** acima dele (deve ser registrado antes para não conflitar com path matching, mas FastAPI faz exact match de path antes de path com placeholder, então a ordem dos decorators não importa — ainda assim, declarar antes por legibilidade):

```python
@router.get("", response_model=BriefingListResponse)
async def list_briefings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Busca em event_subject"),
) -> BriefingListResponse:
    """Lista briefings do usuário, paginados por event_start desc.

    Suporta filtro textual em event_subject (ILIKE %q%).
    """
    filters = [Briefing.user_id == user.id]
    if q:
        filters.append(Briefing.event_subject.ilike(f"%{q}%"))

    count_stmt = select(func.count()).select_from(Briefing).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    paged_stmt = (
        select(Briefing)
        .where(*filters)
        .order_by(Briefing.event_start.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    briefings = (await db.execute(paged_stmt)).scalars().all()

    return BriefingListResponse(
        items=[BriefingListItem.model_validate(b, from_attributes=True) for b in briefings],
        total=total,
        page=page,
        page_size=page_size,
    )
```

**Schemas novos** em `app/schemas/briefing.py` (acrescentar):

```python
class BriefingListItem(BaseModel):
    id: UUID
    event_id: str
    event_subject: str
    event_start: datetime
    event_end: datetime
    attendees: list[str]
    generated_at: datetime

    model_config = {"from_attributes": True}


class BriefingListResponse(BaseModel):
    items: list[BriefingListItem]
    total: int
    page: int
    page_size: int
```

**Importante:** o item da lista NÃO contém `content` nem telemetria de tokens — payload reduzido. Para ler o conteúdo, frontend chama `GET /briefings/{event_id}`.

### 6a.B.5 Endpoint `GET /status` (dashboard) — `app/routers/status.py` (NOVO)

Cria router novo para evitar acoplar com auth/briefings. Endpoint único que agrega métricas para o dashboard:

```python
"""Router de status — métricas agregadas para o painel."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.embedding import Embedding
from app.models.memory import Memory
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.schemas.status import StatusConfig, StatusResponse, ServiceCount, TokenUsageBucket

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=StatusResponse)
async def get_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Retorna métricas agregadas do usuário para o dashboard.

    Inclui:
    - Estado do token Microsoft (expira em N segundos)
    - Subscrições webhook ativas (count + lista breve)
    - Contagem de embeddings por serviço
    - Contagem de memórias
    - Briefings dos últimos 30 dias (count + lista das 5 mais recentes)
    - Soma de tokens Claude consumidos nos últimos 30 dias (input/output/cache_read/cache_write)
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Webhooks
    webhook_stmt = select(WebhookSubscription).where(
        WebhookSubscription.user_id == user.id
    )
    webhooks = (await db.execute(webhook_stmt)).scalars().all()

    # Embeddings por serviço
    emb_stmt = (
        select(Embedding.service, func.count())
        .where(Embedding.user_id == user.id)
        .group_by(Embedding.service)
    )
    embeddings_by_service = [
        ServiceCount(service=row[0].value, count=row[1])
        for row in (await db.execute(emb_stmt)).all()
    ]

    # Memórias
    mem_count_stmt = select(func.count()).select_from(
        select(Memory).where(Memory.user_id == user.id).subquery()
    )
    memories_count = (await db.execute(mem_count_stmt)).scalar_one()

    # Briefings últimos 30 dias
    briefing_count_stmt = select(func.count()).select_from(
        select(Briefing)
        .where(
            Briefing.user_id == user.id,
            Briefing.generated_at >= thirty_days_ago,
        )
        .subquery()
    )
    briefings_count_30d = (await db.execute(briefing_count_stmt)).scalar_one()

    recent_briefings_stmt = (
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .order_by(Briefing.event_start.desc())
        .limit(5)
    )
    recent_briefings = (await db.execute(recent_briefings_stmt)).scalars().all()

    # Tokens últimos 30 dias (somatório)
    token_sum_stmt = select(
        func.coalesce(func.sum(Briefing.input_tokens), 0),
        func.coalesce(func.sum(Briefing.output_tokens), 0),
        func.coalesce(func.sum(Briefing.cache_read_tokens), 0),
        func.coalesce(func.sum(Briefing.cache_write_tokens), 0),
    ).where(
        Briefing.user_id == user.id,
        Briefing.generated_at >= thirty_days_ago,
    )
    in_t, out_t, cache_r, cache_w = (await db.execute(token_sum_stmt)).one()

    return StatusResponse(
        user_email=user.email,
        token_expires_at=user.token_expires_at,
        token_expires_in_seconds=int(
            (user.token_expires_at - now).total_seconds()
        ),
        last_sync_at=user.last_sync_at,
        webhook_subscriptions=[
            {"service": w.service.value, "expires_at": w.expires_at} for w in webhooks
        ],
        embeddings_by_service=embeddings_by_service,
        memories_count=memories_count,
        briefings_count_30d=briefings_count_30d,
        recent_briefings=[
            {
                "event_id": b.event_id,
                "event_subject": b.event_subject,
                "event_start": b.event_start,
            }
            for b in recent_briefings
        ],
        tokens_30d={
            "input": in_t,
            "output": out_t,
            "cache_read": cache_r,
            "cache_write": cache_w,
        },
        config={
            "briefing_history_window_days": settings.BRIEFING_HISTORY_WINDOW_DAYS,
        },
    )
```

**Schema novo** em `app/schemas/status.py` (NOVO):

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ServiceCount(BaseModel):
    service: str
    count: int


class TokenUsageBucket(BaseModel):
    input: int
    output: int
    cache_read: int
    cache_write: int


class StatusConfig(BaseModel):
    briefing_history_window_days: int


class StatusResponse(BaseModel):
    user_email: str
    token_expires_at: datetime
    token_expires_in_seconds: int
    last_sync_at: datetime | None
    webhook_subscriptions: list[dict[str, Any]]
    embeddings_by_service: list[ServiceCount]
    memories_count: int
    briefings_count_30d: int
    recent_briefings: list[dict[str, Any]]
    tokens_30d: TokenUsageBucket
    config: StatusConfig
```

Registrar o router em `app/main.py` junto aos outros: `app.include_router(status.router)`.

### 6a.B.6 Testes do backend (mínimo 8 novos)

**Auth dual:**
- `test_get_current_user_accepts_cookie` — request com cookie `lanez_session=<jwt>` retorna user
- `test_get_current_user_accepts_bearer` — comportamento atual preservado
- `test_get_current_user_cookie_takes_priority` — quando ambos presentes, cookie ganha

**Callback dual:**
- `test_auth_callback_with_return_url_sets_cookie_and_redirects` — passa `return_url` allowlisted, response é 302 com `Set-Cookie: lanez_session=...; HttpOnly`
- `test_auth_callback_without_return_url_returns_json` — comportamento atual preservado
- `test_auth_microsoft_rejects_return_url_outside_allowlist` — `?return_url=https://evil.com` → 400

**Endpoints novos:**
- `test_auth_me_returns_user_info` — autenticado via cookie, retorna email/token_expires_at/etc
- `test_auth_logout_clears_cookie` — POST /auth/logout → 204 + `Set-Cookie` com `Max-Age=0`
- `test_briefings_list_paginates_and_filters` — cria 25 briefings, GET com `page=2, page_size=10, q=alpha` retorna subset correto
- `test_status_aggregates_correctly` — popula DB com fixtures, GET /status retorna contagens corretas

---

## Parte F — Frontend

### 6a.F.1 Estrutura de diretórios — exata

```
frontend/
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .gitignore
├── README.md
├── components.json              ← config do shadcn/ui
└── src/
    ├── main.tsx                  ← entry: monta App em #root
    ├── App.tsx                   ← BrowserRouter + QueryClientProvider + AuthProvider + Routes
    ├── index.css                 ← @tailwind base/components/utilities + variáveis shadcn
    ├── lib/
    │   ├── api.ts                ← cliente fetch com credentials: 'include'
    │   ├── queryClient.ts        ← new QueryClient com defaults
    │   └── utils.ts              ← cn() utility do shadcn (clsx + tailwind-merge)
    ├── auth/
    │   ├── AuthContext.tsx       ← Context + Provider + hook useAuth()
    │   └── ProtectedRoute.tsx    ← componente que redireciona para /login se não autenticado
    ├── theme/
    │   ├── ThemeContext.tsx      ← Context + Provider + hook useTheme() (light/dark/system)
    │   └── ThemeToggle.tsx       ← DropdownMenu com 3 opções (sol/lua/monitor)
    ├── hooks/
    │   ├── useStatus.ts          ← TanStack Query hook para GET /status
    │   ├── useBriefings.ts       ← hook para GET /briefings (lista paginada)
    │   └── useBriefing.ts        ← hook para GET /briefings/:event_id
    ├── components/
    │   ├── ui/                   ← componentes shadcn (button, card, input, ...)
    │   ├── AppShell.tsx          ← layout com sidebar + topbar (envolve rotas autenticadas)
    │   ├── Sidebar.tsx
    │   ├── TopBar.tsx
    │   ├── StatusCard.tsx
    │   ├── TokenUsageChart.tsx   ← Recharts
    │   ├── BriefingCard.tsx      ← item de lista de briefings
    │   ├── BriefingMarkdown.tsx  ← wrapper de react-markdown com prose tailwind
    │   ├── EmptyState.tsx
    │   ├── ErrorState.tsx
    │   └── LoadingSkeleton.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── DashboardPage.tsx
    │   ├── BriefingsListPage.tsx
    │   ├── BriefingDetailPage.tsx
    │   └── SettingsPage.tsx
    └── __tests__/
        ├── setup.ts              ← config Vitest + jsdom
        ├── App.test.tsx
        ├── ProtectedRoute.test.tsx
        └── BriefingsListPage.test.tsx
```

**Não criar:** `frontend/src/store/`, `frontend/src/context/` (use `frontend/src/auth/`), `frontend/src/services/` (use `frontend/src/lib/api.ts`).

### 6a.F.2 Setup inicial (comandos exatos)

```bash
cd frontend
npm create vite@latest . -- --template react-ts
# Sobrescrever quando perguntado.
npm install

# Tailwind v3.4 (não v4 — estabilidade) + plugin typography (usado em BriefingMarkdown)
npm install -D tailwindcss@3.4 postcss autoprefixer @tailwindcss/typography
npx tailwindcss init -p

# Roteamento + dados + utilitários
npm install react-router-dom@6 @tanstack/react-query@5
npm install date-fns recharts react-markdown remark-gfm
npm install clsx tailwind-merge class-variance-authority lucide-react

# shadcn/ui (CLI configura tudo)
npx shadcn@latest init
# Escolher: Default, Slate, CSS variables: Yes

# Componentes shadcn necessários (adicionar todos nesta ordem)
npx shadcn@latest add button card input label badge skeleton alert separator dropdown-menu table sonner

# Testes
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitejs/plugin-react
```

**`package.json` scripts** (exatos — substituir os criados pelo Vite):

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "lint": "eslint . --ext ts,tsx",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

### 6a.F.3 Configuração do Vite — `frontend/vite.config.ts`

```ts
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/briefings": "http://localhost:8000",
      "/status": "http://localhost:8000",
      "/mcp": "http://localhost:8000",
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.ts"],
    globals: true,
  },
});
```

**Por que proxy?** Em dev, o browser faz request para `http://localhost:5173/auth/me` e o Vite encaminha para `http://localhost:8000/auth/me`. Cookie é mesma origem do ponto de vista do browser → CORS resolvido sem `credentials: 'include'` cross-origin. Em produção (fora do escopo da 6a) seria diferente, mas para dev local é o caminho mais simples.

**Não use** `define: { 'process.env.VITE_API_URL': ... }` ou variáveis de ambiente para URL do backend. O proxy substitui essa necessidade.

### 6a.F.4 Cliente API — `frontend/src/lib/api.ts`

```ts
/**
 * Cliente HTTP fino. Todas as requests vão para a mesma origem
 * (Vite proxy encaminha em dev). Cookies são enviados automaticamente
 * porque é same-origin do ponto de vista do browser.
 */

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // resposta não é JSON; mantém statusText
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};
```

**Não adicionar:** axios, ky, ofetch. `fetch` resolve.

### 6a.F.5 Auth — `frontend/src/auth/AuthContext.tsx`

```tsx
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, ApiError } from "@/lib/api";

interface User {
  id: string;
  email: string;
  token_expires_at: string;
  last_sync_at: string | null;
  created_at: string;
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const login = () => {
    const returnUrl = `${window.location.origin}/dashboard`;
    window.location.href = `/auth/microsoft?return_url=${encodeURIComponent(returnUrl)}`;
  };

  const logout = async () => {
    await api.post("/auth/logout");
    setUser(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
```

### 6a.F.5b Tema (light/dark/system) — `frontend/src/theme/ThemeContext.tsx`

shadcn/ui já entrega CSS variables para light e dark em `index.css` quando inicializado com "CSS variables: Yes". O switch é feito adicionando/removendo a classe `dark` no `<html>`. Nenhuma biblioteca externa.

```tsx
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

type Theme = "light" | "dark" | "system";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "lanez_theme";

function getSystemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme): "light" | "dark" {
  const resolved = theme === "system" ? getSystemTheme() : theme;
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  root.classList.add(resolved);
  return resolved;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return stored ?? "system";
  });
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() =>
    applyTheme(theme),
  );

  useEffect(() => {
    setResolvedTheme(applyTheme(theme));
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  // Reagir a mudanças do prefers-color-scheme quando theme=system
  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => setResolvedTheme(applyTheme("system"));
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme: setThemeState, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme deve ser usado dentro de ThemeProvider");
  return ctx;
}
```

**Toggle** — `frontend/src/theme/ThemeToggle.tsx`:

```tsx
import { Moon, Sun, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/theme/ThemeContext";

export function ThemeToggle() {
  const { setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Alternar tema">
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun className="h-4 w-4 mr-2" /> Claro
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon className="h-4 w-4 mr-2" /> Escuro
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor className="h-4 w-4 mr-2" /> Sistema
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

**Tailwind config** — `tailwind.config.js` precisa ter `darkMode: "class"` (shadcn já configura assim por padrão; verificar). Se faltar, adicionar manualmente:

```js
module.exports = {
  darkMode: "class",
  // ...resto da config gerada pelo shadcn
};
```

**`ThemeProvider` envolve toda a árvore** — adicionar em `App.tsx` como o provider mais externo (antes de `QueryClientProvider`):

```tsx
<ThemeProvider>
  <QueryClientProvider client={queryClient}>
    {/* ...resto */}
  </QueryClientProvider>
</ThemeProvider>
```

### 6a.F.6 ProtectedRoute — `frontend/src/auth/ProtectedRoute.tsx`

```tsx
import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    // Evita flash de skeleton fora do AppShell durante a verificação
    // inicial de sessão; pinta apenas o background do tema.
    return <div className="min-h-screen bg-background" />;
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

### 6a.F.7 Roteamento — `frontend/src/App.tsx`

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";

import { queryClient } from "@/lib/queryClient";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { AppShell } from "@/components/AppShell";

import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { BriefingsListPage } from "@/pages/BriefingsListPage";
import { BriefingDetailPage } from "@/pages/BriefingDetailPage";
import { SettingsPage } from "@/pages/SettingsPage";

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/briefings" element={<BriefingsListPage />} />
              <Route path="/briefings/:eventId" element={<BriefingDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

### 6a.F.8 Layout AppShell — `frontend/src/components/AppShell.tsx`

Layout com **sidebar fixa à esquerda (240px)** + **conteúdo principal**. Sidebar contém: logo "Lanez" + navegação (Dashboard, Briefings, Settings) + botão Logout no rodapé. TopBar contém: `<ThemeToggle />` + email do usuário.

**Estrutura visual:**

```
┌──────────┬──────────────────────────────────────┐
│          │  TopBar (email do usuário, hora)     │
│ Sidebar  ├──────────────────────────────────────┤
│ 240px    │                                      │
│          │                                      │
│  Logo    │    <Outlet /> (página atual)         │
│          │                                      │
│  Dash    │                                      │
│  Briefs  │                                      │
│  Setts   │                                      │
│          │                                      │
│  Logout  │                                      │
└──────────┴──────────────────────────────────────┘
```

```tsx
import { Outlet, Link, useLocation } from "react-router-dom";
import { LayoutDashboard, FileText, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/theme/ThemeToggle";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/briefings", label: "Briefings", icon: FileText },
  { to: "/settings", label: "Configurações", icon: Settings },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside className="w-60 bg-card border-r border-border flex flex-col">
        <div className="px-6 py-5 text-2xl font-semibold tracking-tight">
          Lanez
        </div>
        <nav className="flex-1 px-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-border">
          <Button
            variant="ghost"
            className="w-full justify-start"
            onClick={() => void logout()}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Sair
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <header className="h-14 border-b border-border bg-card px-6 flex items-center justify-end gap-3 text-sm text-muted-foreground">
          <span>{user?.email}</span>
          <ThemeToggle />
        </header>
        <div className="p-6 max-w-6xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
```

### 6a.F.9 Pages — especificação por página

#### LoginPage

Página inteira centralizada vertical + horizontal. Card no centro com:
- Título "Lanez"
- Subtítulo "Entre com sua conta Microsoft 365"
- Botão grande "Entrar com Microsoft" (variant="default") que chama `login()` do `useAuth`

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/AuthContext";

export function LoginPage() {
  const { login, user, loading } = useAuth();
  if (loading) return null;
  if (user) {
    window.location.href = "/dashboard";
    return null;
  }
  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-3xl">Lanez</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-slate-600">
            Entre com sua conta Microsoft 365 para acessar o painel.
          </p>
          <Button className="w-full" onClick={login}>
            Entrar com Microsoft
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
```

#### DashboardPage

Grid de cards. Layout:

```
[ Card: Microsoft 365  ] [ Card: Webhooks ativos     ]
[ Card: Briefings 30d ] [ Card: Memórias            ]
[ Card: Embeddings por serviço (lista)              ]
[ Card: Uso de tokens 30d (gráfico Recharts)        ]
[ Card: Briefings recentes (lista de 5 últimos)     ]
```

Usar `useStatus()` (hook abaixo). Estados: loading → `LoadingSkeleton`, erro → `ErrorState`, vazio (impossível para dashboard com user logado, mas defender) → mensagem.

**Card "Microsoft 365":** mostra `user_email`, `token_expires_in_seconds` formatado como "expira em X dias / horas / minutos" via `date-fns/formatDistanceToNow`. Se `token_expires_in_seconds < 0`, mostrar Badge vermelho "Token expirado".

**Card "Webhooks ativos":** count + lista de subscriptions (service + expires_at).

**Card "Briefings 30d":** número grande + texto "nos últimos 30 dias".

**Card "Memórias":** number `memories_count`.

**Card "Embeddings por serviço":** tabela com 2 colunas (Serviço, Quantidade). Usar `<Table>` shadcn.

**Card "Uso de tokens 30d":** gráfico de barras Recharts com 4 barras: Input, Output, Cache Read, Cache Write. Cores: slate-700, slate-500, emerald-500, sky-500.

**Card "Briefings recentes":** lista de até 5 com `event_subject` em negrito + data formatada `dd 'de' MMM '·' HH:mm` em pt-BR. Cada item é um `Link` para `/briefings/:event_id`.

**Atenção a cores no dark mode:** os tokens shadcn (`bg-card`, `text-foreground`, `text-muted-foreground`, `border-border`, `bg-primary`) já se adaptam. As cores **literais** usadas no Recharts (`#334155 slate-700`, `#64748b slate-500`, `#10b981 emerald-500`, `#0ea5e9 sky-500`) precisam de variantes para dark — usar `useTheme()` no `TokenUsageChart` e trocar a paleta:
- Light: slate-700, slate-500, emerald-500, sky-500
- Dark: slate-300, slate-400, emerald-400, sky-400

#### BriefingsListPage

Layout: barra de busca (Input shadcn com placeholder "Buscar por assunto...") + lista de cards de briefings + paginação (botões "Anterior" / "Próximo" + contador "Página X de Y").

`BriefingCard` mostra: `event_subject` (h3), `event_start` formatado, badges com primeiros 3 attendees + "+N mais" se houver mais. Hover muda background para `bg-accent` (token shadcn — adapta light/dark). Click navega para `/briefings/:event_id`.

Estados:
- Carregando: 5 `<Skeleton>` empilhados (h-24)
- Vazio: `EmptyState` com texto "Nenhum briefing ainda. Eles serão gerados automaticamente quando reuniões aparecerem no calendar."
- Erro: `ErrorState` com botão "Tentar novamente"

Busca: debounce 300ms via `useEffect` + `setTimeout`. Não usar `lodash.debounce`.

#### BriefingDetailPage

Topo: botão "← Voltar" para `/briefings`. Em seguida:

- Cabeçalho do evento: `event_subject` (h1), data formatada, badges de attendees
- Telemetria de geração em texto pequeno cinza: "Gerado em <data>, <input_tokens + cache> tokens entrada · <output_tokens> saída · modelo <model_used>"
- `<Separator />`
- `<BriefingMarkdown content={briefing.content} />` — renderiza com `react-markdown` + `remark-gfm`, classes Tailwind `prose prose-slate dark:prose-invert max-w-none`. O plugin `@tailwindcss/typography` já foi instalado em 6a.F.2; basta registrá-lo em `tailwind.config.js`: `plugins: [require("@tailwindcss/typography")]`

Estados loading/erro como na lista. 404: `EmptyState` "Briefing não encontrado para este evento."

#### SettingsPage

**Read-only nesta fase.** Lista de Cards informativos:

- "Janela histórica de briefings" — valor lido de `useStatus().data?.config.briefing_history_window_days` formatado como "X dias" + nota "configurado via env no servidor". Não hardcodar.
- "Email autenticado" — `user.email`
- "Última sincronização" — `user.last_sync_at` formatado
- "Token Microsoft" — link "Renovar token agora" que chama `POST /auth/refresh` e mostra toast de sucesso/erro via Sonner. Importar `toast` do pacote `sonner` diretamente: `import { toast } from "sonner"`. O `<Toaster />` já está montado em `App.tsx`.

Adicionar nota visível no topo da página: `<Alert>` informativo "Configurações editáveis virão em uma fase futura. Esta tela é somente leitura."

### 6a.F.10 Hooks de dados

```ts
// useStatus.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface StatusData { /* mirror do StatusResponse pydantic */ }

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => api.get<StatusData>("/status"),
    staleTime: 30_000,
  });
}
```

Padrão idêntico para `useBriefings(page, pageSize, q)` (`/briefings?page=...`) e `useBriefing(eventId)` (`/briefings/:eventId`). `useBriefings` deve passar params via `URLSearchParams` no path.

**`useBriefings` deve usar `placeholderData: keepPreviousData`** para evitar flicker para skeleton ao trocar de página ou digitar na busca. TanStack Query v5 substituiu o antigo `keepPreviousData: true` por essa forma:

```ts
import { keepPreviousData, useQuery } from "@tanstack/react-query";

export function useBriefings(page: number, pageSize: number, q: string) {
  return useQuery({
    queryKey: ["briefings", { page, pageSize, q }],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (q) params.set("q", q);
      return api.get<BriefingListResponse>(`/briefings?${params.toString()}`);
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
```

Tipos TypeScript: declarar interfaces que refletem os schemas Pydantic. **Não gerar via openapi-typescript-codegen** — é um overhead que não vale para 3 endpoints.

### 6a.F.11 README — `frontend/README.md`

Conteúdo mínimo:

```markdown
# Lanez — Painel

Frontend React do Lanez. Roda em dev a `http://localhost:5173` e proxia
requests para o backend FastAPI em `http://localhost:8000`.

## Pré-requisitos

- Node 20+
- Backend Lanez rodando em :8000 (ver README do projeto raiz)

## Comandos

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # build de produção em dist/
    npm test         # roda Vitest

## Stack

Vite, React 18, TypeScript, Tailwind 3.4, shadcn/ui, TanStack Query v5,
React Router v6, Recharts, react-markdown.
```

### 6a.F.12 Testes do frontend (mínimo 6 smoke tests)

- `App.test.tsx` — renderiza sem crashar; sem usuário, redireciona para `/login`
- `ProtectedRoute.test.tsx` — sem user → `Navigate to="/login"`; com user → renderiza children
- `BriefingsListPage.test.tsx` — mock do `useBriefings` retornando 3 itens, verifica que 3 cards aparecem
- `BriefingsListPage.test.tsx` — mock retornando lista vazia, verifica que `EmptyState` aparece
- `LoginPage.test.tsx` — clicar no botão chama `window.location.href = "/auth/microsoft?return_url=..."` (mockar window.location)
- `ThemeContext.test.tsx` — `setTheme("dark")` adiciona classe `dark` em `document.documentElement` e persiste em `localStorage` com chave `lanez_theme`

Setup do Vitest em `src/__tests__/setup.ts`:

```ts
import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock global do fetch para não fazer request real em testes
global.fetch = vi.fn();
```

---

## Critérios de aceitação

A entrega 6a é aceita se TODOS abaixo passarem:

### Backend
1. `app/dependencies.py::get_current_user` aceita cookie `lanez_session` E header `Authorization: Bearer`. Cookie tem prioridade.
2. `GET /auth/microsoft?return_url=<url>` rejeita URLs fora de `CORS_ORIGINS` com 400.
3. `GET /auth/callback` com `return_url` válido retorna 302 + `Set-Cookie: lanez_session=<jwt>; HttpOnly; SameSite=Lax`.
4. `GET /auth/callback` sem `return_url` mantém comportamento atual (retorna `TokenResponse` JSON).
5. `GET /auth/me` retorna `UserMeResponse` quando autenticado, 401 caso contrário.
6. `POST /auth/logout` retorna 204 e cookie limpo.
7. `GET /briefings` retorna lista paginada com filtro `q`, ordenada por `event_start desc`.
8. `GET /status` retorna agregação completa (token, webhooks, embeddings, memórias, briefings, tokens 30d).
9. Suíte completa passa, **sem novas falhas**, com pelo menos os 10 testes obrigatórios da seção 6a.B.6.
   - Rodar `pytest` **sem `-k`, sem `-x`, sem flags de seleção** (a Fase 5 quebrou exatamente por executar suíte parcial e não notar 2 testes pré-existentes desatualizados).
   - Reportar a contagem total absoluta no formato `N passed, M failed` no bloco de Explicação. A meta é manter `136 + novos` verdes; qualquer redução exige justificativa explícita.

### Frontend
10. `npm install && npm run dev` em `frontend/` sobe Vite em :5173 sem erros.
11. `npm run build` produz bundle em `frontend/dist/` sem warnings de TypeScript.
12. `npm test` passa todos os smoke tests.
13. Diretório `frontend/` segue exatamente a estrutura da seção 6a.F.1.
14. shadcn/ui inicializado com tema Slate, CSS variables ativadas.
15. Auth flow funciona end-to-end: clicar "Entrar com Microsoft" → OAuth Microsoft → redirect de volta para `/dashboard` autenticado.
16. Logout limpa cookie e redireciona para `/login`.
17. Dashboard renderiza todos os 7 cards listados em 6a.F.9 → DashboardPage com dados reais do backend.
18. Lista de briefings tem paginação funcional, busca com debounce 300ms, e estados loading/empty/error implementados.
19. Detalhe do briefing renderiza Markdown corretamente (listas, tabelas, headers).
20. Settings é somente leitura, com Alert no topo, e botão "Renovar token agora" funcional.
21. Sidebar fixa, navegação destaca rota atual, layout responsivo até 1024px (sem mobile-first nesta fase — tablets já cobertos).
22. Toggle de tema (light / dark / system) funciona, persiste em `localStorage` (chave `lanez_theme`), e o tema escolhido sobrevive a reload da página. Modo "system" reage a mudanças de `prefers-color-scheme` em tempo real.
23. Em modo escuro: backgrounds, bordas, texto e gráfico (`TokenUsageChart`) seguem a paleta correta — sem texto branco sobre branco ou cinza claro sobre cinza claro.

### Estilo
24. **Nenhum** componente de UI é desenhado do zero — todos os primitivos vêm de `@/components/ui/` (shadcn). Componentes próprios (StatusCard, BriefingCard, etc.) compõem com primitivos.
25. **Nenhum** CSS file novo além do `index.css`. Estilos via classes Tailwind.
26. **Nenhuma** biblioteca de UI alternativa (Mantine, Chakra, MUI, antd) instalada. **Nenhum** `next-themes` ou similar — tema é implementação própria conforme 6a.F.5b.
27. Cores via tokens shadcn (`bg-background`, `text-foreground`, `bg-card`, `bg-primary`, `bg-accent`, `border-border`, `text-muted-foreground`) sempre que possível — eles adaptam light/dark automaticamente. Cores literais (slate-700 etc.) só são permitidas no Recharts e devem ter variante para dark.

---

## Restrições / O que NÃO entra

- **Sem voz, sem `/voice/transcribe`, sem mic button** — Fase 6b.
- **Sem `/audit` no painel, sem audit log no backend** — Fase 7.
- **Sem edição de settings** — só leitura.
- **Sem mobile (<768px)** — desktop e tablet apenas.
- **Sem Vercel deploy** — rodar local.
- **Sem Docker para o frontend** — só `npm run dev`.
- **Sem rotas autenticadas no Storybook ou Chromatic** — fora do escopo.
- **Sem lib estado global** (Zustand, Redux, Jotai). React Context só para auth, TanStack Query para servidor.
- **Sem CSS-in-JS** (styled-components, emotion). Só Tailwind.
- **Não tocar em** `app/services/*`, `app/models/*`, `app/routers/mcp.py`, `app/routers/graph.py`, `app/routers/webhooks.py`, `alembic/versions/*`. **Nenhuma migration nova nesta fase** — backend muda apenas auth + adiciona endpoints de leitura.
- **Não otimizar performance do frontend** (code splitting, lazy loading, image optimization) — fora do escopo.
- **Não introduzir Tailwind v4** — usar 3.4 (estável).

---

## Estratégia de testes

**Backend:** mocks com `unittest.mock` + `httpx.AsyncClient` test client do FastAPI. Sem chamadas reais à Microsoft Graph ou Anthropic. Reaproveitar fixtures existentes em `tests/conftest.py`.

**Frontend:** Vitest + React Testing Library + jsdom. **Mockar `fetch` globalmente** — sem MSW, sem chamadas reais. Mockar hooks de TanStack Query com `vi.mock("@/hooks/useBriefings", () => ({ useBriefings: vi.fn() }))` quando necessário.

**Não rodar Playwright/Cypress.** Smoke tests cobrem o suficiente para esta fase.

---

## Estrutura sugerida — arquivos novos e modificados

### Backend

| Arquivo | Tipo | Issue |
|---|---|---|
| `app/dependencies.py` | MOD | 6a.B.1 (auth dual) |
| `app/routers/auth.py` | MOD | 6a.B.2, 6a.B.3 (callback dual + me + logout) |
| `app/schemas/auth.py` | MOD | 6a.B.3 (UserMeResponse) |
| `app/routers/briefings.py` | MOD | 6a.B.4 (lista paginada) |
| `app/schemas/briefing.py` | MOD | 6a.B.4 (BriefingListItem, BriefingListResponse) |
| `app/routers/status.py` | NOVO | 6a.B.5 |
| `app/schemas/status.py` | NOVO | 6a.B.5 |
| `app/main.py` | MOD | 6a.B.5 (registrar status router) |
| `tests/test_auth_dual.py` | NOVO | 6a.B.6 |
| `tests/test_auth_me_logout.py` | NOVO | 6a.B.6 |
| `tests/test_briefings_list.py` | NOVO | 6a.B.6 |
| `tests/test_status.py` | NOVO | 6a.B.6 |

### Frontend (todos NOVOS)

Toda a árvore `frontend/` da seção 6a.F.1.

Total backend: 4 novos + 5 modificados. Total frontend: ~30 arquivos novos.

---

## Instrução global de documentação

Seguir o mesmo padrão das Fases 4, 4.5 e 5: gerar bloco "Explicação — Tarefa X.Y" para cada tarefa concluída, com arquivos, trechos relevantes, justificativa e invariantes.

---

## Observação para o KIRO

Esta fase tem **alto risco de divergência em frontend**. Auditor sabe que erros comuns são:

1. **Improvisar componentes** — desenhar buttons/cards próprios em vez de usar shadcn. NÃO faça isso. Toda primitiva vem de `@/components/ui/`.
2. **Esquecer estados loading/empty/error** — toda página com dados de servidor precisa dos três. Use `LoadingSkeleton`, `EmptyState`, `ErrorState`.
3. **Inventar cores** — paleta limitada a slate/emerald/sky/amber/rose. Nada de `bg-[#3b82f6]`.
4. **Adicionar bibliotecas** — sem Zustand, sem Axios, sem Mantine, sem Framer Motion, sem dayjs (use date-fns), sem styled-components.
5. **Mexer em arquivos backend fora da Parte B** — não modifique services, modelos, migrations, MCP. Backend muda apenas auth + 3 endpoints novos.
6. **Pular tipos TypeScript** — toda interface de resposta da API tem tipo declarado. `any` é erro de revisão.
7. **Rodar suíte parcial** — após qualquer mudança no backend, rodar `pytest -x` completo. Após mudanças no frontend, `npm test` + `npm run build` para garantir TS limpo.

**Comece gerando a spec em `.kiro/specs/lanez-fase6a-painel/` (design.md, requirements.md, tasks.md)** seguindo o formato das fases anteriores. Ordem sugerida das tarefas:

1. Tarefa 1: Backend — auth dual em `dependencies.py` + testes (6a.B.1, 6a.B.6 parcial)
2. Tarefa 2: Backend — callback OAuth dual + return_url allowlist + testes (6a.B.2, 6a.B.6 parcial)
3. Tarefa 3: Backend — `/auth/me` + `/auth/logout` + schemas + testes (6a.B.3, 6a.B.6 parcial)
4. Tarefa 4: Backend — `GET /briefings` lista paginada + schemas + testes (6a.B.4)
5. Tarefa 5: Backend — `/status` router + schemas + testes (6a.B.5)
6. Tarefa 6: Frontend — setup Vite/Tailwind/shadcn + estrutura de diretórios + cliente API + queryClient + utils
7. Tarefa 7: Frontend — AuthContext + ThemeContext/ThemeToggle + ProtectedRoute + roteamento (App.tsx) + AppShell + LoginPage
8. Tarefa 8: Frontend — DashboardPage + componentes (StatusCard, TokenUsageChart) + useStatus
9. Tarefa 9: Frontend — BriefingsListPage + BriefingDetailPage + BriefingMarkdown + useBriefings + useBriefing
10. Tarefa 10: Frontend — SettingsPage + smoke tests + README + npm run build limpo

Apresente a spec para aprovação antes de implementar.
