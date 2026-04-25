# Tarefas de Implementação — Lanez Fase 1: Fundação

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

## Tarefa 1: Infraestrutura e Configuração Base

- [x] 1.1 Criar `requirements.txt` com dependências fixadas: fastapi==0.115.0, uvicorn[standard]==0.30.0, sqlalchemy[asyncio]==2.0.35, asyncpg==0.29.0, redis[hiredis]==5.1.0, httpx==0.27.0, pydantic-settings==2.5.0, cryptography==43.0.0, python-dotenv==1.0.1, pgvector==0.3.0, python-jose[cryptography]==3.3.0, alembic==1.13.0, pytest==8.3.0, pytest-asyncio==0.24.0, hypothesis==6.112.0, respx==0.21.0
- [x] 1.2 Criar `.env.example` com todas as variáveis documentadas: MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, MICROSOFT_REDIRECT_URI, DATABASE_URL, REDIS_URL, SECRET_KEY, WEBHOOK_CLIENT_STATE, CORS_ORIGINS
- [x] 1.3 Criar `Dockerfile` com Python 3.12-slim, instalação de dependências e CMD uvicorn
- [x] 1.4 Criar `docker-compose.yml` com serviços app (FastAPI, porta 8000), db (pgvector/pgvector:pg16, porta 5432, volume pgdata) e redis (redis:7-alpine, porta 6379)
- [x] 1.5 Criar `app/config.py` com Pydantic BaseSettings carregando todas as variáveis de ambiente, campos obrigatórios sem valor padrão (MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, SECRET_KEY, WEBHOOK_CLIENT_STATE), e instância singleton `settings`
- [x] 1.6 Criar `app/database.py` com create_async_engine (asyncpg), AsyncSessionLocal, função get_db() como dependency injection, e inicialização de conexão Redis via redis.asyncio

## Tarefa 2: Modelos de Dados SQLAlchemy

- [x] 2.1 Criar `app/models/__init__.py` exportando Base e todos os modelos
- [x] 2.2 Criar `app/models/user.py` com modelo User: id (UUID PK, default uuid4), email (String unique not null), microsoft_access_token (Text, criptografado), microsoft_refresh_token (Text, criptografado), token_expires_at (DateTime timezone), created_at (DateTime default utcnow), last_sync_at (DateTime nullable). Implementar criptografia/descriptografia de tokens usando Fernet com chave derivada de SECRET_KEY via PBKDF2
- [x] 2.3 Criar `app/models/cache.py` com modelo GraphCache: id (UUID PK), user_id (FK User.id), service (String enum: calendar/mail/onenote/onedrive), resource_id (String), data (JSONB), cached_at (DateTime default utcnow), expires_at (DateTime), etag (String nullable). Índice composto unique em (user_id, service, resource_id)
- [x] 2.4 Criar `app/models/webhook.py` com modelo WebhookSubscription: id (UUID PK), user_id (FK User.id), subscription_id (String unique), resource (String), client_state (String), expires_at (DateTime, indexed), created_at (DateTime default utcnow)

## Tarefa 3: Schemas Pydantic

- [x] 3.1 Criar `app/schemas/__init__.py`
- [x] 3.2 Criar `app/schemas/auth.py` com schemas: AuthRedirectResponse (authorization_url: str), TokenResponse (access_token: str, token_type: str, user_id: UUID, email: str, token_expires_at: datetime), ErrorResponse (detail: str)
- [x] 3.3 Criar `app/schemas/graph.py` com schemas: ServiceType (str Enum: calendar, mail, onenote, onedrive), GraphDataResponse (service, data, from_cache, cached_at), WebhookNotification (subscription_id, client_state, resource, change_type), WebhookSubscriptionResponse (id, subscription_id, resource, expires_at)

## Tarefa 4: Serviço de Cache Redis

- [x] 4.1 Criar `app/services/__init__.py`
- [x] 4.2 Criar `app/services/cache.py` com classe CacheService: TTL_MAP (calendar=300, mail=300, onenote=900, onedrive=900), função cache_key retornando "lanez:{user_id}:{service}", métodos async get(), set() (com TTL do serviço), invalidate() e invalidate_all()

## Tarefa 5: Serviço Microsoft Graph API

