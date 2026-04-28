# Tarefas de Implementação — Lanez Fase 6a: Painel React (Somente Leitura)

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

## Tarefa 1: Backend — Auth Dual (Cookie + Bearer) em `app/dependencies.py`

- [x] 1.1 Pré-flight — rodar `grep -rn "oauth2_scheme" app/ tests/` e listar todos os callsites. Inspecionar modelos (`app/models/embedding.py`, `app/models/webhook.py`, `app/models/memory.py`, `app/models/briefing.py`) para confirmar nomes reais de colunas. Reportar divergências encontradas no bloco de explicação antes de prosseguir
  - Confirmar: `Embedding.service` é `String(20)` (sem `.value`), `WebhookSubscription` tem `resource` (não `service`), `Memory.user_id` existe, `Briefing` tem todos os campos de tokens
  - _Requisitos: R1.2, R5.4, R5.5_

- [x] 1.2 Reescrever `app/dependencies.py` — remover `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/refresh")`, remover import de `OAuth2PasswordBearer`. Adicionar import de `Request`. Implementar `_extract_token(request: Request) -> str | None` (cookie `lanez_session` tem prioridade sobre header `Authorization: Bearer`) e novo `get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User` conforme design seção 1
  - Constantes: `_COOKIE_NAME = "lanez_session"`, `_JWT_ALGORITHM = "HS256"`
  - 401 com detail "Não autenticado" se token ausente/inválido/expirado
  - 401 com detail "Usuário não encontrado" se user_id não existe no banco
  - Header `WWW-Authenticate: Bearer` em ambos os 401
  - _Requisitos: R1.1, R1.3, R1.4, R1.5, R1.6, R1.7_

- [x] 1.3 Limpar callsites de `oauth2_scheme` — remover imports e `Depends(oauth2_scheme)` em todos os arquivos que importavam de `app.dependencies`. Verificar que nenhum arquivo referencia `oauth2_scheme` após a limpeza
  - _Requisitos: R1.2, R1.8_

- [x] 1.4 Criar `tests/test_auth_dual.py` com testes unitários:
  - `test_get_current_user_accepts_cookie` — request com cookie `lanez_session=<jwt>` retorna user
  - `test_get_current_user_accepts_bearer` — request com header `Authorization: Bearer <jwt>` retorna user (comportamento existente preservado)
  - `test_get_current_user_cookie_takes_priority` — quando ambos cookie e Bearer presentes com tokens diferentes, cookie é usado
  - `test_get_current_user_no_token_returns_401` — sem credenciais retorna 401
  - _Requisitos: R6.1, R6.2, R6.3_

- [x]* 1.5 Criar `tests/test_property_auth_dual.py` com property test `test_property_extract_token_cookie_priority` — Hypothesis com `@settings(max_examples=100)`. Gerar pares de tokens aleatórios (cookie_token, bearer_token) e verificar que `_extract_token` sempre retorna cookie_token quando ambos presentes, bearer_token quando apenas Bearer presente, None quando nenhum presente
  - **Propriedade 1: Extração dual de token — cookie tem prioridade**
  - **Valida: Requisitos R1.1, R1.4, R1.8**

- [x] 1.6 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 136 existentes + novos verdes
  - _Requisitos: R6.11, NF3.1, NF3.2_

## Tarefa 2: Backend — Callback OAuth Dual + return_url allowlist + Redis JSON

- [x] 2.1 Adicionar função `_is_allowed_return_url(url: str) -> bool` em `app/routers/auth.py` — valida que `url` começa com pelo menos uma origem listada em `settings.CORS_ORIGINS` (separado por vírgula). Retorna `False` para qualquer URL fora da allowlist
  - _Requisitos: R2.2_

- [x] 2.2 Modificar `auth_microsoft` em `app/routers/auth.py` — aceitar `return_url: str | None = Query(default=None)`. Se `return_url` fornecido, validar contra `_is_allowed_return_url`; se inválido, `raise HTTPException(400, "return_url não permitido")`. Migrar Redis de string pura para JSON: `json.dumps({"code_verifier": code_verifier, "return_url": return_url})` com TTL 600s. Adicionar `import json` no topo
  - _Requisitos: R2.1, R2.2, R2.3_

