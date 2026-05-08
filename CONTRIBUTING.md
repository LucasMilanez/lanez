# Contributing to Lanez

Thanks for your interest in Lanez. This is a personal project I maintain, but
PRs and issues are welcome when they fit the scope.

## Development setup

1. Fork and clone the repository
2. Copy `.env.example` to `.env` and fill in the required credentials (see
   inline comments in that file)
3. Start the full local stack:

   ```bash
   docker compose up -d --build
   ```

4. Backend will be available at `http://localhost:8000`, frontend at
   `http://localhost:5173`, and the OpenAPI docs at `http://localhost:8000/docs`.

## Running tests

```bash
# Backend — full suite
pytest

# Backend — specific file
pytest tests/test_mcp_protocol_handshake.py -v

# Backend — with coverage
pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend
npm test
```

At the time of writing the suite has 277 tests total: 256 on the backend
(unit, integration and Hypothesis property-based) plus 21 on the frontend
(Vitest + Testing Library). CI on GitHub Actions runs the full suite,
type-checks the frontend, and builds the Docker image on every push and
pull request.

## Code style

- **Python** — type hints required on public functions; async I/O everywhere;
  ruff is the linter (`ruff check app tests`).
- **TypeScript** — strict mode; functional React components; path alias `@/`
  for `frontend/src/`.
- **Commits** — conventional commits (`feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`, `chore:`).

## Pull request process

1. Create a feature branch off `main` (branch protection is enabled on `main`)
2. Keep the PR focused — one feature or fix per PR
3. Add or update tests for any behaviour change
4. Ensure the full suite passes locally before opening the PR
5. Describe the change and the motivation in the PR body; link any related
   issue

## Architecture notes

- **Async-first** — all I/O uses `async`/`await` (SQLAlchemy 2.0 async engine,
  httpx, redis.asyncio)
- **Dependency injection** — FastAPI `Depends()` for sessions, auth, services
- **Stateless MCP dispatcher** — no server-side MCP session state; every call
  authenticates independently via cookie or Bearer token
- **Audit everything** — every MCP tool call, auth event and webhook delivery
  is persisted with latency and success flag in `audit_log`

## Reporting issues

Please include:

- Steps to reproduce
- Expected vs actual behavior
- Relevant environment (OS, Python version, Docker version, browser if
  frontend related)

For security-sensitive reports, prefer GitHub's private security advisory
rather than a public issue.