- [x] 5.1 Criar `app/services/graph.py` com classe GraphService: BASE_URL, ENDPOINTS mapeando ServiceType para paths da Graph API, httpx.AsyncClient compartilhado com timeout 30s
- [x] 5.2 Implementar método fetch_data() com fluxo: verificar cache → verificar rate limit → GET Graph API com Bearer token → tratar 401 (renovar token + retry 1x) → tratar 429 (backoff) → salvar no cache → persistir no GraphCache → retornar GraphDataResponse
- [x] 5.3 Implementar rate limiter no Redis: chave "lanez:ratelimit:{user_id}", INCR + EXPIRE com janela 900s, limite 200 req/janela
- [x] 5.4 Implementar exponential backoff: ler Retry-After header se presente, senão backoff 1s→2s→4s, máximo 3 tentativas, logar cada ocorrência de rate limiting

## Tarefa 6: Serviço de Webhooks

- [x] 6.1 Criar `app/services/webhook.py` com classe WebhookService: SUBSCRIPTION_RESOURCES mapeando ServiceType para recursos Graph, método create_subscriptions() que cria subscrições para os 4 serviços via POST Graph API /subscriptions com changeType, notificationUrl, resource, expirationDateTime (4230 min), clientState
- [x] 6.2 Implementar método process_notification(): validar clientState contra WEBHOOK_CLIENT_STATE, mapear resource para ServiceType e user_id, invalidar cache via CacheService
- [x] 6.3 Implementar método renew_subscriptions(): consultar subscrições com expires_at < now + 60min, PATCH Graph API /subscriptions/{id}, atualizar expires_at no banco, se falhar criar nova subscrição

## Tarefa 7: Router de Autenticação OAuth 2.0

- [x] 7.1 Criar `app/routers/__init__.py`
- [x] 7.2 Criar `app/routers/auth.py` com endpoint GET /auth/microsoft: gerar code_verifier (32 bytes base64url), calcular code_challenge (SHA256 + base64url), gerar state (16 bytes hex), armazenar code_verifier e state no Redis (TTL 10min), redirecionar para endpoint de autorização Entra ID com todos os parâmetros (client_id, response_type=code, redirect_uri, scope com 6 escopos, code_challenge, code_challenge_method=S256, state)
- [x] 7.3 Implementar endpoint GET /auth/callback: validar state contra Redis, verificar parâmetro error (retornar 400), trocar code por tokens via POST token endpoint com code_verifier, buscar email via GET /me, criar/atualizar User com tokens criptografados, emitir JWT interno assinado com SECRET_KEY contendo user_id e exp, disparar criação de subscrições webhook como background task, retornar TokenResponse com access_token JWT
- [x] 7.4 Implementar endpoint POST /auth/refresh: obter user_id do JWT via dependency get_current_user, buscar User, descriptografar refresh_token, POST token endpoint com grant_type=refresh_token, atualizar tokens criptografados e token_expires_at, emitir novo JWT, retornar 401 se falhar

## Tarefa 8: Router de Webhooks

- [x] 8.1 Criar `app/routers/webhooks.py` com endpoint POST /webhooks/graph: se validationToken presente responder HTTP 200 text/plain com o token, senão parsear notificações e chamar WebhookService.process_notification() para cada, retornar HTTP 202
- [x] 8.2 Implementar endpoint GET /webhooks/subscriptions: protegido por dependency get_current_user (JWT), buscar subscrições ativas do usuário autenticado, retornar lista de WebhookSubscriptionResponse

## Tarefa 9: Routers de Dados Graph API

- [x] 9.1 Criar `app/routers/graph.py` com endpoints GET /me/events, GET /me/messages, GET /me/onenote/pages, GET /me/drive/root/children, cada um protegido por dependency get_current_user (JWT), chamando GraphService.fetch_data() com o ServiceType correspondente e retornando GraphDataResponse

## Tarefa 10: Aplicação Principal e Integração

- [x] 10.1 Criar `app/__init__.py`
- [x] 10.2 Criar `app/main.py` com FastAPI app, lifespan async context manager (startup: inicializar Redis, criar tabelas, iniciar asyncio.create_task para renewal_loop; shutdown: cancelar task de renovação, fechar Redis, fechar engine), registrar routers (auth, webhooks, graph), middleware CORS configurável via settings.CORS_ORIGINS.split(",") — não usar allow_origins=["*"] fixo
- [x] 10.3 Implementar renewal_loop como asyncio.Task no lifespan (não BackgroundTasks que é request-scoped): loop infinito que chama webhook_service.renew_subscriptions() a cada 30 minutos via asyncio.sleep(1800), cancelado no shutdown

