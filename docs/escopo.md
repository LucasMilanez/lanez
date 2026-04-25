# Lanez — Escopo Completo

## Visão geral

MCP Server pessoal que conecta qualquer AI assistant (Claude Desktop, Cursor, etc.) aos seus dados do Microsoft 365 — emails, calendário, OneNote, OneDrive — com busca semântica, memória persistente e briefing automático de reuniões. Painel web em React para configuração e monitoramento.

**A story:** "Construí um MCP server que transforma qualquer AI assistant em um assistente que conhece sua agenda, suas notas e seus arquivos — sem copiar e colar nada. Substitui o Microsoft Copilot ($30/usuário/mês) com stack open source."

---

## Stack

```
Frontend    → Vite + React + TailwindCSS + TanStack Query + Recharts (Vercel - grátis)
Backend     → FastAPI (MCP server)
Banco       → PostgreSQL + pgvector (busca semântica)
Embeddings  → Sentence Transformers all-MiniLM-L6-v2 (~90MB, CPU, grátis)
Cache       → Redis (Graph API responses + prompt cache)
AI          → Claude Haiku API (~$1-2/mês uso pessoal)
Voz STT     → Groq Whisper API (free tier - 2.000 req/dia, grátis)
Voz TTS     → Browser SpeechSynthesis API (nativo, grátis)
Busca web   → SearXNG self-hosted (Docker - grátis)
Auth        → OAuth 2.0 Microsoft 365 (Graph API)
Tempo real  → Microsoft Graph Webhooks
Infra       → Docker Compose
```

---

## Fases

### Fase 1 — Fundação
**Meta:** autenticação e pipeline de dados do Microsoft 365 funcionando.

- OAuth 2.0 com Azure AD (Microsoft 365)
- Integração com Microsoft Graph API:
  - Outlook Calendar (`GET /me/events`)
  - Outlook Mail (`GET /me/messages`)
  - OneNote (`GET /me/onenote/pages`)
  - OneDrive (`GET /me/drive/root/children`)
- Microsoft Graph Webhooks — notificações em tempo real quando dados mudam
- Cache de respostas Graph API no Redis (TTL: 5-15min por serviço)
- Armazenamento em PostgreSQL

---

### Fase 2 — MCP Server
**Meta:** servidor MCP funcional consumível pelo Claude Desktop.

Ferramentas expostas via MCP:

```python
get_calendar_events(start, end)     # eventos do Outlook
search_emails(query, limit)         # busca em emails
get_onenote_pages(notebook, query)  # notas do OneNote
search_files(query)                 # arquivos do OneDrive
web_search(query)                   # SearXNG
```

- Protocolo MCP sobre HTTP/SSE
- Configuração em `claude_desktop_config.json`

---

### Fase 3 — Busca Semântica Cross-Service
**Meta:** encontrar qualquer informação em todos os serviços simultaneamente por significado, não por palavra-chave.

- Modelo de embeddings: `all-MiniLM-L6-v2` via Sentence Transformers (local, grátis, ~90MB)
- Geração de embeddings ao ingerir emails, notas e arquivos → vetores de 384 dimensões
- Armazenamento no pgvector
- Ferramenta MCP: `semantic_search(query)` — gera embedding da query e busca vetores mais próximos em todos os serviços
- Re-embedding automático quando webhook notifica mudança

---

### Fase 4 — Memória Persistente
**Meta:** o AI lembra contexto entre sessões.

- Banco local de contexto: decisões, projetos em andamento, preferências
- Ferramentas MCP:
  - `save_memory(content, tags)`
  - `recall_memory(query)`
- Memória usada automaticamente nos briefings e respostas

---

### Fase 5 — Briefing Automático de Reunião
**Meta:** preparação completa de reunião gerada automaticamente.

Fluxo:
1. Webhook notifica novo evento no Outlook
2. Sistema busca: participantes, emails trocados com eles, notas OneNote relacionadas, arquivos relevantes
3. Memória persistente adiciona contexto de interações anteriores
4. Claude Haiku gera briefing estruturado:
   - Contexto da reunião
   - Histórico com participantes
   - Documentos relevantes
   - Pontos pendentes da última interação
5. Briefing salvo e disponível no painel React

---

### Fase 6 — Painel React + Voz
**Meta:** interface visual para configuração, monitoramento, histórico e entrada por voz.

**Páginas:**

| Rota | Conteúdo |
|---|---|
| `/login` | OAuth Microsoft 365 |
| `/dashboard` | Status conexões, uso de tokens Claude, últimas sincronizações |
| `/briefings` | Histórico de briefings com filtro por data/participante |
| `/audit` | Log de acessos com filtros (serviço, data, query) |
| `/settings` | Serviços ativos, TTL de cache, configurações de memória |

