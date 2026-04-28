# Documento de Requisitos — Lanez Fase 6a: Painel React (Somente Leitura)

## Introdução

A Fase 6a do Lanez implementa o primeiro frontend do projeto: um painel web em React que permite ao usuário autenticar via Microsoft 365 com sessão persistente via cookie HttpOnly, visualizar status das integrações no dashboard, navegar e ler briefings gerados, e consultar configurações atuais do sistema. O backend recebe 5 mudanças para suportar o painel: autenticação dual (Cookie + Bearer), callback OAuth com modo dual (redirect + JSON), endpoints de sessão (`/auth/me`, `/auth/logout`), listagem paginada de briefings (`GET /briefings`), e endpoint de métricas agregadas (`GET /status`). O frontend usa Vite + React 18 + TypeScript + Tailwind 3.4 + shadcn/ui + TanStack Query v5 + React Router v6, rodando local em `:5173` com proxy para o backend em `:8000`. Esta fase é somente leitura — sem voz, sem audit trail, sem edição de settings, sem deploy.

### Divergências de modelo detectadas (pré-flight)

Antes de redigir os requisitos, os modelos reais foram inspecionados. Divergências encontradas em relação ao briefing original:

1. **`Embedding.service`** é `String(20)`, NÃO Enum — usar a string diretamente, sem `.value`
2. **`WebhookSubscription`** NÃO possui coluna `service` — possui `resource` (`String(255)`), `subscription_id`, `client_state`, `expires_at`, `user_id`. O endpoint `/status` deve derivar o serviço a partir da string `resource` ou expor `resource` diretamente
3. **`WebhookSubscription`** NÃO possui campo `service_type`
4. O armazenamento Redis atual em `auth_microsoft` é uma STRING pura (`code_verifier`), não JSON. A migração para JSON em 6a.B.2 deve tratar ambos os formatos durante transição
5. `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/refresh")` existe em `app/dependencies.py` e deve ser removido junto com todos os callsites

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Painel**: Aplicação frontend React em `frontend/` que consome a API REST do Sistema
- **Cookie_Sessão**: Cookie HttpOnly chamado `lanez_session` contendo JWT interno, usado pelo Painel para autenticação persistente no browser
- **Auth_Dual**: Mecanismo de autenticação que aceita JWT via Cookie HttpOnly OU header Authorization Bearer, com prioridade para cookie
- **Callback_Dual**: Comportamento do `/auth/callback` que retorna redirect + Set-Cookie quando `return_url` está presente, ou JSON (`TokenResponse`) quando ausente — mantendo compatibilidade com MCP/curl
- **Return_URL**: Query parameter opcional em `/auth/microsoft` que indica a URL de retorno após autenticação OAuth; validado contra allowlist `CORS_ORIGINS`
- **BriefingListItem**: Schema reduzido de briefing para listagem — sem `content` nem telemetria de tokens
- **StatusResponse**: Schema agregado com métricas do dashboard — token expiry, webhooks, embeddings, memórias, briefings 30d, tokens 30d, config
- **shadcn_ui**: Biblioteca de componentes UI baseada em Radix + Tailwind, copiados para `frontend/src/components/ui/` via CLI
- **TanStack_Query**: Biblioteca de gerenciamento de server-state (cache, retry, refetch) usada nos hooks de dados
- **AppShell**: Layout principal do Painel com sidebar (240px) + TopBar, envolvendo rotas autenticadas
- **ProtectedRoute**: Componente que redireciona para `/login` se o usuário não estiver autenticado

## Requisitos

### Requisito R1: Autenticação Dual (Cookie + Bearer)

**User Story:** Como desenvolvedor do painel, quero que a autenticação aceite JWT via cookie HttpOnly além do header Bearer existente, para que o browser mantenha sessão persistente sem expor tokens a XSS.

#### Critérios de Aceitação

1. THE Sistema SHALL substituir `get_current_user` em `app/dependencies.py` para extrair JWT do Cookie_Sessão (`lanez_session`) OU do header `Authorization: Bearer <jwt>`, com prioridade para o cookie
2. THE Sistema SHALL remover `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/refresh")` de `app/dependencies.py` e limpar todos os callsites que importam `oauth2_scheme`
3. THE Sistema SHALL usar `Request` como parâmetro de `get_current_user` em vez de `Depends(oauth2_scheme)` para extração de token
4. WHEN ambos Cookie_Sessão e header Bearer estão presentes na requisição, THEN THE Sistema SHALL usar o token do Cookie_Sessão (cookie tem prioridade)
5. WHEN nenhum token é encontrado (nem cookie nem Bearer), THEN THE Sistema SHALL retornar HTTP 401 com detail "Não autenticado" e header `WWW-Authenticate: Bearer`
6. WHEN o JWT é inválido ou expirado, THEN THE Sistema SHALL retornar HTTP 401 com detail "Não autenticado"
7. WHEN o `user_id` do JWT não corresponde a nenhum usuário no banco, THEN THE Sistema SHALL retornar HTTP 401 com detail "Usuário não encontrado"
8. THE Sistema SHALL manter compatibilidade total com clientes MCP e curl que usam header Bearer