- [x] 2.3 Modificar `auth_callback` em `app/routers/auth.py` — parsear JSON do Redis (`json.loads(raw)`), extrair `code_verifier = state_data["code_verifier"]`. Preservar guard de state inválido/expirado. Após emitir JWT (`internal_jwt = _create_jwt(str(user.id))`), bifurcar: se `state_data.get("return_url")` → `RedirectResponse(url=return_url, status_code=302)` com `set_cookie(key="lanez_session", value=internal_jwt, max_age=604800, httponly=True, samesite="lax", secure=False, path="/")` + comentário `# TODO Fase 6c (deploy): secure=True quando atrás de HTTPS`; sem return_url → `TokenResponse` JSON (legado). Adicionar import de `Response` do FastAPI
  - _Requisitos: R2.3, R2.4, R2.5, R2.6, R2.7, R2.8_

- [x] 2.4 Adicionar testes em `tests/test_auth_dual.py`:
  - `test_auth_callback_with_return_url_sets_cookie_and_redirects` — passa `return_url` allowlisted, response é 302 com `Set-Cookie: lanez_session=...; HttpOnly`
  - `test_auth_callback_without_return_url_returns_json` — comportamento JSON atual preservado (TokenResponse)
  - `test_auth_microsoft_rejects_return_url_outside_allowlist` — `return_url=https://evil.com` retorna 400
  - _Requisitos: R6.4, R6.5, R6.6_

- [x]* 2.5 Criar ou estender `tests/test_property_auth_dual.py` com property test `test_property_is_allowed_return_url` — Hypothesis com `@settings(max_examples=100)`. Gerar URLs aleatórias e lista de origens permitidas, verificar que a função retorna True sse a URL começa com pelo menos uma origem da lista
  - **Propriedade 2: Validação de allowlist de return_url**
  - **Valida: Requisito R2.2**

- [x] 2.6 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed"
  - _Requisitos: R6.11, NF3.1, NF3.2_

## Tarefa 3: Backend — Endpoints de Sessão (`/auth/me` + `/auth/logout`)

- [x] 3.1 Adicionar schema `UserMeResponse` em `app/schemas/auth.py` — campos: `id` (UUID), `email` (str), `token_expires_at` (datetime), `last_sync_at` (datetime | None), `created_at` (datetime). NÃO substituir schemas existentes (`AuthRedirectResponse`, `TokenResponse`, `ErrorResponse`)
  - _Requisitos: R3.1, R3.2_

- [x] 3.2 Adicionar endpoint `GET /auth/me` em `app/routers/auth.py` — `response_model=UserMeResponse`, usa `Depends(get_current_user)`. Retorna `UserMeResponse` com dados do usuário autenticado. Importar `UserMeResponse` de `app.schemas.auth`
  - _Requisitos: R3.1, R3.5_

- [x] 3.3 Adicionar endpoint `POST /auth/logout` em `app/routers/auth.py` — retorna `Response(status_code=204)` com `response.delete_cookie(key="lanez_session", path="/")`. Idempotente — sempre 204. Importar `Response` de `fastapi` (se não importado)
  - _Requisitos: R3.3, R3.4_

- [x] 3.4 Adicionar testes em `tests/test_auth_dual.py`:
  - `test_auth_me_returns_user_info` — autenticado via cookie, retorna email, token_expires_at, id, etc
  - `test_auth_logout_clears_cookie` — POST /auth/logout retorna 204 com `Set-Cookie` contendo `Max-Age=0`
  - _Requisitos: R6.7, R6.8_

- [x] 3.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed"
  - _Requisitos: R6.11, NF3.1, NF3.2_

## Tarefa 4: Backend — `GET /briefings` lista paginada

