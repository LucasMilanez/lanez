"""Defesa CSRF em profundidade.

O cookie de sessão já é `samesite=lax`, o que bloqueia CSRF cross-site
em browsers modernos para métodos não-GET. Este middleware adiciona
uma segunda camada: exige que requests autenticadas por cookie enviem
o header `X-Requested-With: XMLHttpRequest`. Esse header não é enviado
em navegação direta (click em link, form submit cross-site), então
bloqueia ataques mesmo se o samesite falhar.

Requests autenticadas via Bearer token (clientes MCP) são isentas —
elas não vêm de um browser com cookies ambientes.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_REQUIRED_HEADER = "X-Requested-With"
_REQUIRED_VALUE = "XMLHttpRequest"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_COOKIE_NAME = "lanez_session"

# Rotas isentas do check CSRF — callbacks de OAuth e webhooks que não
# são iniciadas pelo frontend.
_EXEMPT_PATH_PREFIXES = (
    "/auth/callback",       # OAuth redirect do Entra ID
    "/webhooks/graph",      # notificações Microsoft Graph
    "/healthz",
    "/readyz",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Bloqueia mutações cookie-authenticated sem X-Requested-With."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if self._should_check(request) and not self._is_valid(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing CSRF header"},
            )
        return await call_next(request)

    @staticmethod
    def _should_check(request: Request) -> bool:
        # Métodos seguros são isentos
        if request.method in _SAFE_METHODS:
            return False

        # Endpoints recebendo callbacks externos são isentos
        path = request.url.path
        for prefix in _EXEMPT_PATH_PREFIXES:
            if path.startswith(prefix):
                return False

        # Bearer auth (MCP, CLI) é isento — não usa cookies ambientes
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return False

        # Sem cookie = sem risco de CSRF (a auth retornará 401)
        if not request.cookies.get(_COOKIE_NAME):
            return False

        return True

    @staticmethod
    def _is_valid(request: Request) -> bool:
        return request.headers.get(_REQUIRED_HEADER) == _REQUIRED_VALUE
