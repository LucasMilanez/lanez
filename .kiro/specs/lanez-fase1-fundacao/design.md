# Documento de Design — Lanez Fase 1: Fundação

## Visão Geral

Este documento descreve a arquitetura e o design técnico da Fase 1 do Lanez. A aplicação é construída com FastAPI (assíncrono), PostgreSQL com asyncpg, e Redis. A arquitetura segue o padrão de camadas: routers → services → models/repositories, com separação clara de responsabilidades.

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI App                        │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Routers  │  │   Services   │  │    Models      │  │
│  │  auth.py  │→│  graph.py    │→│  user.py       │  │
│  │  webhooks │→│  cache.py    │→│  cache.py      │  │
│  │  .py      │→│  webhook.py  │→│  webhook.py    │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
│        │              │                   │           │
│        ▼              ▼                   ▼           │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Schemas  │  │    Redis     │  │  PostgreSQL   │  │
│  │  auth.py  │  │   (cache)    │  │  (asyncpg)    │  │
│  │  graph.py │  └──────────────┘  └───────────────┘  │
│  └──────────┘                                        │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────────┐
│  Microsoft       │     │  Microsoft Graph     │
│  Entra ID        │     │  Webhooks            │
│  (OAuth 2.0)     │     │  (Notificações)      │
└─────────────────┘     └──────────────────────┘
```

## Componentes

### 1. Módulo de Configuração (`app/config.py`)

**Responsabilidade:** Carregar e validar todas as variáveis de ambiente.

**Design:**
- Usar Pydantic `BaseSettings` com `model_config` apontando para `.env`
- Campos obrigatórios sem valor padrão: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, `SECRET_KEY`, `WEBHOOK_CLIENT_STATE`
- Campos com valor padrão: `MICROSOFT_REDIRECT_URI` (http://localhost:8000/auth/callback), `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS` (http://localhost:5173)
- Instância singleton `settings` exportada para uso em toda a aplicação
- Validação automática na inicialização — aplicação falha se variável obrigatória estiver ausente

**Mapeia requisitos:** R17

### 2. Módulo de Banco de Dados (`app/database.py`)

**Responsabilidade:** Gerenciar conexão assíncrona com PostgreSQL.

**Design:**
- Usar SQLAlchemy 2.0 com `create_async_engine` e driver `asyncpg`
- `AsyncSessionLocal` como factory de sessões
- Função `get_db()` como dependency injection do FastAPI (async generator com yield)
- Evento `startup` do FastAPI cria as tabelas via `Base.metadata.create_all`
- Conexão Redis via `redis.asyncio.Redis.from_url()`

**Mapeia requisitos:** R17

### 3. Modelos SQLAlchemy (`app/models/`)

#### 3.1 User (`app/models/user.py`)

**Colunas:**
| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| email | String(255) | unique, not null, index |
| microsoft_access_token | Text | not null |
| microsoft_refresh_token | Text | not null |
| token_expires_at | DateTime(timezone=True) | not null |
| created_at | DateTime(timezone=True) | default utcnow |
| last_sync_at | DateTime(timezone=True) | nullable |

**Criptografia de tokens:**
- Usar `cryptography.fernet.Fernet` com chave derivada de `SECRET_KEY` via PBKDF2
- Propriedades Python `access_token` e `refresh_token` que criptografam/descriptografam transparentemente
- Valores armazenados no banco são sempre criptografados (base64 do ciphertext)

**Mapeia requisitos:** R4, R13

#### 3.2 GraphCache (`app/models/cache.py`)

**Colunas:**
| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| user_id | UUID | FK(User.id), not null, index |
| service | String(20) | not null (enum: calendar, mail, onenote, onedrive) |
| resource_id | String(255) | not null |
| data | JSONB | not null |
| cached_at | DateTime(timezone=True) | default utcnow |
| expires_at | DateTime(timezone=True) | not null |
| etag | String(255) | nullable |

**Índices:**
- Índice composto em `(user_id, service, resource_id)` com `unique=True`

**Mapeia requisitos:** R14

#### 3.3 WebhookSubscription (`app/models/webhook.py`)

**Colunas:**
| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| user_id | UUID | FK(User.id), not null, index |
| subscription_id | String(255) | unique, not null |
| resource | String(255) | not null |
| client_state | String(255) | not null |
| expires_at | DateTime(timezone=True) | not null, index |
| created_at | DateTime(timezone=True) | default utcnow |

**Mapeia requisitos:** R15


### 4. Schemas Pydantic (`app/schemas/`)

#### 4.1 Auth Schemas (`app/schemas/auth.py`)

```python
class AuthRedirectResponse(BaseModel):
    authorization_url: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str
    token_expires_at: datetime