- [x] 4.1 Adicionar schemas `BriefingListItem` e `BriefingListResponse` em `app/schemas/briefing.py` — NÃO substituir `BriefingResponse` existente. `BriefingListItem`: id (UUID), event_id (str), event_subject (str), event_start (datetime), event_end (datetime), attendees (list[str]), generated_at (datetime), `model_config = {"from_attributes": True}`. `BriefingListResponse`: items (list[BriefingListItem]), total (int), page (int), page_size (int). SEM campo `content` nem tokens na listagem
  - _Requisitos: R4.6, R4.7, R4.8_

- [x] 4.2 Adicionar endpoint `GET /briefings` (sem path param) em `app/routers/briefings.py` — `response_model=BriefingListResponse`. Parâmetros: `page` (int, default=1, ge=1), `page_size` (int, default=20, ge=1, le=100), `q` (str | None, default=None). Filtro ILIKE `%q%` em `event_subject` quando `q` fornecido. Statements SEPARADOS para `count_stmt` e `paged_stmt`. Ordenação `event_start.desc()`. Importar `func`, `select`, `Query` e schemas necessários
  - _Requisitos: R4.1, R4.2, R4.3, R4.4, R4.5_

- [x] 4.3 Criar `tests/test_briefings_list.py` com teste `test_briefings_list_paginates_and_filters` — criar múltiplos briefings (≥25) no DB de teste, verificar paginação (page=2, page_size=10), verificar filtro por `q`, verificar ordenação por event_start desc, verificar que `total` reflete contagem correta
  - _Requisitos: R6.9_

- [x]* 4.4 Criar `tests/test_property_briefings_list.py` com property tests:
  - `test_property_briefings_pagination_invariants` — Hypothesis com `@settings(max_examples=100)`. Para N briefings e quaisquer page/page_size válidos, verificar: (a) `total == N`, (b) `len(items) == min(page_size, max(0, N - (page-1)*page_size))`, (c) items ordenados por event_start desc
    - **Propriedade 3: Invariantes de paginação de briefings**
    - **Valida: Requisitos R4.2, R4.4, R4.8**
  - `test_property_briefings_filter_ilike` — Hypothesis com `@settings(max_examples=100)`. Para conjunto de briefings e string de busca `q`, todos os items retornados contêm `q` (case-insensitive) em event_subject, e nenhum briefing sem `q` aparece nos resultados
    - **Propriedade 4: Filtro ILIKE retorna apenas briefings correspondentes**
    - **Valida: Requisito R4.3**

- [x] 4.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed"
  - _Requisitos: R6.11, NF3.1, NF3.2_

## Tarefa 5: Backend — `GET /status` (dashboard)

- [x] 5.1 Criar `app/schemas/status.py` com schemas: `ServiceCount` (service: str, count: int), `WebhookInfo` (resource: str, expires_at: datetime), `RecentBriefing` (event_id: str, event_subject: str, event_start: datetime), `TokenUsageBucket` (input: int, output: int, cache_read: int, cache_write: int), `StatusConfig` (briefing_history_window_days: int), `StatusResponse` (user_email: str, token_expires_at: datetime, token_expires_in_seconds: int, last_sync_at: datetime | None, webhook_subscriptions: list[WebhookInfo], embeddings_by_service: list[ServiceCount], memories_count: int, briefings_count_30d: int, recent_briefings: list[RecentBriefing], tokens_30d: TokenUsageBucket, config: StatusConfig)
  - _Requisitos: R5.10_

- [x] 5.2 Criar `app/routers/status.py` com endpoint `GET /status` (`response_model=StatusResponse`) — agregar métricas do usuário autenticado. ATENÇÃO às divergências de modelo:
  - `Embedding.service` é `String(20)` — usar `row[0]` diretamente no `ServiceCount`, SEM `.value`
  - `WebhookSubscription` tem `resource` (String(255)), NÃO `service` — usar `WebhookInfo(resource=w.resource, expires_at=w.expires_at)`
  - Usar `func.coalesce(..., 0)` em somas de tokens para evitar NULL
  - `token_expires_in_seconds` calculado como `int((user.token_expires_at - now).total_seconds())`
  - Importar todos os modelos necessários: `User`, `Briefing`, `Embedding`, `Memory`, `WebhookSubscription`
  - _Requisitos: R5.1, R5.3, R5.4, R5.5, R5.6, R5.7, R5.8, R5.9_

