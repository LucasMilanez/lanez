# Lanez — Briefing Fase 1 para KIRO

## O que é o Lanez

MCP Server pessoal que conecta AI assistants (Claude Desktop, Cursor) aos dados do Microsoft 365 do usuário — emails, calendário, OneNote, OneDrive — com busca semântica, memória persistente e briefing automático de reuniões.

**Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source a ~$1-2/mês.**

---

## Stack definida (não alterar)

```
Backend     → FastAPI
Banco       → PostgreSQL + pgvector
Embeddings  → Sentence Transformers all-MiniLM-L6-v2
Cache       → Redis
AI          → Claude Haiku API (anthropic)
Voz STT     → Groq Whisper API
Voz TTS     → Browser SpeechSynthesis API (frontend)
Busca web   → SearXNG (self-hosted Docker)
Auth        → OAuth 2.0 Microsoft Entra ID (Graph API)
Tempo real  → Microsoft Graph Webhooks
Infra       → Docker Compose
Frontend    → Vite + React + TailwindCSS + TanStack Query (fase posterior)
```

---

## Fase 1 — Fundação (escopo desta entrega)

### Objetivo
Pipeline de dados do Microsoft 365 funcionando end-to-end: autenticar, buscar dados, cachear e armazenar.

### O que implementar

**1. Autenticação OAuth 2.0 com Microsoft Entra ID**
- `GET /auth/microsoft` — redireciona para login Microsoft
- `GET /auth/callback` — recebe code, troca por access_token + refresh_token
- `POST /auth/refresh` — renova access_token usando refresh_token
- Tokens armazenados no PostgreSQL, nunca em memória ou logs
- Usar PKCE flow

**2. Integração Microsoft Graph API**
- `GET /me/events` — Outlook Calendar
- `GET /me/messages` — Outlook Mail
- `GET /me/onenote/pages` — OneNote
- `GET /me/drive/root/children` — OneDrive

**3. Microsoft Graph Webhooks (tempo real)**
- `POST /webhooks/graph` — recebe change notifications da Microsoft
- `GET /webhooks/subscriptions` — lista subscrições ativas
- Validar `clientState` em toda notificação recebida
- Renovar subscrições antes de expirar (máx 4230 minutos)

**4. Cache Redis**
- Cachear respostas do Graph API por serviço:
  - Calendar: TTL 5 min
  - Mail: TTL 5 min
  - OneNote: TTL 15 min
  - OneDrive: TTL 15 min
- Invalidar cache quando webhook notificar mudança no recurso

**5. Armazenamento PostgreSQL**
- Persistir tokens do usuário
- Persistir dados sincronizados do Graph API

---

## Modelos de dados (Fase 1)

```
User
├── id (uuid)
├── email
├── microsoft_access_token (encrypted)
├── microsoft_refresh_token (encrypted)
├── token_expires_at
├── created_at
└── last_sync_at

GraphCache
├── id
├── user_id (fk User)
├── service (calendar | mail | onenote | onedrive)
├── resource_id
├── data (jsonb)
├── cached_at
├── expires_at
└── etag

WebhookSubscription
├── id
├── user_id (fk User)
├── subscription_id (Microsoft ID)
├── resource
├── client_state (secret para validação)
├── expires_at
└── created_at
```

---

## Variáveis de ambiente necessárias

```env
# Microsoft Entra ID
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/callback

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lanez

# Redis
REDIS_URL=redis://localhost:6379

# App
SECRET_KEY=               # para assinar JWT interno
WEBHOOK_CLIENT_STATE=     # secret para validar webhooks Microsoft
```

---

## Estrutura de pastas esperada

```
lanez/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── user.py
│   │   ├── cache.py
│   │   └── webhook.py
│   ├── routers/
│   │   ├── auth.py
│   │   └── webhooks.py
│   ├── services/
│   │   ├── graph.py        ← Microsoft Graph API client
│   │   ├── cache.py        ← Redis operations
│   │   └── webhook.py      ← subscription management
│   └── schemas/
│       ├── auth.py
│       └── graph.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Decisões técnicas já tomadas (não questionar)

- **Webhooks em vez de polling** — dados em tempo real sem gastar rate limit
- **TTL de cache por serviço** — Calendar/Mail 5min, OneNote/OneDrive 15min
- **Tokens criptografados no banco** — nunca em texto plano
- **PKCE no OAuth flow** — segurança adicional no Entra ID
- **asyncpg** — driver async para PostgreSQL (FastAPI é async)

---

## Permissões Microsoft Graph necessárias

```
Calendars.Read
Mail.Read
Notes.Read
Files.Read
User.Read
offline_access
```

---

## Rate limits Microsoft Graph (para referência)

- 200 requests / 15 minutos
- 2.000 requests / dia
- Implementar exponential backoff em caso de 429

---

## O que NÃO fazer nesta fase

- Não implementar embeddings ou busca semântica (Fase 3)
- Não implementar MCP server (Fase 2)
- Não implementar frontend React (Fase 6)
- Não armazenar tokens em variáveis de ambiente ou logs
- Não usar polling — apenas webhooks para atualizações

---

## Entregáveis esperados da Fase 1

1. `docker-compose.yml` funcional (FastAPI + PostgreSQL + Redis)
2. OAuth flow completo com Entra ID
3. Endpoints de sincronização dos 4 serviços Graph API
4. Webhooks recebendo e validando notificações
5. Cache Redis funcionando com TTLs corretos
6. `.env.example` com todas as variáveis documentadas
7. `requirements.txt` com dependências fixadas