### Requisito R2: Callback OAuth Modo Dual

**User Story:** Como usuário do painel, quero que o fluxo OAuth redirecione de volta ao painel com cookie de sessão configurado, sem quebrar o comportamento atual para MCP/curl.

#### Critérios de Aceitação

1. THE Sistema SHALL aceitar query parameter opcional `return_url` em `GET /auth/microsoft`
2. WHEN `return_url` é fornecido, THEN THE Sistema SHALL validar que a URL começa com uma origem listada em `CORS_ORIGINS` — rejeitar com HTTP 400 "return_url não permitido" se fora da allowlist
3. THE Sistema SHALL migrar o armazenamento Redis do state OAuth de string pura para JSON: `{"code_verifier": "...", "return_url": "..."}` com TTL de 600 segundos
4. WHEN `return_url` está presente no state Redis durante o callback, THEN THE Sistema SHALL retornar `RedirectResponse` (302) para `return_url` com `Set-Cookie: lanez_session=<jwt>; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800` — flag `Secure` omitida em dev (Secure será adicionado na Fase 6c quando atrás de HTTPS)
5. WHEN `return_url` NÃO está presente no state Redis durante o callback, THEN THE Sistema SHALL manter o comportamento atual retornando `TokenResponse` JSON — compatibilidade com MCP/curl preservada
6. THE Sistema SHALL preservar o guard existente para state ausente ou expirado no Redis — HTTP 400 "state inválido ou expirado"
7. THE Sistema SHALL usar `secure=False` com comentário `# TODO Fase 6c (deploy): secure=True quando atrás de HTTPS` — NÃO condicionar por `request.url.scheme`
8. THE Sistema SHALL usar `samesite="lax"` — NÃO trocar por `"strict"` (quebraria o redirect de retorno do OAuth)

### Requisito R3: Endpoints de Sessão

**User Story:** Como painel React, quero endpoints para verificar sessão ativa e fazer logout, para que o frontend saiba se o usuário está autenticado e possa encerrar a sessão.

#### Critérios de Aceitação

1. THE Sistema SHALL expor `GET /auth/me` com `response_model=UserMeResponse` que retorna dados básicos do usuário autenticado: id (UUID), email (str), token_expires_at (datetime), last_sync_at (datetime | None), created_at (datetime)
2. THE Sistema SHALL criar schema `UserMeResponse` em `app/schemas/auth.py` com os campos id, email, token_expires_at, last_sync_at, created_at — sem substituir schemas existentes
3. THE Sistema SHALL expor `POST /auth/logout` que retorna HTTP 204 e limpa o Cookie_Sessão (`lanez_session`) via `delete_cookie` com `path="/"`
4. THE endpoint `/auth/logout` SHALL ser idempotente — sempre retorna 204 independente de haver cookie presente
5. THE endpoint `/auth/me` SHALL usar `Depends(get_current_user)` para autenticação — retorna 401 se não autenticado

### Requisito R4: Listagem Paginada de Briefings

**User Story:** Como usuário do painel, quero ver uma lista paginada dos meus briefings com busca por assunto, para navegar rapidamente entre reuniões passadas.

#### Critérios de Aceitação

1. THE Sistema SHALL expor `GET /briefings` (sem path parameter) com `response_model=BriefingListResponse` em `app/routers/briefings.py`
2. THE endpoint SHALL aceitar query parameters: `page` (int, default=1, ge=1), `page_size` (int, default=20, ge=1, le=100), `q` (str | None, default=None)
3. WHEN `q` é fornecido, THEN THE Sistema SHALL filtrar briefings onde `event_subject` contém `q` via ILIKE case-insensitive
4. THE Sistema SHALL ordenar resultados por `event_start` descendente (mais recentes primeiro)
5. THE Sistema SHALL usar statements SEPARADOS para contagem (`count_stmt`) e paginação (`paged_stmt`) — NÃO reutilizar o mesmo statement
6. THE Sistema SHALL criar schemas `BriefingListItem` e `BriefingListResponse` em `app/schemas/briefing.py` — BriefingListItem contém id, event_id, event_subject, event_start, event_end, attendees, generated_at com `model_config = {"from_attributes": True}`
7. THE BriefingListItem NÃO SHALL incluir `content` nem campos de telemetria de tokens — payload reduzido para listagem
8. THE BriefingListResponse SHALL conter campos: items (list[BriefingListItem]), total (int), page (int), page_size (int)