- [x] 5.3 Registrar router em `app/main.py`: `from app.routers.status import router as status_router` + `app.include_router(status_router)`
  - _Requisitos: R5.2_

- [x] 5.4 Criar `tests/test_status.py` com testes:
  - `test_status_aggregates_correctly` — popula DB com fixtures (user, webhooks, embeddings, memórias, briefings), GET /status, verificar contagens corretas em todos os campos
  - `test_status_uses_resource_not_service` — verificar que webhook_subscriptions expõe campo `resource` (não `service`)
  - `test_status_embedding_service_no_dot_value` — verificar que embeddings_by_service usa string direta do campo `service`, sem `.value`
  - _Requisitos: R6.10, R5.4, R5.5_

- [x] 5.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem final do backend: "N passed, M failed". Meta: 136 existentes + todos os novos verdes
  - _Requisitos: R6.11, NF3.1, NF3.2_

## Tarefa 6: Frontend — Setup (Vite + Tailwind + shadcn/ui + estrutura)

- [x] 6.1 Criar projeto Vite em `frontend/` com template `react-ts`. Executar `npm create vite@latest . -- --template react-ts` dentro de `frontend/`
  - _Requisitos: R7.1, R7.2_

- [x] 6.2 Instalar dependências de produção e desenvolvimento:
  - Tailwind 3.4 + postcss + autoprefixer + @tailwindcss/typography: `npm install -D tailwindcss@3.4 postcss autoprefixer @tailwindcss/typography`
  - Roteamento + dados + utilitários: `npm install react-router-dom@6 @tanstack/react-query@5 date-fns recharts react-markdown remark-gfm clsx tailwind-merge class-variance-authority lucide-react`
  - _Requisitos: R7.4, NF2.2_

- [x] 6.3 Inicializar shadcn/ui (`npx shadcn@latest init` — Default, Slate, CSS variables: Yes). Adicionar componentes: `npx shadcn@latest add button card input label badge skeleton alert separator dropdown-menu table sonner`
  - _Requisitos: R7.3_

- [x] 6.4 Configurar `frontend/vite.config.ts` com: proxy para `/auth`, `/briefings`, `/status`, `/mcp` apontando para `http://localhost:8000`; alias `@` → `./src`; test config com `environment: "jsdom"`, `setupFiles: ["./src/__tests__/setup.ts"]`, `globals: true`. Plugin `@vitejs/plugin-react`
  - _Requisitos: R7.5, R7.6_

- [x] 6.5 Configurar `frontend/tailwind.config.js` com `darkMode: "class"` e plugin `@tailwindcss/typography`. Content paths: `["./index.html", "./src/**/*.{ts,tsx}"]`
  - _Requisitos: R7.2_

- [x] 6.6 Criar utilitários base:
  - `frontend/src/lib/api.ts` — cliente fetch com `credentials: "include"`, classe `ApiError(status, detail)`, métodos `api.get<T>` e `api.post<T>`. Response 204 retorna `undefined`. NÃO usar axios/ky/ofetch
  - `frontend/src/lib/queryClient.ts` — `new QueryClient` com defaults (retry, staleTime)
  - `frontend/src/lib/utils.ts` — função `cn()` do shadcn (clsx + tailwind-merge)
  - _Requisitos: R8.9, R7.8_

- [x] 6.7 Criar estrutura de diretórios conforme 6a.F.1: `src/auth/`, `src/theme/`, `src/hooks/`, `src/components/`, `src/pages/`, `src/__tests__/`. NÃO criar `src/store/`, `src/context/`, `src/services/`
  - _Requisitos: R7.1, R7.8_

- [x] 6.8 Atualizar `frontend/package.json` scripts: `"dev": "vite"`, `"build": "tsc && vite build"`, `"lint": "eslint . --ext ts,tsx"`, `"preview": "vite preview"`, `"test": "vitest run"`, `"test:watch": "vitest"`
  - _Requisitos: R7.7_

- [x] 6.9 Instalar dependências de teste: `npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitejs/plugin-react`
  - _Requisitos: R11.1_

