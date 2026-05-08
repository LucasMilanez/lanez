"""Health endpoints — /healthz (liveness) e /readyz (readiness).

Liveness: processo está rodando. Não checa dependências.
Readiness: dependências (DB + Redis) estão acessíveis. Usado por
load balancers para decidir se a instância pode receber tráfego.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import database
from app.database import engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, bool]:
    """Liveness probe — sem auth, sem checagem de dependências."""
    return {"ok": True}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    """Readiness probe — valida conexões DB + Redis.

    Retorna 200 com ``{"ok": true, "db": true, "redis": true}`` se ambos
    respondem, ou 503 com detalhes da falha.

    Observação técnica: o cliente Redis é resolvido via ``app.database``
    em vez de ``from app.database import redis_client`` porque a variável
    é reatribuída no lifespan (``init_redis``). Um import direto captura
    o valor inicial ``None`` e nunca reflete a atualização.
    """
    checks: dict[str, object] = {"db": False, "redis": False}

    # DB — SELECT 1
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception as exc:
        checks["db_error"] = str(exc)[:200]

    # Redis — PING (resolve lazy para pegar a instância inicializada no lifespan)
    try:
        client = database.redis_client
        if client is not None:
            await client.ping()
            checks["redis"] = True
        else:
            checks["redis_error"] = "redis not initialized"
    except Exception as exc:
        checks["redis_error"] = str(exc)[:200]

    if not (checks["db"] and checks["redis"]):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ok": False, **checks}

    return {"ok": True, **checks}