### Requisito R5: Endpoint de Status (Dashboard)

**User Story:** Como usuário do painel, quero ver métricas agregadas das minhas integrações num dashboard, para entender o estado atual do sistema de forma rápida.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/routers/status.py` com router `APIRouter(prefix="/status", tags=["status"])` e endpoint `GET /status` com `response_model=StatusResponse`
2. THE Sistema SHALL registrar o router de status em `app/main.py` junto aos demais routers
3. THE endpoint SHALL retornar: email do usuário, token_expires_at, token_expires_in_seconds (int calculado), last_sync_at
4. THE endpoint SHALL retornar lista de subscrições webhook do usuário — usando campo `resource` (String) do modelo WebhookSubscription, NÃO campo `service` (que não existe no modelo)
5. THE endpoint SHALL retornar contagem de embeddings agrupados por `service` (campo String(20) do modelo Embedding) — usar a string diretamente, sem `.value`
6. THE endpoint SHALL retornar contagem total de memórias do usuário
7. THE endpoint SHALL retornar contagem de briefings dos últimos 30 dias e lista dos 5 briefings mais recentes (event_id, event_subject, event_start)
8. THE endpoint SHALL retornar soma de tokens Claude consumidos nos últimos 30 dias: input_tokens, output_tokens, cache_read_tokens, cache_write_tokens — usando `func.coalesce(..., 0)` para evitar NULL
9. THE endpoint SHALL retornar configuração atual: `briefing_history_window_days` de `settings.BRIEFING_HISTORY_WINDOW_DAYS`
10. THE Sistema SHALL criar schemas `ServiceCount`, `TokenUsageBucket`, `StatusConfig` e `StatusResponse` em `app/schemas/status.py` (arquivo novo)

### Requisito R6: Testes do Backend

**User Story:** Como desenvolvedor, quero testes automatizados cobrindo as novas funcionalidades de auth dual, callback dual, sessão, listagem e status, para garantir que as mudanças não quebram o sistema existente.

#### Critérios de Aceitação

1. THE Sistema SHALL incluir teste `test_get_current_user_accepts_cookie` — request com cookie `lanez_session=<jwt>` retorna user corretamente
2. THE Sistema SHALL incluir teste `test_get_current_user_accepts_bearer` — comportamento Bearer existente preservado
3. THE Sistema SHALL incluir teste `test_get_current_user_cookie_takes_priority` — quando ambos cookie e Bearer presentes, cookie é usado
4. THE Sistema SHALL incluir teste `test_auth_callback_with_return_url_sets_cookie_and_redirects` — com `return_url` allowlisted, response é 302 com `Set-Cookie: lanez_session=...; HttpOnly`
5. THE Sistema SHALL incluir teste `test_auth_callback_without_return_url_returns_json` — comportamento JSON atual preservado
6. THE Sistema SHALL incluir teste `test_auth_microsoft_rejects_return_url_outside_allowlist` — `return_url=https://evil.com` retorna 400
7. THE Sistema SHALL incluir teste `test_auth_me_returns_user_info` — autenticado via cookie, retorna email, token_expires_at, etc
8. THE Sistema SHALL incluir teste `test_auth_logout_clears_cookie` — POST /auth/logout retorna 204 com `Set-Cookie` contendo `Max-Age=0`
9. THE Sistema SHALL incluir teste `test_briefings_list_paginates_and_filters` — cria múltiplos briefings, verifica paginação e filtro por `q`
10. THE Sistema SHALL incluir teste `test_status_aggregates_correctly` — popula DB com fixtures, verifica contagens corretas no response
11. THE suíte completa de testes (136 existentes + novos) SHALL passar sem flags `-k` ou `-x`

### Requisito R7: Setup do Frontend

**User Story:** Como desenvolvedor, quero o projeto frontend configurado com a stack decidida (Vite + React 18 + TypeScript + Tailwind 3.4 + shadcn/ui), para que o desenvolvimento do painel possa começar com a estrutura correta.

#### Critérios de Aceitação