class ErrorResponse(BaseModel):
    detail: str
```

#### 4.2 Graph Schemas (`app/schemas/graph.py`)

```python
class ServiceType(str, Enum):
    CALENDAR = "calendar"
    MAIL = "mail"
    ONENOTE = "onenote"
    ONEDRIVE = "onedrive"

class GraphDataResponse(BaseModel):
    service: ServiceType
    data: dict | list
    from_cache: bool
    cached_at: datetime | None

class WebhookNotification(BaseModel):
    subscription_id: str
    client_state: str
    resource: str
    change_type: str

class WebhookSubscriptionResponse(BaseModel):
    id: UUID
    subscription_id: str
    resource: str
    expires_at: datetime
```

**Mapeia requisitos:** R1-R12

### 5. Serviço de Autenticação (`app/routers/auth.py`)

**Responsabilidade:** Implementar o fluxo OAuth 2.0 com PKCE para Microsoft Entra ID.

**Endpoints:**

#### GET /auth/microsoft
1. Gerar `code_verifier` (32 bytes aleatórios, base64url)
2. Calcular `code_challenge` = base64url(SHA256(code_verifier))
3. Gerar `state` aleatório (16 bytes, hex)
4. Armazenar `code_verifier` e `state` em sessão temporária (Redis, TTL 10 min)
5. Construir URL de autorização: `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize`
6. Redirecionar com `RedirectResponse` (HTTP 302)

**Parâmetros da URL:**
- `client_id`, `response_type=code`, `redirect_uri`, `scope` (todos os 6 escopos), `code_challenge`, `code_challenge_method=S256`, `state`

#### GET /auth/callback
1. Validar `state` contra valor armazenado no Redis
2. Se `error` presente nos query params, retornar HTTP 400
3. Trocar `code` por tokens via POST para `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
4. Body: `client_id`, `client_secret`, `code`, `redirect_uri`, `grant_type=authorization_code`, `code_verifier`
5. Extrair `access_token`, `refresh_token`, `expires_in` da resposta
6. Buscar email do usuário via GET `https://graph.microsoft.com/v1.0/me`
7. Criar ou atualizar User no banco (upsert por email)
8. Criptografar e persistir tokens
9. Emitir JWT interno assinado com `SECRET_KEY` contendo `user_id` e `exp`
10. Disparar criação de subscrições de webhook (async background task)
11. Retornar `TokenResponse` com `access_token` (JWT interno)

#### POST /auth/refresh
1. Obter `user_id` do JWT via dependency `get_current_user`
2. Buscar User no banco, descriptografar `refresh_token`
3. POST para token endpoint com `grant_type=refresh_token`
4. Atualizar tokens criptografados e `token_expires_at`
5. Emitir novo JWT interno com `user_id` e `exp` atualizado
6. Se falhar, retornar HTTP 401

**Mapeia requisitos:** R1, R2, R3, R4, R18

### 6. Serviço Graph API (`app/services/graph.py`)

**Responsabilidade:** Consumir a Microsoft Graph API com cache, rate limiting e retry.

**Design:**

```python
class GraphService:
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    ENDPOINTS = {
        ServiceType.CALENDAR: "/me/events",
        ServiceType.MAIL: "/me/messages",
        ServiceType.ONENOTE: "/me/onenote/pages",
        ServiceType.ONEDRIVE: "/me/drive/root/children",
    }
```

