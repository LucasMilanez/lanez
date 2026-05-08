# Deployment guide

Runbook to put a fresh Lanez instance on the air end-to-end.

**Production stack:**

- **Backend** — [Fly.io](https://fly.io) (Amsterdam region by default)
- **Frontend** — [Vercel](https://vercel.com) (static SPA)
- **Database** — [Neon](https://neon.tech) (managed Postgres 16 + pgvector)
- **Cache** — [Upstash](https://upstash.com) (managed Redis)

Web search via SearXNG is not deployed in production; `web_search` returns an `unavailable` stub instead.

---

## 1. Prerequisites

Install the CLIs and create the accounts (all have free tiers):

- **flyctl** — `curl -L https://fly.io/install.sh | sh` (or `brew install flyctl`)
- **vercel** — `npm i -g vercel`
- Accounts on [Fly.io](https://fly.io/app/sign-up), [Neon](https://console.neon.tech/signup), [Upstash](https://console.upstash.com/login) and [Vercel](https://vercel.com/signup)
- A Microsoft Entra ID app registration (**single-tenant** recommended) with the redirect URI `http://localhost:8000/auth/callback` configured for development. The production URI will be added later.

## 2. Create the Postgres database on Neon

1. Open the Neon console and create a new project (pick a region geographically close to your Fly.io region).
2. Copy the connection string and convert it to the async form: `postgresql+asyncpg://user:pass@host/dbname`.
3. Enable the `vector` extension from the Neon SQL editor:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

## 3. Create the Redis instance on Upstash

1. Create a new Redis database in the Upstash console (Global region).
2. Copy the connection string in the form `rediss://default:<token>@<host>:<port>`.

## 4. Create the Fly.io app

From the repository root:

```bash
fly launch --no-deploy
```

When prompted, **decline** the offer to provision internal Postgres and Redis — we use Neon and Upstash.
Check that the generated `fly.toml` matches the one committed in the repo.

## 5. Set Fly.io secrets

```bash
fly secrets set \
  MICROSOFT_CLIENT_ID="..." \
  MICROSOFT_CLIENT_SECRET="..." \
  MICROSOFT_TENANT_ID="..." \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  WEBHOOK_CLIENT_STATE="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ALLOWED_EMAILS="you@example.com" \
  DATABASE_URL="postgresql+asyncpg://..." \
  REDIS_URL="rediss://default:...@...:port" \
  ANTHROPIC_API_KEY="..." \
  GROQ_API_KEY="..."
```

> **Generate fresh values for `SECRET_KEY` and `WEBHOOK_CLIENT_STATE`.** Do not reuse local-dev secrets in production.

> **`ALLOWED_EMAILS`** is a comma-separated allowlist of addresses allowed to complete the OAuth flow. It is a defense-in-depth layer against accidentally making the Azure app multi-tenant. Leave empty only in dev.

## 6. Deploy the backend

```bash
fly deploy
```

Wait for the health check to turn green, then confirm the instance is serving:

```bash
curl https://<your-app>.fly.dev/healthz
# {"ok":true}

curl https://<your-app>.fly.dev/readyz
# {"ok":true,"db":true,"redis":true}
```

The startup sequence runs `alembic upgrade head` automatically — no manual migration step is required.

## 7. Deploy the frontend

From the `frontend/` directory:

```bash
cd frontend
vercel --prod
```

Note the URL Vercel assigned (for example `lanez.vercel.app` or `lanez-xxxxx.vercel.app`).

If it is **not** `lanez.vercel.app`, update `CORS_ORIGINS` inside `fly.toml` to match and redeploy the backend with `fly deploy`.

## 8. Update the Azure portal

In the Lanez Entra ID app registration:

1. Go to **Authentication → Redirect URIs**
2. Add `https://<your-app>.fly.dev/auth/callback`
3. **Keep** `http://localhost:8000/auth/callback` so local dev still works
4. Save

## 9. Smoke test

Open the Vercel URL in a private browser window:

1. Sign in with your Microsoft 365 account
2. The dashboard should load with your email and webhook count
3. Visit `/audit` to confirm the audit trail renders
4. If there are events on your calendar, open one from the Briefings list to confirm briefings are being generated

## 10. Bootstrap the Microsoft Graph webhooks

> **Warning — `setup-webhook.sh` is destructive.**
> It deletes **all** webhook subscriptions in the production database.
> Use it only on the very first deployment or when you need to reset the subscriptions completely. It is a one-shot bootstrap, not a routine task.

```bash
bash scripts/setup-webhook.sh
```

The application's `renewal_loop` will recreate the subscriptions automatically within 30 minutes, using the production `WEBHOOK_NOTIFICATION_URL`. To force immediate recreation:

```bash
flyctl restart --app <your-app>
```

## 11. Future deployments

After the initial setup, subsequent deployments are automatic:

```bash
git push origin main
```

Fly.io and Vercel both detect the push and redeploy.

For changes that involve database migrations, startup runs `alembic upgrade head` automatically. If startup fails because of a migration error, use the diagnostic script:

```bash
bash scripts/migrate.sh
```

---

## Rollback

- **Frontend:** `vercel rollback` (or pick a previous deployment in the Vercel dashboard).
- **Backend:** `fly releases --app <your-app>` then `fly releases rollback <version> --app <your-app>`.
- **Database:** Neon provides point-in-time recovery via its console. For a schema-only rollback, run `alembic downgrade` locally against the production URL.

## Observability

- **Logs:** `fly logs --app <your-app>`
- **Metrics:** Fly.io dashboard (CPU, memory, request rate)
- **Audit trail:** every MCP call is recorded in the `audit_log` table; browse it via `/audit` in the web panel
- **Health:** `/readyz` for readiness checks (validates DB and Redis connectivity)