1. THE Painel SHALL residir no diretório `frontend/` na raiz do repositório com a estrutura exata definida no briefing seção 6a.F.1
2. THE Painel SHALL usar Vite com template `react-ts`, React 18, TypeScript, Tailwind CSS 3.4 (NÃO v4) com plugin `@tailwindcss/typography`
3. THE Painel SHALL usar shadcn/ui (tema Default, Slate, CSS variables: Yes) com componentes: button, card, input, label, badge, skeleton, alert, separator, dropdown-menu, table, sonner
4. THE Painel SHALL instalar dependências exatas: `react-router-dom@6`, `@tanstack/react-query@5`, `date-fns`, `recharts`, `react-markdown`, `remark-gfm`, `clsx`, `tailwind-merge`, `class-variance-authority`, `lucide-react`
5. THE Painel SHALL configurar Vite com proxy para rotas `/auth`, `/briefings`, `/status`, `/mcp` apontando para `http://localhost:8000`
6. THE Painel SHALL configurar alias `@` para `./src` no Vite e TypeScript
7. THE Painel SHALL ter scripts npm exatos: `dev`, `build` (`tsc && vite build`), `lint`, `preview`, `test` (`vitest run`), `test:watch` (`vitest`)
8. THE Painel NÃO SHALL criar diretórios `store/`, `context/`, ou `services/` — usar `auth/` para contexto de auth e `lib/api.ts` para cliente HTTP
9. THE Painel NÃO SHALL adicionar bibliotecas extras além das listadas: sem Zustand, Axios, Mantine, next-themes, styled-components, dayjs

### Requisito R8: Autenticação e Tema no Frontend

**User Story:** Como usuário do painel, quero fazer login via Microsoft 365 com sessão persistente e alternar entre temas claro/escuro/sistema, para ter uma experiência personalizada e segura.

#### Critérios de Aceitação

1. THE Painel SHALL implementar `AuthContext` em `frontend/src/auth/AuthContext.tsx` com Provider e hook `useAuth()` expondo: user, loading, login(), logout()
2. THE Painel SHALL verificar sessão ativa via `GET /auth/me` no mount do AuthProvider — se 401, user é null (não autenticado)
3. WHEN `login()` é chamado, THEN THE Painel SHALL redirecionar para `/auth/microsoft?return_url=<origin>/dashboard` via `window.location.href`
4. WHEN `logout()` é chamado, THEN THE Painel SHALL chamar `POST /auth/logout` e limpar o estado do user
5. THE Painel SHALL implementar `ProtectedRoute` em `frontend/src/auth/ProtectedRoute.tsx` que redireciona para `/login` se o usuário não estiver autenticado
6. THE Painel SHALL implementar `ThemeContext` em `frontend/src/theme/ThemeContext.tsx` com Provider e hook `useTheme()` suportando 3 modos: light, dark, system
7. THE Painel SHALL persistir preferência de tema em `localStorage` com chave `lanez_theme`
8. THE Painel SHALL implementar `ThemeToggle` em `frontend/src/theme/ThemeToggle.tsx` usando `DropdownMenu` do shadcn/ui com 3 opções (ícones sol/lua/monitor)
9. THE Painel SHALL usar cliente HTTP em `frontend/src/lib/api.ts` com `fetch` nativo, `credentials: "include"`, e classe `ApiError` — sem axios, ky ou ofetch

### Requisito R9: Layout e Navegação

**User Story:** Como usuário do painel, quero um layout com sidebar e barra superior consistentes, para navegar facilmente entre as seções do sistema.

#### Critérios de Aceitação

1. THE Painel SHALL implementar `AppShell` em `frontend/src/components/AppShell.tsx` como layout principal com sidebar (240px) + TopBar envolvendo rotas autenticadas
2. THE Painel SHALL implementar `Sidebar` em `frontend/src/components/Sidebar.tsx` contendo: logo "Lanez", itens de navegação (Dashboard, Briefings, Configurações), botão de Logout
3. THE Painel SHALL implementar `TopBar` em `frontend/src/components/TopBar.tsx` contendo: email do usuário e componente ThemeToggle
4. THE Painel SHALL usar exclusivamente primitivos do shadcn/ui para componentes de UI — sem componentes custom-drawn
5. THE Painel SHALL usar ícones da biblioteca `lucide-react`

### Requisito R10: Páginas do Painel

**User Story:** Como usuário do painel, quero páginas de login, dashboard, listagem de briefings, detalhe de briefing e configurações, para interagir com todas as funcionalidades disponíveis.

#### Critérios de Aceitação