**Fluxo de consulta (`fetch_data`):**
1. Verificar cache Redis → se hit, retornar dados do cache
2. Verificar rate limit (contador no Redis por user_id, janela 15 min)
3. Fazer GET para Graph API com `Authorization: Bearer {access_token}`
4. Se HTTP 401 → renovar token via `auth.refresh()` → retry uma vez
5. Se HTTP 429 → ler `Retry-After` header → aguardar → retry (max 3x com backoff)
6. Armazenar resposta no Redis com TTL do serviço
7. Persistir no GraphCache (upsert por user_id + service + resource_id)
8. Retornar `GraphDataResponse`

**Rate Limiter:**
- Chave Redis: `lanez:ratelimit:{user_id}`
- Usar `INCR` + `EXPIRE` com janela de 900 segundos (15 min)
- Limite: 200 requisições por janela
- Se excedido, aguardar até reset da janela

**Exponential Backoff:**
- Tentativa 1: aguardar 1s
- Tentativa 2: aguardar 2s
- Tentativa 3: aguardar 4s
- Após 3 tentativas, propagar erro HTTP 429

**HTTP Client:**
- Usar `httpx.AsyncClient` com timeout de 30 segundos
- Instância compartilhada via dependency injection

**Mapeia requisitos:** R5, R6, R7, R8, R9

### 7. Serviço de Cache (`app/services/cache.py`)

**Responsabilidade:** Gerenciar cache Redis com TTLs diferenciados por serviço.

**Design:**

```python
TTL_MAP = {
    ServiceType.CALENDAR: 300,   # 5 minutos
    ServiceType.MAIL: 300,       # 5 minutos
    ServiceType.ONENOTE: 900,    # 15 minutos
    ServiceType.ONEDRIVE: 900,   # 15 minutos
}

def cache_key(user_id: str, service: str) -> str:
    return f"lanez:{user_id}:{service}"
```

**Métodos:**
- `get(user_id, service)` → buscar do Redis, deserializar JSON, retornar ou None
- `set(user_id, service, data)` → serializar JSON, armazenar com TTL do serviço
- `invalidate(user_id, service)` → deletar chave do Redis
- `invalidate_all(user_id)` → deletar todas as chaves do usuário (4 serviços)

**Serialização:** JSON via `json.dumps`/`json.loads` (dados já são dicts do Graph API)

**Mapeia requisitos:** R12

### 8. Serviço de Webhooks (`app/services/webhook.py`)

**Responsabilidade:** Gerenciar subscrições e processar notificações de webhook.

**Design:**

**Criação de subscrições (`create_subscriptions`):**
- Para cada serviço (calendar, mail, onenote, onedrive):
  - POST para `https://graph.microsoft.com/v1.0/subscriptions`
  - Body: `changeType=created,updated,deleted`, `notificationUrl`, `resource`, `expirationDateTime` (4230 min), `clientState`
  - Persistir `WebhookSubscription` no banco

**Mapeamento de recursos Graph para subscrições:**
```python
SUBSCRIPTION_RESOURCES = {
    ServiceType.CALENDAR: "/me/events",
    ServiceType.MAIL: "/me/messages",
    ServiceType.ONENOTE: "/me/onenote/pages",
    ServiceType.ONEDRIVE: "/me/drive/root",
}
```

**Renovação de subscrições (`renew_subscriptions`):**
- Consultar subscrições com `expires_at < now + 60 minutos`
- PATCH para `https://graph.microsoft.com/v1.0/subscriptions/{id}`
- Atualizar `expires_at` no banco
- Se falhar, deletar subscrição antiga e criar nova

**Processamento de notificações (`process_notification`):**
1. Validar `clientState` contra `WEBHOOK_CLIENT_STATE`
2. Extrair `resource` da notificação
3. Mapear resource para `ServiceType` e `user_id`
4. Invalidar cache via `CacheService.invalidate(user_id, service)`

**Mapeia requisitos:** R10, R11

### 9. Router de Webhooks (`app/routers/webhooks.py`)

**Endpoints:**

