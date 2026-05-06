"""Testes do handshake e dispatcher MCP — Fase 11.

13 testes cobrindo:
- Handshake initialize (protocolVersion, capabilities, serverInfo, Mcp-Session-Id)
- Notification notifications/initialized (202, política permissiva)
- Ping (result vazio)
- tools/list (9 tools)
- tools/call via POST /mcp (save_memory + audit)
- Método desconhecido (-32601)
- Endpoint legado POST /mcp/call (compat + warning)
- Request sem auth (401)
- Tool inexistente não gera audit
- Param obrigatório ausente não gera audit
- Métodos de protocolo não geram audit
- jsonrpc inválido (-32600)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db, get_redis
from app.dependencies import get_current_user
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.microsoft_access_token = "fake-token"
    user.microsoft_refresh_token = "fake-refresh"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return user


class FakeRedis:
    """Redis mock mínimo para testes."""

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
        pass

    async def ttl(self, key: str) -> int:
        return 60

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._counters.pop(k, None)


# ---------------------------------------------------------------------------
# Fix 1: Trailing slash — Pre-flight Opção B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trailing_slash_returns_200_no_redirect():
    """POST /mcp/ deve retornar 200 direto, sem 307. Pre-flight Opção B."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=False,  # crítico: queremos 200 direto, não 307
        ) as client:
            resp = await client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )

        assert resp.status_code == 200, (
            f"POST /mcp/ deve retornar 200 sem redirect, got {resp.status_code}"
        )
        assert resp.json()["result"] == {}
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.2 test_initialize_returns_protocol_version_and_capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_returns_protocol_version_and_capabilities():
    """POST /mcp initialize → protocolVersion, capabilities, serverInfo, Mcp-Session-Id."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                    },
                },
            )

        assert resp.status_code == 200
        body = resp.json()

        # Verify result structure
        result = body["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["capabilities"]["tools"]["listChanged"] is False
        assert result["serverInfo"]["name"] == "lanez"
        assert result["serverInfo"]["version"] == "0.1.0"

        # Verify Mcp-Session-Id header is present and valid UUID4
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None
        parsed = uuid.UUID(session_id, version=4)
        assert str(parsed) == session_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.3 test_notifications_initialized_returns_202
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notifications_initialized_returns_202():
    """POST /mcp notifications/initialized → 202 (sem id e com id)."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Caso A: sem id
            resp_a = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
            )
            assert resp_a.status_code == 202
            assert resp_a.content == b""

            # Caso B: com id (política permissiva)
            resp_b = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "notifications/initialized",
                },
            )
            assert resp_b.status_code == 202
            assert resp_b.content == b""
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.4 test_ping_returns_empty_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_returns_empty_result():
    """POST /mcp ping → result == {}."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "ping",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == {}
        assert body["id"] == 1
        assert body["jsonrpc"] == "2.0"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.5 test_tools_list_returns_9_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_list_returns_9_tools():
    """POST /mcp tools/list → 9 tools com name, description, inputSchema."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        tools = body["result"]["tools"]
        assert len(tools) == 9

        # Each tool has required fields
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.6 test_tools_call_save_memory_works_via_new_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_call_save_memory_works_via_new_endpoint():
    """POST /mcp tools/call save_memory → success + 1 audit event MCP_CALL."""
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

    async def _mock_save_memory(arguments, user, db, redis, graph, searxng):
        return {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "content": arguments["content"],
            "tags": [],
            "created_at": "2026-04-30T10:00:00+00:00",
        }

    try:
        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"save_memory": _mock_save_memory}):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "save_memory",
                            "arguments": {"content": "test memory via new endpoint"},
                        },
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["isError"] is False

        # Verify exactly 1 audit event with event_type=mcp.call
        mcp_events = [e for e in logged_events if e["event_type"] == "mcp.call"]
        assert len(mcp_events) == 1
        assert mcp_events[0]["event_data"]["tool_name"] == "save_memory"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.7 test_unknown_method_returns_minus_32601
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_method_returns_minus_32601():
    """POST /mcp method=foo/bar → error.code == -32601, HTTP 200."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "foo/bar",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.8 test_legacy_call_endpoint_still_works_with_warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_call_endpoint_still_works_with_warning(caplog):
    """POST /mcp/call tools/call save_memory → success + deprecation warning."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    async def _mock_save_memory(arguments, user, db, redis, graph, searxng):
        return {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "content": arguments["content"],
            "tags": [],
            "created_at": "2026-04-30T10:00:00+00:00",
        }

    async def _noop_log_event(db, *, user_id, event_type, event_data=None,
                               success=True, error_message=None, latency_ms=None):
        pass

    try:
        with patch("app.routers.mcp.log_event", side_effect=_noop_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"save_memory": _mock_save_memory}):
            import logging
            with caplog.at_level(logging.WARNING, logger="app.routers.mcp"):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/mcp/call",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {
                                "name": "save_memory",
                                "arguments": {"content": "test via legacy"},
                            },
                        },
                    )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["isError"] is False

        # Verify deprecation warning in logs
        assert any("deprecated endpoint POST /mcp/call" in r.message for r in caplog.records)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# Fix 2: Cobertura Req 5.3 — POST /mcp/call com method != tools/call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_call_endpoint_rejects_non_tools_call(caplog):
    """POST /mcp/call com method != tools/call -> -32601 + warning. Req 5.3."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        import logging
        with caplog.at_level(logging.WARNING, logger="app.routers.mcp"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",  # diferente de tools/call
                        "params": {},
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601
        # Warning de deprecacao ainda dispara antes do reject
        assert any("deprecated endpoint POST /mcp/call" in r.message for r in caplog.records)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.9 test_unauthenticated_request_returns_401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401():
    """POST /mcp sem Authorization → HTTP 401."""
    # Ensure no override for get_current_user
    app.dependency_overrides.pop(get_current_user, None)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {},
                },
            )

        assert resp.status_code == 401
    finally:
        pass


# ---------------------------------------------------------------------------
# 7.10 test_unknown_tool_does_not_create_audit_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_does_not_create_audit_event():
    """POST /mcp tools/call tool_inexistente → -32601, 0 audit events."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
        })

    try:
        # Verify 0 events before
        assert len(logged_events) == 0

        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "tools/call",
                        "params": {
                            "name": "tool_inexistente",
                            "arguments": {},
                        },
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["error"]["code"] == -32601

        # Verify 0 audit events after
        mcp_events = [e for e in logged_events if e["event_type"] == "mcp.call"]
        assert len(mcp_events) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.11 test_missing_required_param_does_not_create_audit_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_required_param_does_not_create_audit_event():
    """POST /mcp tools/call save_memory arguments={} → -32602, 0 audit events."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
        })

    try:
        # Verify 0 events before
        assert len(logged_events) == 0

        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "tools/call",
                        "params": {
                            "name": "save_memory",
                            "arguments": {},
                        },
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["error"]["code"] == -32602

        # Verify 0 audit events after
        mcp_events = [e for e in logged_events if e["event_type"] == "mcp.call"]
        assert len(mcp_events) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.12 test_protocol_methods_do_not_create_audit_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_methods_do_not_create_audit_event():
    """initialize, tools/list, ping, notifications/initialized → 0 audit events."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    logged_events: list[dict] = []

    async def _capture_log_event(db, *, user_id, event_type, event_data=None,
                                  success=True, error_message=None, latency_ms=None):
        logged_events.append({
            "user_id": user_id,
            "event_type": str(event_type),
        })

    try:
        # Verify 0 events before
        assert len(logged_events) == 0

        with patch("app.routers.mcp.log_event", side_effect=_capture_log_event):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # initialize
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    },
                )
                # tools/list
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                    },
                )
                # ping
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "ping",
                    },
                )
                # notifications/initialized
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                )

        # Verify 0 audit events after entire sequence
        mcp_events = [e for e in logged_events if e["event_type"] == "mcp.call"]
        assert len(mcp_events) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# 7.13 test_invalid_jsonrpc_version_returns_minus_32600
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_jsonrpc_version_returns_minus_32600():
    """POST /mcp jsonrpc='1.0' → error.code == -32600, HTTP 200."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "1.0",
                    "id": 1,
                    "method": "ping",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32600
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)