**Entrada por voz:**
- Botão de microfone no dashboard
- React grava áudio do browser → envia para FastAPI → FastAPI chama Groq Whisper → retorna texto transcrito → texto vai para o MCP server como query normal
- Resposta da AI lida em voz via Browser SpeechSynthesis API (nativo, zero custo)
- Suporte a português (Whisper Large v3 Turbo, multilingual)
- Free tier Groq: 2.000 requests/dia, 7.200 segundos de áudio/hora

**Endpoint de voz:**
```
POST /voice/transcribe   ← recebe áudio, retorna texto via Groq Whisper
```

**Stack React:**
- Vite + React
- TailwindCSS
- TanStack Query (fetch + cache)
- React Router
- Recharts (gráficos de uso)

---

### Fase 7 — Audit Trail
**Meta:** log imutável de segurança para cada acesso aos dados.

- Registro de: ferramenta chamada, serviço acessado, query, timestamp, tokens consumidos
- Imutável — append only, sem update/delete
- Visualização no painel com filtros
- Exportação em CSV

---

## Modelos de dados

```
User
├── id, email, microsoft_access_token, microsoft_refresh_token
└── created_at, last_sync_at

GraphCache
├── user_id, service, resource_id
├── data (JSON), cached_at, expires_at
└── etag (para validação)

Embedding
├── user_id, service, resource_id
├── content_hash, vector (pgvector)
└── updated_at

Memory
├── user_id, content, tags[]
├── embedding (pgvector)
└── created_at, last_accessed_at

Briefing
├── user_id, event_id, event_title
├── participants[], generated_at
├── content (markdown)
└── sources (JSON — quais dados foram usados)

AuditLog                ← append only
├── user_id, timestamp
├── tool_called, service_accessed
├── query, tokens_used
└── response_time_ms
```

---

## Endpoints FastAPI

```
Auth
  GET  /auth/microsoft          ← inicia OAuth
  GET  /auth/callback           ← callback OAuth
  POST /auth/refresh            ← refresh token

Webhooks
  POST /webhooks/graph          ← recebe notificações Microsoft Graph
  GET  /webhooks/subscriptions  ← lista subscrições ativas

MCP
  GET  /mcp                     ← lista ferramentas disponíveis (MCP protocol)
  POST /mcp/call                ← executa ferramenta MCP

Voz
  POST /voice/transcribe        ← recebe áudio, retorna texto via Groq Whisper

Briefings
  GET  /briefings               ← histórico
  GET  /briefings/{id}          ← briefing específico
  POST /briefings/generate      ← força geração manual

Audit
  GET  /audit?start=&end=&service=
  GET  /audit/export.csv

Dashboard
  GET  /status                  ← status conexões e métricas
```

---

## Estimativa de custos mensais

| Serviço | Custo |
|---|---|
| Claude Haiku API | ~$1-2/mês (uso pessoal) |
| SearXNG | $0 (self-hosted Docker) |
| Vercel (frontend) | $0 (free tier) |
| PostgreSQL + Redis | $0 (Docker local ou Railway free tier) |
| Microsoft Graph API | $0 (incluído no Microsoft 365) |
| Groq Whisper (voz STT) | $0 (free tier) |
| SpeechSynthesis (voz TTS) | $0 (nativo do browser) |
| Sentence Transformers | $0 (local, CPU) |
| **Total** | **~$1-2/mês** |

---

## Requisitos mínimos de hardware

| Recurso | Desenvolvimento | VPS (produção) |
|---|---|---|
| RAM | 8GB | 4GB (Hetzner CX22 ~€4/mês) |
| CPU | 4 cores | 2 vCPU |
| Disco | 5GB livres | 20GB |

---

## O que falar na entrevista

- **Problema:** Microsoft Copilot custa $30/usuário/mês. Construí a alternativa open source.
- **MCP:** protocolo novo de 2025/2026, poucos devs sabem construir um servidor do zero.
- **Webhooks vs polling:** escolhi webhooks para dados em tempo real sem gastar rate limit.
- **Busca semântica:** pgvector em vez de Elasticsearch — mesma qualidade, zero infra extra.
- **Embeddings:** Sentence Transformers local em vez de API paga — zero custo, zero dependência externa.
- **Prompt caching:** reduziu custo do Claude Haiku em 90% nas queries repetitivas.
- **Audit trail:** 66% dos MCP servers em 2026 tinham vulnerabilidades — construí com segurança desde o início.
- **Voz:** Groq Whisper (STT) + Browser SpeechSynthesis (TTS) — pipeline de voz completo a custo zero.
- **Próximo passo:** suporte a Google Workspace (Calendar + Drive + Gmail) como segundo provider OAuth.
