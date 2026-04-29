"""Testes do endpoint POST /memories — Fase 6b.

Verifica criação de memória, validações de content (min_length, whitespace-only),
limite de tags e autenticação.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app


def _make_fake_user() -> MagicMock:
    """Cria User mock para dependency override."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_sync_at = None
    user.created_at = datetime.now(timezone.utc)
    return user


@pytest.mark.asyncio
async def test_create_memory_201_with_id_and_created_at():
    """Mock save_memory retornando dict → 201 com id e created_at presentes."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        with patch(
            "app.routers.memories.save_memory",
            new_callable=AsyncMock,
            return_value={
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "content": "teste de memória",
                "tags": ["voz"],
                "created_at": "2024-01-15T10:30:00+00:00",
            },
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/memories",
                    json={"content": "teste de memória", "tags": ["voz"]},
                )

            assert resp.status_code == 201
            body = resp.json()
            assert "id" in body
            assert body["id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            assert "created_at" in body
            assert body["content"] == "teste de memória"
            assert body["tags"] == ["voz"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_memory_validates_min_length():
    """Body com content="" → 422."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/memories",
                json={"content": ""},
            )

        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_memory_rejects_whitespace_only_content():
    """Body com content="   " → 422 (field_validator strips e rejeita)."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/memories",
                json={"content": "   "},
            )

        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_memory_validates_max_tags():
    """Body com 21 tags → 422."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            tags = [f"t{i}" for i in range(21)]
            resp = await client.post(
                "/memories",
                json={"content": "valid content", "tags": tags},
            )

        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_memory_requires_auth():
    """Sem cookie/Bearer → 401. NÃO define dependency override."""
    # Garantir que NÃO há override para get_current_user
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/memories",
            json={"content": "teste", "tags": []},
        )

    assert resp.status_code == 401
