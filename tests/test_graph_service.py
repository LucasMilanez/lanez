"""Testes unitários para GraphService.fetch_data().

Usa respx para mockar chamadas HTTP e fakeredis para simular Redis.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.schemas.graph import GraphDataResponse, ServiceType
from app.services.graph import (
    GraphService,
    _RATE_LIMIT_MAX,
    _RATE_LIMIT_WINDOW,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id: uuid.UUID | None = None,
    access_token: str = "fake-access-token",
    refresh_token: str = "fake-refresh-token",
) -> MagicMock:
    """Cria um mock de User com propriedades de token."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.microsoft_access_token = access_token
    user.microsoft_refresh_token = refresh_token
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return user


class FakeRedis:
    """Redis fake in-memory para testes (suporta get/set/incr/expire/ttl/delete)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass  # no-op para testes

    async def ttl(self, key: str) -> int:
        return _RATE_LIMIT_WINDOW

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._counters.pop(k, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_data_cache_hit():
    """Quando há cache hit, retorna dados do cache sem chamar Graph API."""
    user_id = uuid.uuid4()
    cached_data = {"value": [{"subject": "Meeting"}]}

    fake_redis = FakeRedis()
    # Pre-populate cache
    cache_key = f"lanez:{user_id}:calendar"
    await fake_redis.set(cache_key, json.dumps(cached_data))

    db = AsyncMock()
    svc = GraphService()

    result = await svc.fetch_data(user_id, ServiceType.CALENDAR, db, fake_redis)

    assert result.from_cache is True
    assert result.service == ServiceType.CALENDAR
    assert result.data == cached_data
    # DB should not have been queried for user
    db.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_data_success_no_cache():
    """Quando não há cache, faz GET na Graph API e retorna dados."""
    user_id = uuid.uuid4()
    user = _make_user(user_id=user_id)
    graph_data = {"value": [{"id": "1", "subject": "Test Event"}]}

    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = user
    # Mock execute for _persist_graph_cache upsert query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    with respx.mock:
        respx.get(
            f"https://graph.microsoft.com/v1.0/me/events"
        ).mock(return_value=httpx.Response(200, json=graph_data))

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_data(
                user_id, ServiceType.CALENDAR, db, fake_redis
            )

    assert result.from_cache is False
    assert result.service == ServiceType.CALENDAR
    assert result.data == graph_data
    # Verify data was cached in Redis
    cached = await fake_redis.get(f"lanez:{user_id}:calendar")
    assert cached is not None
    assert json.loads(cached) == graph_data


@pytest.mark.asyncio
async def test_fetch_data_401_refresh_and_retry():
    """Quando Graph API retorna 401, renova token e faz retry."""
    user_id = uuid.uuid4()
    user = _make_user(user_id=user_id)
    graph_data = {"value": [{"id": "msg1"}]}

    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = user
    # Mock execute for _persist_graph_cache upsert query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    call_count = 0

    with respx.mock:
        # First call returns 401, second returns 200
        route = respx.get("https://graph.microsoft.com/v1.0/me/messages")

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return httpx.Response(401)
            return httpx.Response(200, json=graph_data)

        route.mock(side_effect=side_effect)

        # Mock token refresh endpoint
        respx.post(
            url__startswith="https://login.microsoftonline.com/"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                },
            )
        )

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_data(
                user_id, ServiceType.MAIL, db, fake_redis
            )

    assert result.from_cache is False
    assert result.data == graph_data
    # Token should have been refreshed
    assert user.microsoft_access_token == "new-access-token"


@pytest.mark.asyncio
async def test_fetch_data_rate_limit_exceeded():
    """Quando rate limit é excedido, levanta HTTP 429."""
    user_id = uuid.uuid4()
    fake_redis = FakeRedis()
    # Simulate counter already at max
    key = f"lanez:ratelimit:{user_id}"
    fake_redis._counters[key] = _RATE_LIMIT_MAX

    db = AsyncMock()
    svc = GraphService()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await svc.fetch_data(user_id, ServiceType.CALENDAR, db, fake_redis)

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_fetch_data_429_backoff():
    """Quando Graph API retorna 429, aplica backoff e faz retry."""
    user_id = uuid.uuid4()
    user = _make_user(user_id=user_id)
    graph_data = {"value": []}

    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = user
    # Mock execute for _persist_graph_cache upsert query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    call_count = 0

    with respx.mock:
        route = respx.get("https://graph.microsoft.com/v1.0/me/events")

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json=graph_data)

        route.mock(side_effect=side_effect)

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_data(
                user_id, ServiceType.CALENDAR, db, fake_redis
            )

    assert result.from_cache is False
    assert result.data == graph_data
    assert call_count == 3  # 2 retries + 1 success


@pytest.mark.asyncio
async def test_fetch_data_user_not_found():
    """Quando usuário não existe no banco, levanta HTTP 404."""
    user_id = uuid.uuid4()
    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = None

    svc = GraphService()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await svc.fetch_data(user_id, ServiceType.CALENDAR, db, fake_redis)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_data_persists_to_graph_cache():
    """Verifica que dados são persistidos no GraphCache via db."""
    user_id = uuid.uuid4()
    user = _make_user(user_id=user_id)
    graph_data = {"value": [{"name": "file.txt"}]}

    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = user
    # Mock the select query for upsert — no existing entry
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    with respx.mock:
        respx.get(
            "https://graph.microsoft.com/v1.0/me/drive/root/children"
        ).mock(return_value=httpx.Response(200, json=graph_data))

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_data(
                user_id, ServiceType.ONEDRIVE, db, fake_redis
            )

    assert result.from_cache is False
    # db.add should have been called for new GraphCache entry
    db.add.assert_called_once()
    # db.commit should have been called (for persist)
    assert db.commit.call_count >= 1
