"""Testes para GET /status (dashboard) — Fase 6a.

Verifica que o endpoint agrega métricas corretamente, usa `resource`
(não `service`) para webhooks, e usa Embedding.service como string
direta (sem .value).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_sync_at = datetime.now(timezone.utc) - timedelta(hours=2)
    user.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    return user


def _make_webhook(resource: str) -> MagicMock:
    w = MagicMock()
    w.resource = resource
    w.expires_at = datetime.now(timezone.utc) + timedelta(days=2)
    return w


def _make_briefing(index: int) -> MagicMock:
    b = MagicMock()
    b.event_id = f"evt-{index}"
    b.event_subject = f"Meeting {index}"
    b.event_start = datetime.now(timezone.utc) - timedelta(days=index)
    return b


@pytest.mark.asyncio
async def test_status_aggregates_correctly():
    """GET /status retorna métricas agregadas corretas."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()
    webhooks = [
        _make_webhook("me/calendars/default/events"),
        _make_webhook("me/mailFolders/inbox/messages"),
    ]
    recent = [_make_briefing(i) for i in range(3)]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # webhooks query
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = webhooks
            result.scalars.return_value = scalars_mock
        elif call_count == 2:
            # embeddings group_by — returns tuples (service_string, count)
            result.all.return_value = [("mail", 10), ("onenote", 5)]
        elif call_count == 3:
            # memories count
            result.scalar_one.return_value = 42
        elif call_count == 4:
            # briefings count 30d
            result.scalar_one.return_value = 7
        elif call_count == 5:
            # recent briefings
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = recent
            result.scalars.return_value = scalars_mock
        elif call_count == 6:
            # token sums
            result.one.return_value = (1000, 500, 200, 100)
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/status")

        assert resp.status_code == 200
        body = resp.json()

        assert body["user_email"] == "test@example.com"
        assert body["memories_count"] == 42
        assert body["briefings_count_30d"] == 7
        assert len(body["webhook_subscriptions"]) == 2
        assert len(body["embeddings_by_service"]) == 2
        assert len(body["recent_briefings"]) == 3
        assert body["tokens_30d"]["input"] == 1000
        assert body["tokens_30d"]["output"] == 500
        assert body["tokens_30d"]["cache_read"] == 200
        assert body["tokens_30d"]["cache_write"] == 100
        assert body["config"]["briefing_history_window_days"] == 90
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_status_uses_resource_not_service():
    """webhook_subscriptions expõe campo `resource` (não `service`)."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()
    webhooks = [_make_webhook("me/calendars/default/events")]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = webhooks
            result.scalars.return_value = scalars_mock
        elif call_count == 2:
            result.all.return_value = []
        elif call_count == 3:
            result.scalar_one.return_value = 0
        elif call_count == 4:
            result.scalar_one.return_value = 0
        elif call_count == 5:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            result.scalars.return_value = scalars_mock
        elif call_count == 6:
            result.one.return_value = (0, 0, 0, 0)
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/status")

        assert resp.status_code == 200
        body = resp.json()
        ws = body["webhook_subscriptions"]
        assert len(ws) == 1
        # Must have `resource`, not `service`
        assert "resource" in ws[0]
        assert ws[0]["resource"] == "me/calendars/default/events"
        assert "service" not in ws[0]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_status_embedding_service_no_dot_value():
    """embeddings_by_service usa string direta do campo `service`, sem `.value`."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            result.scalars.return_value = scalars_mock
        elif call_count == 2:
            # embeddings — returns plain strings, not Enum objects
            result.all.return_value = [("mail", 15), ("calendar", 8)]
        elif call_count == 3:
            result.scalar_one.return_value = 0
        elif call_count == 4:
            result.scalar_one.return_value = 0
        elif call_count == 5:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            result.scalars.return_value = scalars_mock
        elif call_count == 6:
            result.one.return_value = (0, 0, 0, 0)
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/status")

        assert resp.status_code == 200
        body = resp.json()
        emb = body["embeddings_by_service"]
        assert len(emb) == 2
        # Values should be plain strings, not Enum representations
        services = {e["service"] for e in emb}
        assert services == {"mail", "calendar"}
        # Verify counts
        for e in emb:
            if e["service"] == "mail":
                assert e["count"] == 15
            elif e["service"] == "calendar":
                assert e["count"] == 8
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
