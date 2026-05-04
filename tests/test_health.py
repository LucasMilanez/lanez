"""Smoke test do endpoint /healthz — Fase 8."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_healthz_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_healthz_does_not_require_auth():
    """Garante que /healthz NÃO está atrás de get_current_user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Sem cookie/Bearer — deve retornar 200, não 401
        resp = await client.get("/healthz")

    assert resp.status_code == 200
