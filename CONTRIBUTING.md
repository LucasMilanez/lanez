# Contributing to Lanez

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repository
2. Copy `.env.example` to `.env` and fill in your credentials
3. Start the local stack:

```bash
docker compose up -d --build
```

4. The backend runs at `http://localhost:8000` and frontend at `http://localhost:5173`

## Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_mcp_protocol_handshake.py

# With coverage
pytest --cov=app --cov-report=term-missing
```

## Code Style

- Python: Follow PEP 8. Use type hints. Async everywhere.
- Frontend: TypeScript strict mode. Functional components.
- Commits: Use conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all 217+ tests pass
4. Submit a PR with a clear description of what and why

## Architecture Decisions

- **Async-first**: All I/O operations use async/await (SQLAlchemy 2.0, httpx, aioredis)
- **Dependency injection**: FastAPI `Depends()` for database sessions, auth, and services
- **Stateless MCP**: The MCP dispatcher is stateless — no server-side session storage
- **Audit everything**: All tool executions are logged with latency and success/failure

## Reporting Issues

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Docker version)
