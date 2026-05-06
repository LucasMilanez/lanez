# Lanez

> Self-hosted MCP server that connects AI assistants to your Microsoft 365 data — calendar, emails, OneNote, OneDrive — with semantic search, persistent memory, and automatic meeting briefings.

**Replaces Microsoft Copilot ($30/user/month) with an open-source stack at ~€1-2/month.**

---

## Features

- **9 MCP Tools** — Calendar events, email search, OneNote pages, OneDrive files, web search, semantic search, memory save/recall, meeting briefings
- **MCP Protocol 2025-06-18** — Standard JSON-RPC 2.0 over HTTP, compatible with any MCP client
- **Semantic Search** — Cross-service search using sentence embeddings (pgvector)
- **Persistent Memory** — Save and recall context across sessions
- **Auto Briefings** — Pre-meeting briefings generated from emails, notes, and files related to attendees
- **Real-time Sync** — Microsoft Graph webhooks for instant calendar updates
- **Web Panel** — React dashboard for configuration, briefing history, and audit logs
- **Voice Input** — Speech-to-text via Groq Whisper API
- **Audit Trail** — Immutable log of all tool executions with latency tracking

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  MCP Clients (Claude Desktop, Cursor, etc.)             │
└────────────────────────┬────────────────────────────────┘
                         │ POST /mcp (JSON-RPC 2.0)
                         ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Backend                                        │
│  ┌───────────┐  ┌──────────┐  ┌───────────────────┐    │
│  │ MCP Router│  │ Auth     │  │ Graph Service     │    │
│  │ (dispatch)│  │ (OAuth)  │  │ (Microsoft 365)   │    │
│  └───────────┘  └──────────┘  └───────────────────┘    │
│  ┌───────────┐  ┌──────────┐  ┌───────────────────┐    │
│  │ Embeddings│  │ Memory   │  │ Briefing Service  │    │
│  │ (MiniLM)  │  │ Service  │  │ (Anthropic API)   │    │
│  └───────────┘  └──────────┘  └───────────────────┘    │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌────────────┐ ┌───────────┐ ┌────────────┐
   │ PostgreSQL │ │   Redis   │ │  SearXNG   │
   │ + pgvector │ │  (cache)  │ │ (web search│
   └────────────┘ └───────────┘ └────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.12, fully async) |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| Embeddings | Sentence Transformers all-MiniLM-L6-v2 (384-dim, CPU) |
| AI | Anthropic API (briefing generation) |
| Voice | Groq Whisper (STT) + Browser SpeechSynthesis (TTS) |
| Web Search | SearXNG (self-hosted) |
| Auth | OAuth 2.0 + PKCE (Microsoft Entra ID) |
| Real-time | Microsoft Graph Webhooks |
| Frontend | React 19 + Vite + TailwindCSS + TanStack Query |
| Infra | Docker Compose (local) / Fly.io + Vercel + Neon + Upstash (prod) |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Microsoft 365 account (for Graph API access)
- Microsoft Entra ID app registration ([guide](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app))

### Local Development

```bash
# Clone and configure
cp .env.example .env
# Fill in your Microsoft OAuth credentials and secrets in .env

# Start all services
docker compose up -d --build

# Backend: http://localhost:8000
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
```

### Environment Variables

See [`.env.example`](.env.example) for all required variables. Key ones:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT signing key (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `MICROSOFT_CLIENT_ID` | Azure app registration client ID |
| `MICROSOFT_CLIENT_SECRET` | Azure app registration secret |
| `ANTHROPIC_API_KEY` | For briefing generation |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

## MCP Client Setup

Lanez implements the [Model Context Protocol](https://modelcontextprotocol.io/) (spec 2025-06-18). Any MCP-compatible client can connect.

### Quick Setup (Claude Desktop / Cursor / any MCP client)

1. Get a Bearer token by authenticating at `/auth/microsoft`
2. Add to your client's MCP config:

```json
{
  "mcpServers": {
    "lanez": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://your-deployment.fly.dev/mcp",
        "--header",
        "Authorization: Bearer YOUR_TOKEN"
      ]
    }
  }
}
```

3. Restart your client — 9 tools should appear

See [docs/mcp-client-setup.md](docs/mcp-client-setup.md) for detailed instructions.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | MCP dispatcher (JSON-RPC 2.0) |
| `/mcp` | GET | List available tools |
| `/auth/microsoft` | GET | Start OAuth flow |
| `/auth/callback` | GET | OAuth callback |
| `/healthz` | GET | Health check |

## Deployment

Production deployment uses:
- **Fly.io** — Backend (Amsterdam region)
- **Vercel** — Frontend
- **Neon** — Managed PostgreSQL with pgvector
- **Upstash** — Managed Redis

See [docs/deploy.md](docs/deploy.md) for the full deployment guide.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

The test suite includes 217 tests covering unit, integration, and property-based testing (Hypothesis).

## Project Structure

```
lanez/
├── app/                    # FastAPI backend
│   ├── main.py             # App entry point, lifespan, middleware
│   ├── config.py           # Settings (pydantic-settings)
│   ├── database.py         # SQLAlchemy async engine, Redis
│   ├── dependencies.py     # Auth dependencies
│   ├── models/             # SQLAlchemy ORM models
│   ├── routers/            # API endpoints (10 routers)
│   ├── schemas/            # Pydantic request/response schemas
│   └── services/           # Business logic (10 services)
├── frontend/               # React + Vite + TailwindCSS
├── alembic/                # Database migrations
├── tests/                  # Test suite (217 tests)
├── docs/                   # Documentation
├── docker-compose.yml      # Local dev stack (5 services)
├── Dockerfile              # Production image
└── fly.toml                # Fly.io deployment config
```

## License

[MIT](LICENSE)