## Tarefa 7: Frontend — Auth + Tema + Layout + Login

- [x] 7.1 Criar `frontend/src/auth/AuthContext.tsx` — `AuthProvider` + hook `useAuth()`. Estado: `user` (User | null), `loading` (boolean). No mount, verifica sessão via `GET /auth/me`; se 401, `user = null`. `login()` redireciona para `/auth/microsoft?return_url=<origin>/dashboard` via `window.location.href`. `logout()` chama `POST /auth/logout` e limpa estado
  - _Requisitos: R8.1, R8.2, R8.3, R8.4_

- [x] 7.2 Criar `frontend/src/auth/ProtectedRoute.tsx` — se `loading` → renderiza `<div className="min-h-screen bg-background" />` (sem Skeleton — evita flash fora do AppShell durante a verificação inicial de sessão); se `!user` → `Navigate to="/login" replace`; se `user` → `Outlet`
  - _Requisitos: R8.5_

- [x] 7.3 Criar `frontend/src/theme/ThemeContext.tsx` — `ThemeProvider` + hook `useTheme()` retornando `{ theme, setTheme, resolvedTheme }`. `theme: "light" | "dark" | "system"` é a preferência salva; `resolvedTheme: "light" | "dark"` é o valor efetivo após resolver `system` via `window.matchMedia("(prefers-color-scheme: dark)")`. Persiste `theme` em `localStorage` com chave `lanez_theme`. Aplica classe `dark` no `<html>` conforme `resolvedTheme`. Reage a mudanças de `prefers-color-scheme` em tempo real apenas quando `theme === "system"`
  - _Requisitos: R8.6, R8.7_

- [x] 7.4 Criar `frontend/src/theme/ThemeToggle.tsx` — `DropdownMenu` do shadcn/ui com 3 opções: Sol (light), Lua (dark), Monitor (system). Ícones: `Sun`, `Moon`, `Monitor` de `lucide-react`
  - _Requisitos: R8.8_

- [x] 7.5 Criar `frontend/src/components/AppShell.tsx` — layout com sidebar (`w-60` / 240px) + TopBar + `<Outlet>`. Criar `Sidebar.tsx` com logo "Lanez", nav items (Dashboard `/dashboard`, Briefings `/briefings`, Configurações `/settings`), botão Logout no rodapé. Ícones: `LayoutDashboard`, `FileText`, `Settings`, `LogOut` de `lucide-react`. Criar `TopBar.tsx` com email do usuário (via `useAuth`) + `ThemeToggle` à direita
  - _Requisitos: R9.1, R9.2, R9.3, R9.4, R9.5_

- [x] 7.6 Criar `frontend/src/pages/LoginPage.tsx` — Card centralizado com logo "Lanez", descrição, botão "Entrar com Microsoft 365" que chama `login()`. Se já autenticado → `Navigate to="/dashboard"`
  - _Requisitos: R10.1_

- [x] 7.7 Criar `frontend/src/App.tsx` — `ThemeProvider` > `QueryClientProvider` > `BrowserRouter` > `AuthProvider` > `Routes`. Rotas: `/login` (LoginPage), `/` → redirect `/dashboard`, `/dashboard` (DashboardPage), `/briefings` (BriefingsListPage), `/briefings/:eventId` (BriefingDetailPage), `/settings` (SettingsPage) — todas protegidas via `ProtectedRoute` + `AppShell`. Adicionar `Toaster` do sonner
  - _Requisitos: R9.1, R10.1_

- [x] 7.8 Criar `frontend/src/main.tsx` — entry point montando `<App />` em `#root`. Importar `index.css`
  - _Requisitos: R7.1_

## Tarefa 8: Frontend — Dashboard

- [ ] 8.1 Criar `frontend/src/hooks/useStatus.ts` — TanStack Query hook para `GET /status`. `staleTime: 30_000` (30s). Retorna `UseQueryResult<StatusResponse>`
  - _Requisitos: R10.9_

