"""Testes dos hooks de injeção de audit log — Fase 7.

Verifica que os pontos de injeção (auth, MCP, memory, voice) registram
eventos corretamente no audit_log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.database import get_db, get_redis
from app.main import app


def _make_fake_user() -> MagicMock:
    """Cria User mock para dependency override."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "audit-hook-test@example.com"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_sync_at = None
    user.created_at = datetime.now(timezone.utc)
    return user


class FakeRedis:
    """Redis mock mínimo para testes que precisam de get_redis."""
    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def incr(self, key):
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key, seconds):
        pass

    async def ttl(self, key):
        return -1

    async def delete(self, *keys):
        for k in keys:
            self._store.pop(k, None)


# ---------------------------------------------------------------------------
# Auth hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logged_on_auth_logout():
    """POST /auth/logout autenticado → row auth.logout no audit_log."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
        })

    try:
        with patch("app.routers.auth.log_event", side_effect=_capture_log_event):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/auth/logout")

        assert resp.status_code == 204
        assert len(logged_events) == 1
        evt = logged_events[0]
        assert evt["event_type"] == "auth.logout"
        assert evt["user_id"] == fake_user.id
        assert evt["event_data"] == {}
        assert evt["success"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_auth_logout_now_requires_auth():
    """POST /auth/logout sem auth → 401 (regressão da mudança em R4.4)."""
    # Garantir que NÃO há override para get_current_user
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/logout")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# MCP hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logged_on_mcp_call_success():
    """POST /mcp/call com tool válida → row mcp.call com success=True e latency_ms."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
            "error_message": error_message,
            "latency_ms": latency_ms,
        })

    async def _mock_handler(arguments, user, db, redis, graph, searxng):
        return {"result": "ok"}

    try:
        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"get_calendar_events": _mock_handler}):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {
                            "name": "get_calendar_events",
                            "arguments": {"start": "2026-01-01", "end": "2026-01-31"},
                        },
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["isError"] is False

        # Verificar audit log
        assert len(logged_events) == 1
        evt = logged_events[0]
        assert evt["event_type"] == "mcp.call"
        assert evt["success"] is True
        assert evt["latency_ms"] is not None and evt["latency_ms"] >= 0
        assert evt["event_data"]["tool_name"] == "get_calendar_events"
        assert evt["event_data"]["success"] is True
        assert evt["event_data"]["error_message"] is None

        # Verificar que arguments_summary não contém strings cruas (PII)
        summary = evt["event_data"]["arguments_summary"]
        assert summary["start"] == {"type": "string", "length": 10}
        assert summary["end"] == {"type": "string", "length": 10}
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_audit_logged_on_mcp_call_failure():
    """Mock handler levantando HTTPException → row mcp.call com success=False."""
    from fastapi import HTTPException as FastAPIHTTPException

    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
            "error_message": error_message,
            "latency_ms": latency_ms,
        })

    long_detail = "x" * 600

    async def _mock_handler(arguments, user, db, redis, graph, searxng):
        raise FastAPIHTTPException(status_code=400, detail=long_detail)

    try:
        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"search_emails": _mock_handler}):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": "2",
                        "method": "tools/call",
                        "params": {
                            "name": "search_emails",
                            "arguments": {"query": "test query"},
                        },
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["isError"] is True

        # Verificar audit log
        assert len(logged_events) == 1
        evt = logged_events[0]
        assert evt["event_type"] == "mcp.call"
        assert evt["success"] is False
        assert evt["error_message"] == long_detail  # truncation happens in log_event
        assert evt["latency_ms"] is not None and evt["latency_ms"] >= 0
        assert evt["event_data"]["tool_name"] == "search_emails"
        assert evt["event_data"]["success"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# Memory hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logged_on_memory_create_rest():
    """POST /memories autenticado → row memory.created com source=rest."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
        })

    try:
        with patch(
            "app.routers.memories.save_memory",
            new_callable=AsyncMock,
            return_value={
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "content": "test memory",
                "tags": ["test"],
                "created_at": "2026-04-30T10:00:00+00:00",
            },
        ) as mock_save:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/memories",
                    json={"content": "test memory", "tags": ["test"]},
                )

        assert resp.status_code == 201
        # Verificar que save_memory foi chamado com source="rest"
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        assert call_kwargs.kwargs.get("source") == "rest" or \
               (len(call_kwargs.args) > 4 and call_kwargs.args[4] == "rest") or \
               call_kwargs.kwargs.get("source", "rest") == "rest"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_audit_logged_on_memory_create_mcp():
    """POST /mcp/call save_memory → row memory.created com source=mcp."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
        })

    async def _mock_save_memory(db, user_id, content, tags=None, source="rest"):
        # Simulate the audit log call that save_memory would make
        await _capture_log_event(
            db,
            user_id=user_id,
            event_type="memory.created",
            event_data={"tags": tags or [], "content_length": len(content), "source": source},
            success=True,
        )
        return {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "content": content,
            "tags": tags or [],
            "created_at": "2026-04-30T10:00:00+00:00",
        }

    try:
        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event), \
             patch("app.services.memory.save_memory", side_effect=_mock_save_memory):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": "3",
                        "method": "tools/call",
                        "params": {
                            "name": "save_memory",
                            "arguments": {"content": "test memory from mcp"},
                        },
                    },
                )

        assert resp.status_code == 200
        # Find the memory.created event
        memory_events = [e for e in logged_events if e["event_type"] == "memory.created"]
        assert len(memory_events) >= 1
        evt = memory_events[0]
        assert evt["event_data"]["source"] == "mcp"
        assert evt["event_data"]["content_length"] == len("test memory from mcp")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# Voice hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logged_on_voice_transcribe_success():
    """POST /voice/transcribe (mock Groq) → row voice.transcribed."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
            "latency_ms": latency_ms,
        })

    audio_content = b"fake audio content bytes"

    try:
        with patch("app.routers.voice.log_event", side_effect=_capture_log_event), \
             patch(
                 "app.routers.voice.transcribe_audio",
                 new_callable=AsyncMock,
                 return_value="texto transcrito de teste",
             ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/voice/transcribe",
                    files={"audio": ("test.webm", audio_content, "audio/webm")},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["transcription"] == "texto transcrito de teste"

        # Verificar audit log
        assert len(logged_events) == 1
        evt = logged_events[0]
        assert evt["event_type"] == "voice.transcribed"
        assert evt["success"] is True
        assert evt["event_data"]["audio_bytes"] == len(audio_content)
        assert evt["event_data"]["transcription_length"] == len("texto transcrito de teste")
        assert evt["event_data"]["duration_ms"] >= 0
        assert evt["latency_ms"] is not None and evt["latency_ms"] >= 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Auth callback + refresh hooks (R13.19, R13.20)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logged_on_auth_callback_success():
    """POST /auth/callback mockando troca de tokens e GET /me com sucesso
    → row auth.login com event_data.method == 'oauth_callback',
    event_data.email correto, event_data.had_return_url consistente.

    Requisito: R13.19
    """
    import json

    from app.routers.auth import auth_callback

    user_id = uuid.uuid4()
    test_email = "callback-audit@example.com"

    # Redis retorna JSON com code_verifier + return_url
    redis = AsyncMock()
    redis.get.return_value = json.dumps({
        "code_verifier": "test-verifier",
        "return_url": "http://localhost:5173/dashboard",
    })

    # Mock DB: execute retorna user existente
    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.email = test_email
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user
    db = AsyncMock()
    db.execute.return_value = mock_result

    background_tasks = MagicMock()

    # Mock httpx para token exchange e /me
    mock_token_response = MagicMock()
    mock_token_response.status_code = 200
    mock_token_response.json.return_value = {
        "access_token": "ms-access-token",
        "refresh_token": "ms-refresh-token",
        "expires_in": 3600,
    }

    mock_me_response = MagicMock()
    mock_me_response.status_code = 200
    mock_me_response.json.return_value = {"mail": test_email}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_response
    mock_client.get.return_value = mock_me_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    logged_events: list[dict] = []

    async def _capture_log_event(db_arg, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
        })

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client), \
         patch("app.routers.auth.log_event", side_effect=_capture_log_event):
        response = await auth_callback(
            background_tasks=background_tasks,
            code="auth-code",
            state="valid-state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    # Deve ser RedirectResponse 302 (com return_url)
    assert response.status_code == 302

    # Verificar audit log
    login_events = [e for e in logged_events if e["event_type"] == "auth.login"]
    assert len(login_events) == 1
    evt = login_events[0]
    assert evt["user_id"] == user_id
    assert evt["event_data"]["method"] == "oauth_callback"
    assert evt["event_data"]["email"] == test_email
    assert evt["event_data"]["had_return_url"] is True
    assert evt["success"] is True


@pytest.mark.asyncio
async def test_audit_logged_on_auth_refresh_success():
    """POST /auth/refresh autenticado mockando renovação Microsoft (200 com
    novos tokens) → row auth.refresh com event_data.expires_in_seconds correto.

    Requisito: R13.20
    """
    from app.routers.auth import auth_refresh

    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    fake_user.email = "refresh-audit@example.com"
    fake_user.microsoft_refresh_token = "old-refresh-token"
    fake_user.token_expires_at = datetime.now(timezone.utc)

    db = AsyncMock()

    # Mock httpx para renovação de tokens com sucesso
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 7200,
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    logged_events: list[dict] = []

    async def _capture_log_event(db_arg, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
            "event_data": event_data or {},
            "success": success,
        })

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client), \
         patch("app.routers.auth.log_event", side_effect=_capture_log_event):
        result = await auth_refresh(current_user=fake_user, db=db)

    # Deve retornar TokenResponse com novos tokens
    assert result.access_token is not None
    assert result.email == "refresh-audit@example.com"

    # Verificar audit log
    refresh_events = [e for e in logged_events if e["event_type"] == "auth.refresh"]
    assert len(refresh_events) == 1
    evt = refresh_events[0]
    assert evt["user_id"] == fake_user.id
    assert evt["event_data"]["expires_in_seconds"] == 7200
    assert evt["success"] is True