#### POST /webhooks/graph
1. Se query param `validationToken` presente → responder HTTP 200 com token em text/plain
2. Parsear body como lista de notificações
3. Para cada notificação, chamar `WebhookService.process_notification()`
4. Retornar HTTP 202 (Accepted)

#### GET /webhooks/subscriptions
1. Buscar subscrições ativas do usuário autenticado
2. Retornar lista de `WebhookSubscriptionResponse`

**Mapeia requisitos:** R10, R11

### 10. Routers Graph API (`app/routers/graph.py`)

**Endpoints de dados protegidos por JWT:**

Todos os endpoints de dados exigem autenticação via dependency `get_current_user` que valida o JWT do header Authorization.

#### GET /me/events
- Dependency: `get_current_user` → User
- Chamar `GraphService.fetch_data(user.id, ServiceType.CALENDAR)`

#### GET /me/messages
- Dependency: `get_current_user` → User
- Chamar `GraphService.fetch_data(user.id, ServiceType.MAIL)`

#### GET /me/onenote/pages
- Dependency: `get_current_user` → User
- Chamar `GraphService.fetch_data(user.id, ServiceType.ONENOTE)`

#### GET /me/drive/root/children
- Dependency: `get_current_user` → User
- Chamar `GraphService.fetch_data(user.id, ServiceType.ONEDRIVE)`

**Mapeia requisitos:** R5, R6, R7, R8, R18

### 11. Aplicação Principal (`app/main.py`)

**Responsabilidade:** Inicializar FastAPI, registrar routers, configurar eventos de lifecycle.

**Design:**
- `lifespan` async context manager:
  - Startup: inicializar conexão Redis, criar tabelas do banco, iniciar loop de renovação de webhooks via `asyncio.create_task`
  - Shutdown: cancelar task de renovação, fechar conexão Redis, fechar engine do banco
- Registrar routers: `auth`, `webhooks`, `graph`
- Middleware CORS configurável via `settings.CORS_ORIGINS.split(",")` — não usar `allow_origins=["*"]` fixo
- Loop de renovação de webhooks como `asyncio.Task` no lifespan (não `BackgroundTasks` que é request-scoped):

```python
async def renewal_loop():
    while True:
        await webhook_service.renew_subscriptions()
        await asyncio.sleep(1800)  # 30 minutos

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    task = asyncio.create_task(renewal_loop())
    yield
    # shutdown
    task.cancel()
```

**Mapeia requisitos:** R16, R17

### 12. Infraestrutura Docker

#### docker-compose.yml
```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db, redis]
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

#### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Mapeia requisitos:** R16


### 13. Autenticação JWT Interna (`app/dependencies.py`)

**Responsabilidade:** Emitir e validar JWTs internos para proteger endpoints de dados.

**Design:**

**Emissão de JWT (no callback OAuth e refresh):**
```python
from jose import jwt

def create_access_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
```

**Dependency `get_current_user`:**
```python
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/refresh")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user
```

**Uso:** Todos os endpoints de dados (graph.py), webhooks/subscriptions e auth/refresh usam `Depends(get_current_user)`.

**Mapeia requisitos:** R18

### 14. Alembic — Migrations de Banco de Dados

**Responsabilidade:** Gerenciar migrations de schema do PostgreSQL.

**Design:**
- Inicializar Alembic com `alembic init alembic`
- Configurar `alembic/env.py` para usar `asyncpg` e importar `Base.metadata` dos modelos
- Criar migration inicial com as 3 tabelas: User, GraphCache, WebhookSubscription
- O `lifespan` do FastAPI continua usando `create_all` para desenvolvimento, mas Alembic é o mecanismo oficial para migrations em produção

**Mapeia requisitos:** R13, R14, R15


## Dependências (`requirements.txt`)

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
redis[hiredis]==5.1.0
httpx==0.27.0
pydantic-settings==2.5.0
cryptography==43.0.0
python-dotenv==1.0.1
pgvector==0.3.0
python-jose[cryptography]==3.3.0
alembic==1.13.0
pytest==8.3.0
pytest-asyncio==0.24.0
hypothesis==6.112.0
respx==0.21.0
```

