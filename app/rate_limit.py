"""Rate limiting centralizado.

Usa slowapi (wrapper do limits em cima do FastAPI). Chave de limite:
o user_id do JWT se autenticado, caindo para o IP remoto caso
contrário. Limites são aplicados por endpoint via decorator.

Configurado in-memory por padrão (1 instância = 1 bucket). Para
múltiplas instâncias Fly.io, usar RateLimiter com storage Redis.
Como o app roda em min_machines_running=1, in-memory é suficiente.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func(request: Request) -> str:
    """Identifica o requester.

    Preferência:
    1. user_id do request.state (setado por get_current_user)
    2. X-Forwarded-For (primeiro IP — Fly.io envia)
    3. Remote address (fallback final)
    """
    # get_current_user não popula request.state por padrão; extraímos do
    # Authorization header direto. Como não podemos decodificar o JWT sem
    # import cíclico, usamos o token completo como chave — mesmo cliente
    # = mesmo bucket, sem expor identidade.
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        # Usar hash-like da cabeça do token para não guardar secret em memória
        # de métricas/logs. Últimos 16 chars são suficientes como ID único.
        return f"bearer:{token[-16:]}"

    cookie = request.cookies.get("lanez_session")
    if cookie:
        return f"cookie:{cookie[-16:]}"

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key_func)