1. THE Painel SHALL implementar `LoginPage` em `frontend/src/pages/LoginPage.tsx` com botão de login via Microsoft 365
2. THE Painel SHALL implementar `DashboardPage` em `frontend/src/pages/DashboardPage.tsx` consumindo `GET /status` via hook `useStatus` com 7 cards: Microsoft 365 (token expiry), Webhooks, Briefings 30d, Memórias, Embeddings por serviço, Token usage chart (Recharts), Briefings recentes
3. THE Painel SHALL implementar `BriefingsListPage` em `frontend/src/pages/BriefingsListPage.tsx` consumindo `GET /briefings` via hook `useBriefings` com busca (debounce 300ms) e paginação
4. THE Painel SHALL implementar `BriefingDetailPage` em `frontend/src/pages/BriefingDetailPage.tsx` consumindo `GET /briefings/:event_id` via hook `useBriefing` com renderização Markdown via `react-markdown` + `remark-gfm` + tipografia prose do Tailwind
5. THE Painel SHALL implementar `SettingsPage` em `frontend/src/pages/SettingsPage.tsx` exibindo configurações em modo somente leitura com componente `Alert` do shadcn/ui e botão de refresh de token
6. WHILE uma página com dados do servidor está carregando, THE Painel SHALL exibir estado de loading com componente `Skeleton` do shadcn/ui via `LoadingSkeleton`
7. WHEN uma página com dados do servidor não tem dados para exibir, THEN THE Painel SHALL exibir estado vazio via componente `EmptyState`
8. IF uma requisição ao servidor falhar, THEN THE Painel SHALL exibir estado de erro via componente `ErrorState`
9. THE Painel SHALL implementar hooks TanStack Query em `frontend/src/hooks/`: `useStatus.ts`, `useBriefings.ts`, `useBriefing.ts`
10. THE Painel SHALL implementar componentes auxiliares: `StatusCard`, `TokenUsageChart` (Recharts), `BriefingCard`, `BriefingMarkdown`, `EmptyState`, `ErrorState`, `LoadingSkeleton`

### Requisito R11: Testes do Frontend

**User Story:** Como desenvolvedor, quero smoke tests mínimos para garantir que os componentes principais renderizam sem crashar e que o auth gate funciona.

#### Critérios de Aceitação

1. THE Painel SHALL configurar Vitest + React Testing Library com jsdom em `frontend/src/__tests__/setup.ts`
2. THE Painel SHALL incluir teste em `App.test.tsx` verificando que o App renderiza sem crashar
3. THE Painel SHALL incluir teste em `ProtectedRoute.test.tsx` verificando que redireciona para `/login` quando não autenticado
4. THE Painel SHALL incluir teste em `BriefingsListPage.test.tsx` verificando renderização básica
5. THE Painel SHALL incluir mínimo de 6 smoke tests no total
6. THE Painel SHALL usar `vitest run` (execução única, sem watch mode) como comando de teste padrão

### Requisito NF1: Restrições de Escopo — Sem Migrations

**User Story:** Como desenvolvedor, quero garantir que esta fase não introduza migrations de banco, para manter a estabilidade do schema existente.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL criar novas migrations Alembic — as mudanças de backend são limitadas a auth e endpoints de leitura
2. THE Sistema NÃO SHALL modificar arquivos em `app/services/*`, `app/models/*`, `app/routers/mcp.py`, `app/routers/graph.py`, `app/routers/webhooks.py`

### Requisito NF2: Restrições de Bibliotecas e UI

**User Story:** Como desenvolvedor, quero garantir que o frontend use exclusivamente as bibliotecas e componentes decididos, para manter consistência e evitar bloat.

#### Critérios de Aceitação

1. THE Painel SHALL usar exclusivamente primitivos do shadcn/ui — sem componentes custom-drawn
2. THE Painel NÃO SHALL adicionar Zustand, Axios, Mantine, next-themes, styled-components, dayjs ou qualquer biblioteca não listada no briefing
3. THE Painel SHALL usar cores via tokens CSS do shadcn/ui — cores literais apenas em Recharts com variantes para dark mode
4. THE Painel SHALL ter UI fixa em pt-BR — sem internacionalização
5. THE Painel SHALL suportar desktop e tablet (≥768px) — sem layout mobile (<768px)

### Requisito NF3: Integridade da Suíte de Testes

**User Story:** Como desenvolvedor, quero que a suíte completa de testes continue verde após as mudanças, para garantir que nenhuma funcionalidade existente foi quebrada.

#### Critérios de Aceitação

1. THE suíte de testes backend SHALL manter os 136 testes existentes verdes mais os novos testes adicionados
2. THE suíte SHALL ser executada com `pytest` sem flags `-k` ou `-x` — todos os testes devem passar