## Propriedades de Corretude

### Propriedade 1: Round-trip de Criptografia de Tokens
- **Tipo:** Round-trip
- **Requisitos:** R4 (4.1, 4.2), R2 (2.2)
- **Descrição:** Para qualquer string de token arbitrária, criptografar e depois descriptografar com a mesma chave deve retornar o valor original.
- **Propriedade:** `decrypt(encrypt(token, key), key) == token` para todo token válido
- **Abordagem de teste:** Property-based test gerando strings aleatórias como tokens, verificando que o round-trip preserva o valor original.

### Propriedade 2: TTL Correto por Serviço
- **Tipo:** Invariante
- **Requisitos:** R12 (12.1, 12.2, 12.3, 12.4)
- **Descrição:** O TTL atribuído a cada serviço deve ser sempre o valor correto: 300s para calendar/mail, 900s para onenote/onedrive.
- **Propriedade:** `get_ttl("calendar") == 300 AND get_ttl("mail") == 300 AND get_ttl("onenote") == 900 AND get_ttl("onedrive") == 900`
- **Abordagem de teste:** Property-based test gerando ServiceType aleatório e verificando que o TTL retornado corresponde ao mapeamento definido.

### Propriedade 3: Formato de Chave de Cache
- **Tipo:** Invariante
- **Requisitos:** R12 (12.5)
- **Descrição:** A chave de cache gerada deve sempre seguir o formato `lanez:{user_id}:{service}`, garantindo isolamento entre usuários e serviços.
- **Propriedade:** `cache_key(user_id, service).startswith("lanez:") AND cache_key(user_id, service).endswith(f":{service}") AND user_id in cache_key(user_id, service)`
- **Abordagem de teste:** Property-based test gerando UUIDs e ServiceTypes aleatórios, verificando que a chave segue o formato esperado e contém os componentes corretos.

### Propriedade 4: PKCE Code Challenge é SHA256 do Code Verifier
- **Tipo:** Round-trip / Metamórfica
- **Requisitos:** R1 (1.1)
- **Descrição:** O code_challenge gerado deve ser exatamente o hash SHA256 base64url-encoded do code_verifier, conforme RFC 7636.
- **Propriedade:** `base64url(sha256(code_verifier)) == code_challenge` para todo par gerado
- **Abordagem de teste:** Property-based test gerando múltiplos pares PKCE e verificando a relação criptográfica entre verifier e challenge.

### Propriedade 5: Validação de clientState em Webhooks
- **Tipo:** Invariante
- **Requisitos:** R10 (10.1, 10.2)
- **Descrição:** Notificações com clientState correto devem ser aceitas; notificações com clientState incorreto devem ser rejeitadas com HTTP 403.
- **Propriedade:** `validate(correct_state) == True AND validate(any_other_state) == False` para todo state diferente do configurado
- **Abordagem de teste:** Property-based test gerando strings aleatórias como clientState e verificando que apenas o valor configurado é aceito.

### Propriedade 6: Exponential Backoff Dobra a Cada Tentativa
- **Tipo:** Metamórfica
- **Requisitos:** R9 (9.3)
- **Descrição:** O tempo de espera do exponential backoff deve dobrar a cada tentativa consecutiva, começando em 1 segundo.
- **Propriedade:** `backoff_time(n) == 2^(n-1)` para n de 1 a 3, onde n é o número da tentativa
- **Abordagem de teste:** Property-based test gerando números de tentativa (1-3) e verificando que o tempo de espera segue a progressão geométrica.

### Propriedade 7: UUID v4 Válido para Novos Registros
- **Tipo:** Invariante
- **Requisitos:** R13 (13.2)
- **Descrição:** Todo registro User criado deve ter um id que é um UUID versão 4 válido.
- **Propriedade:** `UUID(user.id).version == 4` para todo User criado
- **Abordagem de teste:** Property-based test criando múltiplos Users com emails aleatórios e verificando que todos os ids são UUID v4 válidos.