- [ ] 8.2 Criar `frontend/src/components/StatusCard.tsx` — Card do shadcn/ui com props: `title` (string), `value` (string | number), `description?` (string), `icon?` (ReactNode)
  - _Requisitos: R10.2, R10.10_

- [ ] 8.3 Criar `frontend/src/components/TokenUsageChart.tsx` — Recharts `BarChart` com 4 barras (input, output, cache_read, cache_write). Consumir `useTheme()` (campo `resolvedTheme`) e selecionar paleta: light → input `#334155` (slate-700), output `#64748b` (slate-500), cache_read `#10b981` (emerald-500), cache_write `#0ea5e9` (sky-500); dark → input `#cbd5e1` (slate-300), output `#94a3b8` (slate-400), cache_read `#34d399` (emerald-400), cache_write `#38bdf8` (sky-400)
  - _Requisitos: R10.2, R10.10_

- [ ] 8.4 Criar componentes de estado reutilizáveis:
  - `frontend/src/components/EmptyState.tsx` — props: title, description?, icon?
  - `frontend/src/components/ErrorState.tsx` — Alert do shadcn/ui com mensagem e botão retry opcional
  - `frontend/src/components/LoadingSkeleton.tsx` — Skeleton do shadcn/ui repetido `count` vezes
  - _Requisitos: R10.6, R10.7, R10.8, R10.10_

- [ ] 8.5 Criar `frontend/src/pages/DashboardPage.tsx` — consome `useStatus()`. Grid de 7 cards:
  - Microsoft 365 (token expiry countdown via `date-fns`)
  - Webhooks (count + lista resource)
  - Briefings 30d (count)
  - Memórias (count)
  - Embeddings por serviço (Table do shadcn/ui com service: count)
  - Token usage chart (Recharts via `TokenUsageChart`)
  - Briefings recentes (lista com links para `/briefings/{event_id}`)
  - Estados: loading (grid de Skeleton), error (ErrorState com retry via refetch)
  - _Requisitos: R10.2, R10.6, R10.8_

## Tarefa 9: Frontend — Briefings (lista + detalhe)

- [ ] 9.1 Criar `frontend/src/hooks/useBriefings.ts` — TanStack Query hook para `GET /briefings` com params: `page`, `pageSize`, `q`. Importar `keepPreviousData` de `@tanstack/react-query` e usar `placeholderData: keepPreviousData` para evitar flicker para skeleton ao trocar de página ou digitar na busca. `staleTime: 30_000`. Construir o path via `URLSearchParams`
  - _Requisitos: R10.9_

- [ ] 9.2 Criar `frontend/src/hooks/useBriefing.ts` — TanStack Query hook para `GET /briefings/:eventId`. Retorna `UseQueryResult<BriefingResponse>`
  - _Requisitos: R10.9_

- [ ] 9.3 Criar `frontend/src/components/BriefingCard.tsx` — Card com `event_subject`, `event_start` (formatado via `date-fns`), `attendees` (Badge do shadcn/ui), link para `/briefings/{event_id}`
  - _Requisitos: R10.10_

- [ ] 9.4 Criar `frontend/src/components/BriefingMarkdown.tsx` — `react-markdown` + `remark-gfm` + `className="prose prose-slate dark:prose-invert max-w-none"` (Tailwind typography)
  - _Requisitos: R10.4, R10.10_

- [ ] 9.5 Criar `frontend/src/pages/BriefingsListPage.tsx` — consome `useBriefings()`. Input de busca com debounce 300ms (via `setTimeout`), lista de `BriefingCard`, paginação com botões Anterior/Próximo + "Página X de Y". Estados: loading (5× Skeleton h-24), empty ("Nenhum briefing encontrado" via EmptyState), error (ErrorState com retry)
  - _Requisitos: R10.3, R10.6, R10.7, R10.8_

- [ ] 9.6 Criar `frontend/src/pages/BriefingDetailPage.tsx` — consome `useBriefing(eventId)` via `useParams`. Cabeçalho com subject, data (date-fns), attendees (Badge). Telemetria de tokens. Separator do shadcn/ui. `BriefingMarkdown` com conteúdo. Estados: loading (Skeleton), 404 (EmptyState "Briefing não encontrado"), error (ErrorState)
  - _Requisitos: R10.4, R10.6, R10.7, R10.8_

