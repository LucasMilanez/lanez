"""Health check endpoint — Fase 8.

Liveness probe sem auth. Retorna {"ok": true} se o processo está vivo.
NÃO checa dependências (DB/Redis) — liveness ≠ readiness.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