### Propriedade 8: State OAuth é Único Entre Requisições
- **Tipo:** Invariante
- **Requisitos:** R1 (1.4)
- **Descrição:** O parâmetro state gerado para cada requisição OAuth deve ser único, prevenindo ataques CSRF.
- **Propriedade:** Para N chamadas de geração de state, todos os N valores devem ser distintos.
- **Abordagem de teste:** Property-based test gerando múltiplos states e verificando que não há colisões.

### Propriedade 9: Tokens Nunca Aparecem em Logs
- **Tipo:** Invariante
- **Requisitos:** R3 (3.4), R4 (4.4)
- **Descrição:** Nenhuma operação de log do sistema deve conter valores de tokens de acesso ou refresh.
- **Propriedade:** Para qualquer token gerado, o token não deve aparecer como substring em nenhuma saída de log.
- **Abordagem de teste:** Property-based test gerando tokens aleatórios, executando operações que geram logs, e verificando que os tokens não aparecem na saída de log capturada.

## Casos de Borda

### Caso de Borda 1: State OAuth Inválido no Callback
- **Requisitos:** R2 (2.4)
- **Descrição:** Quando o state retornado pelo Entra ID não corresponde ao state original, o sistema deve rejeitar com HTTP 400.
- **Teste:** Enviar callback com state diferente do armazenado e verificar resposta 400.

### Caso de Borda 2: Erro do Entra ID no Callback
- **Requisitos:** R2 (2.5)
- **Descrição:** Quando o Entra ID retorna um erro no callback (ex: user_denied), o sistema deve retornar HTTP 400.
- **Teste:** Enviar callback com parâmetro `error=access_denied` e verificar resposta 400.

### Caso de Borda 3: Refresh Token Expirado
- **Requisitos:** R3 (3.3)
- **Descrição:** Quando o refresh_token armazenado é inválido ou expirado, o sistema deve retornar HTTP 401.
- **Teste:** Tentar refresh com token inválido e verificar resposta 401.

### Caso de Borda 4: Token Expirado Durante Consulta Graph
- **Requisitos:** R5 (5.5), R6 (6.5), R7 (7.5), R8 (8.5)
- **Descrição:** Quando a Graph API retorna 401 durante uma consulta, o sistema deve renovar o token e repetir a requisição uma vez.
- **Teste:** Mock da Graph API retornando 401 na primeira chamada e 200 na segunda, verificar que dados são retornados.

### Caso de Borda 5: clientState Inválido em Webhook
- **Requisitos:** R10 (10.2)
- **Descrição:** Notificação de webhook com clientState incorreto deve ser rejeitada com HTTP 403.
- **Teste:** Enviar notificação com clientState diferente do configurado e verificar resposta 403.

### Caso de Borda 6: Falha na Renovação de Subscrição
- **Requisitos:** R11 (11.6)
- **Descrição:** Quando a renovação de uma subscrição falha, o sistema deve criar uma nova subscrição.
- **Teste:** Mock do PATCH retornando erro, verificar que nova subscrição é criada via POST.

### Caso de Borda 7: Email Duplicado na Criação de User
- **Requisitos:** R13 (13.3)
- **Descrição:** Tentativa de criar dois Users com o mesmo email deve resultar em upsert (atualizar o existente).
- **Teste:** Criar User, tentar criar outro com mesmo email, verificar que apenas um registro existe com dados atualizados.

### Caso de Borda 8: Integridade Referencial em GraphCache e WebhookSubscription
- **Requisitos:** R14 (14.3), R15 (15.3)
- **Descrição:** Inserir registros com user_id inexistente deve falhar com erro de integridade.
- **Teste:** Tentar inserir GraphCache e WebhookSubscription com UUID aleatório como user_id e verificar erro.

### Caso de Borda 9: Variável de Ambiente Obrigatória Ausente
- **Requisitos:** R17 (17.2)
- **Descrição:** A aplicação deve falhar na inicialização se uma variável obrigatória não estiver definida.
- **Teste:** Remover MICROSOFT_CLIENT_ID do ambiente e verificar que Settings() lança ValidationError.