## Tarefa 11: Testes de Propriedade

- [x] 11.1 Escrever property-based test para round-trip de criptografia de tokens: gerar strings aleatórias, criptografar com Fernet/PBKDF2, descriptografar, verificar que valor original é preservado (Propriedade 1)
- [x] 11.2 Escrever property-based test para TTL por serviço: gerar ServiceType aleatório, verificar que get_ttl retorna 300 para calendar/mail e 900 para onenote/onedrive (Propriedade 2)
- [x] 11.3 Escrever property-based test para formato de chave de cache: gerar UUIDs e ServiceTypes aleatórios, verificar formato "lanez:{user_id}:{service}" (Propriedade 3)
- [x] 11.4 Escrever property-based test para PKCE: gerar múltiplos pares code_verifier/code_challenge, verificar que base64url(sha256(verifier)) == challenge (Propriedade 4)
- [x] 11.5 Escrever property-based test para validação de clientState: gerar strings aleatórias, verificar que apenas o valor configurado é aceito (Propriedade 5)
- [x] 11.6 Escrever property-based test para exponential backoff: gerar números de tentativa 1-3, verificar que tempo == 2^(n-1) segundos (Propriedade 6)
- [x] 11.7 Escrever property-based test para state OAuth único: gerar múltiplos states, verificar que todos são distintos (Propriedade 8)

## Tarefa 12: Testes de Casos de Borda

- [x] 12.1 Escrever teste para state OAuth inválido no callback: enviar callback com state diferente, verificar HTTP 400 (Caso de Borda 1)
- [x] 12.2 Escrever teste para erro do Entra ID no callback: enviar callback com error=access_denied, verificar HTTP 400 (Caso de Borda 2)
- [x] 12.3 Escrever teste para refresh token expirado: tentar refresh com token inválido, verificar HTTP 401 (Caso de Borda 3)
- [x] 12.4 Escrever teste para token expirado durante consulta Graph: mock 401 na primeira chamada e 200 na segunda, verificar retry e dados retornados (Caso de Borda 4)
- [x] 12.5 Escrever teste para clientState inválido em webhook: enviar notificação com clientState incorreto, verificar HTTP 403 (Caso de Borda 5)
- [x] 12.6 Escrever teste para falha na renovação de subscrição: mock PATCH retornando erro, verificar que nova subscrição é criada (Caso de Borda 6)
- [x] 12.7 Escrever teste para email duplicado: criar User, criar outro com mesmo email, verificar upsert (Caso de Borda 7)
- [x] 12.8 Escrever teste para integridade referencial: inserir GraphCache e WebhookSubscription com user_id inexistente, verificar erro (Caso de Borda 8)
- [x] 12.9 Escrever teste para variável de ambiente ausente: instanciar Settings sem MICROSOFT_CLIENT_ID, verificar ValidationError (Caso de Borda 9)

## Tarefa 13: Autenticação JWT para Endpoints de Dados

- [x] 13.1 Criar `app/dependencies.py` com função create_access_token(user_id) que emite JWT assinado com SECRET_KEY (algoritmo HS256) contendo user_id e exp (7 dias)
- [x] 13.2 Implementar dependency get_current_user: extrair JWT do header Authorization (Bearer), decodificar com SECRET_KEY, buscar User no banco pelo user_id do payload, retornar HTTP 401 se JWT inválido/expirado ou usuário não encontrado
- [x] 13.3 Integrar get_current_user como Depends() nos endpoints: GET /me/events, GET /me/messages, GET /me/onenote/pages, GET /me/drive/root/children, GET /webhooks/subscriptions, POST /auth/refresh

## Tarefa 14: Alembic — Migrations de Banco de Dados

- [x] 14.1 Inicializar Alembic com `alembic init alembic`, configurar alembic/env.py para usar asyncpg e importar Base.metadata dos modelos
- [x] 14.2 Criar migration inicial para as 3 tabelas: User, GraphCache, WebhookSubscription