## Tarefa 10: Frontend — Settings + Testes + README + Build

- [ ] 10.1 Criar `frontend/src/pages/SettingsPage.tsx` — consome `useStatus()`. Cards read-only: janela histórica (`briefing_history_window_days`), email do usuário, última sincronização, token Microsoft (com botão "Renovar token agora" via `POST /auth/refresh` + toast Sonner). Alert do shadcn/ui no topo: "Configurações somente leitura nesta versão". Estados: loading (Skeleton), error (ErrorState)
  - _Requisitos: R10.5, R10.6, R10.8_

- [ ] 10.2 Criar `frontend/src/__tests__/setup.ts` — `import "@testing-library/jest-dom"`, mock global `fetch` via `vi.fn()`
  - _Requisitos: R11.1_

- [ ] 10.3 Criar smoke tests (mínimo 6 testes):
  - `frontend/src/__tests__/App.test.tsx` — App renderiza sem crashar
  - `frontend/src/__tests__/ProtectedRoute.test.tsx` — redireciona para `/login` quando não autenticado + renderiza conteúdo quando autenticado
  - `frontend/src/__tests__/BriefingsListPage.test.tsx` — página renderiza com dados mockados
  - `frontend/src/__tests__/LoginPage.test.tsx` — LoginPage renderiza botão de login
  - `frontend/src/__tests__/ThemeContext.test.tsx` — `setTheme("dark")` adiciona classe `dark` em `document.documentElement` e persiste em `localStorage` com chave `lanez_theme`. Limpar `document.documentElement.classList` e `localStorage` no `beforeEach`
  - _Requisitos: R11.2, R11.3, R11.4, R11.5_

- [ ] 10.4 Criar `frontend/README.md` conforme seção 6a.F.11 do briefing — instruções de setup, scripts disponíveis, estrutura de diretórios, decisões técnicas
  - _Requisitos: R7.1_

- [x] 10.5 Rodar `npm run build` (`tsc && vite build`) em `frontend/`. Verificar saída do `tsc` — zero erros E zero warnings. Verificar saída do `vite build` — bundle gerado em `frontend/dist/` sem erros de Rollup
  - _Requisitos: R7.7_

- [x] 10.6 Rodar `npm test` (`vitest run`) em `frontend/` — todos os smoke tests devem passar
  - _Requisitos: R11.5, R11.6_

## Checkpoint Final

- [ ] 11. Checkpoint final — Garantir que toda a suíte de testes passa
  - Rodar `pytest` no backend (sem `-k`, sem `-x`) — 136 existentes + todos os novos devem estar verdes
  - Rodar `npm test` no frontend — todos os smoke tests devem passar
  - Verificar que nenhum arquivo em `app/services/*`, `app/models/*`, `app/routers/mcp.py`, `app/routers/graph.py`, `app/routers/webhooks.py` foi modificado (exceto imports de `get_current_user` se necessário)
  - Verificar que nenhuma migration Alembic foi criada
  - Verificar via `grep -rn "oauth2_scheme" app/ tests/` que retorna 0 ocorrências em arquivos `.py` (cache `.pyc` pode aparecer e será limpo automaticamente). Se aparecer qualquer callsite remanescente, voltar à Tarefa 1.3
  - Se houver dúvidas ou falhas, perguntar ao usuário antes de prosseguir
  - _Requisitos: NF1.1, NF1.2, NF3.1, NF3.2_

## Notas

- Tarefas 1–5 são backend e devem ser completadas e testadas antes de iniciar o frontend (Tarefas 6–10)
- Tarefas marcadas com `*` são opcionais (property tests) e podem ser puladas para MVP mais rápido
- Cada tarefa backend termina com execução completa do `pytest` para garantir regressão zero
- Todas as referências a requisitos apontam para o documento `requirements.md` da Fase 6a
- Propriedades formais de corretude estão definidas no documento `design.md` da Fase 6a
- UI fixa em pt-BR — sem internacionalização
