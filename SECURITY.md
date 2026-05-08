# Security policy

Thanks for taking the time to look at Lanez's security posture.

## Supported versions

Lanez follows a rolling release model. Only `main` receives security fixes.
Any tagged release older than the current `main` is considered unsupported.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Use GitHub's [private security advisory](https://github.com/LucasMilanez/Lanez/security/advisories/new) to report:

- The affected component (MCP router, auth, Graph client, etc.)
- Steps to reproduce, ideally with a minimal proof of concept
- Impact assessment (information disclosure, token exfiltration, privilege escalation, etc.)
- Any suggested mitigations

You can expect:

- An acknowledgement within **5 business days**
- A triage update within **10 business days**
- A coordinated disclosure timeline agreed via the advisory thread

If the advisory mechanism is unavailable, email the maintainer at
`security@lanez.pt`. PGP is not currently supported.

## Scope

### In scope

- Authentication and session handling (`app/routers/auth.py`, `app/dependencies.py`)
- MCP dispatcher and tool handlers (`app/routers/mcp.py`)
- Token encryption and key derivation (`app/models/user.py`)
- Webhook validation (`app/routers/webhooks.py`)
- Rate limiting and CSRF middleware (`app/rate_limit.py`, `app/csrf.py`)
- Any SQL injection, SSRF, or authorization-bypass vector in the backend
- Frontend XSS or token leakage (`frontend/src/**`)

### Out of scope

- Denial-of-service via high request volume — rate limits are intentionally
  permissive for single-user deployments
- Issues in upstream services (Microsoft Graph, Anthropic, Groq) — report
  directly to the vendor
- Social engineering of the maintainer
- Automated vulnerability scans without a demonstrated impact
- Missing security headers on the Vercel-served static frontend when the
  impact is only theoretical (e.g. HSTS, COOP)

## Security defaults

Lanez ships secure defaults, but a few configuration items directly affect
the security posture. They are documented in the README "Security" section
and in `.env.example`:

- `ALLOWED_EMAILS` restricts which Microsoft accounts can complete OAuth.
  Leave empty only in dev.
- `SECRET_KEY` and `FERNET_SALT` derive the encryption key for tokens at
  rest. Rotating either invalidates all stored tokens.
- `WEBHOOK_CLIENT_STATE` validates Microsoft Graph webhook deliveries and
  must be kept secret.
- Cookies are `httpOnly + samesite=lax + secure` in production. The
  frontend sends `X-Requested-With: XMLHttpRequest` on every mutation and
  the backend rejects cookie-authenticated mutations without it.

## Acknowledgements

Credit for responsibly disclosed vulnerabilities will be recorded in the
advisory thread and in the release notes once a fix ships, unless the
reporter prefers to remain anonymous.
