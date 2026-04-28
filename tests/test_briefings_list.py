"""Testes para GET /briefings (lista paginada) — Fase 6a.

Verifica paginação, filtro ILIKE por q, ordenação event_start desc,
e contagem total correta.
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
    user.last_sync_at = None
    user.created_at = datetime.now(timezone.utc)
    return user


def _make_briefing(user_id: uuid.UUID, index: int, subject: str = "Meeting") -> MagicMock:
    """Cria mock de Briefing com event_start decrescente por index."""
    b = MagicMock()
    b.id = uuid.uuid4()
    b.user_id = user_id
    b.event_id = f"evt-{index:03d}"
    b.event_subject = f"{subject} {index}"
    b.event_start = datetime(2024, 6, 1, tzinfo=timezone.utc) + timedelta(days=index)
    b.event_end = b.event_start + timedelta(hours=1)
    b.attendees = ["a@test.com", "b@test.com"]
    b.generated_at = datetime.now(timezone.utc)
    b.content = f"Content {index}"
    b.model_used = "claude-haiku"
    b.input_tokens = 100
    b.output_tokens = 50
    b.cache_read_tokens = 0
    b.cache_write_tokens = 0
    return b


@pytest.mark.asyncio
async def test_briefings_list_paginates_and_filters():
    """Cria 25 briefings, verifica paginação e filtro por q."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()

    # Criar 25 briefings: 20 "Meeting X" + 5 "Alpha X"
    all_briefings = []
    for i in range(20):
        all_briefings.append(_make_briefing(user.id, i, "Meeting"))
    for i in range(20, 25):
        all_briefings.append(_make_briefing(user.id, i, "Alpha"))

    # Ordenar por event_start desc (como o endpoint faz)
    all_briefings.sort(key=lambda b: b.event_start, reverse=True)

    # --- Test 1: Paginação page=2, page_size=10 (sem filtro) ---
    page2_items = all_briefings[10:20]  # items 10-19

    call_count = 0

    async def mock_execute_pagination(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # count query
            result.scalar_one.return_value = 25
        else:
            # paged query
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = page2_items
            result.scalars.return_value = scalars_mock
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute_pagination

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/briefings?page=2&page_size=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 25
        assert body["page"] == 2
        assert body["page_size"] == 10
        assert len(body["items"]) == 10

        # Verificar que items não contêm content nem tokens
        for item in body["items"]:
            assert "content" not in item
            assert "input_tokens" not in item
            assert "output_tokens" not in item
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    # --- Test 2: Filtro por q="Alpha" ---
    alpha_briefings = [b for b in all_briefings if "Alpha" in b.event_subject]

    call_count = 0

    async def mock_execute_filter(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = 5
        else:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = alpha_briefings
            result.scalars.return_value = scalars_mock
        return result

    mock_db2 = AsyncMock()
    mock_db2.execute = mock_execute_filter

    async def override_get_db2():
        yield mock_db2

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db2
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/briefings?q=Alpha")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        for item in body["items"]:
            assert "Alpha" in item["event_subject"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    # --- Test 3: Ordenação event_start desc ---
    first_3 = all_briefings[:3]

    call_count = 0

    async def mock_execute_order(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = 25
        else:
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = first_3
            result.scalars.return_value = scalars_mock
        return result

    mock_db3 = AsyncMock()
    mock_db3.execute = mock_execute_order

    async def override_get_db3():
        yield mock_db3

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db3
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/briefings?page=1&page_size=3")

        assert resp.status_code == 200
        body = resp.json()
        items = body["items"]
        # Verificar ordenação desc
        for i in range(len(items) - 1):
            assert items[i]["event_start"] >= items[i + 1]["event_start"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
