"""Health endpoints — /healthz (liveness) e /readyz (readiness).

Liveness: processo está rodando. Não checa dependências.
Readiness: dependências (DB + Redis) estão acessíveis. Usado por
load balancers para decidir se a instância pode receber tráfego.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.database import engine, redis_client

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, bool]:
    """Liveness probe — sem auth, sem checagem de dependências."""
    return {"ok": True}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    """Readiness probe — valida conexões DB + Redis.

    Retorna 200 com `{"ok": true, "db": true, "redis": true}` se ambos
    respondem, ou 503 com detalhes da falha.
    """
    checks = {"db": False, "redis": False}

    # DB — SELECT 1
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception as exc:
        checks["db_error"] = str(exc)[:200]

    # Redis — PING
    try:
        if redis_client is not None:
            await redis_client.ping()
            checks["redis"] = True
        else:
            checks["redis_error"] = "redis não inicializado"
    except Exception as exc:
        checks["redis_error"] = str(exc)[:200]

    if not (checks["db"] and checks["redis"]):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ok": False, **checks}

    return {"ok": True, **checks}
