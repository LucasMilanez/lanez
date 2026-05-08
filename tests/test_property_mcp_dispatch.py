"""Property-based tests para o Dispatcher MCP — Fase 11.

Property 1: Routing Determinism
Property 2: Initialize Idempotence
Property 7: Notification Permissive Policy
Property 8: Error Code Correctness
Property 9: Session Header Exclusivity
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import (
    integers,
    lists,
    none,
    one_of,
    sampled_from,
    text,
)

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


def _setup_overrides():
    """Set up dependency overrides for all tests."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    app.dependency_overrides[get_db] = lambda: AsyncMock()


def _cleanup_overrides():
    """Clean up dependency overrides."""
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

SUPPORTED_METHODS = ["initialize", "ping", "tools/list", "tools/call", "notifications/initialized"]

supported_methods = sampled_from(SUPPORTED_METHODS)

# Generate arbitrary method strings that are NOT in the supported set
unsupported_methods = text(min_size=1, max_size=50).filter(
    lambda s: s not in SUPPORTED_METHODS
)

# Invalid jsonrpc versions
invalid_jsonrpc_versions = sampled_from(["1.0", "3.0", "abc", "", "2.1", "0.0"])

# id values for notifications
notification_ids = one_of(none(), integers(min_value=0, max_value=1000), text(min_size=1, max_size=20))


# Mock handler for tools/call that avoids DB/Graph dependencies
async def _mock_tool_handler(arguments, user, db, redis, graph, searxng):
    return {"mocked": True}


async def _noop_log_event(db, *, user_id, event_type, event_data=None,
                           success=True, error_message=None, latency_ms=None):
    pass


# ---------------------------------------------------------------------------
# Property 1: Routing Determinism
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 8.1, 8.2**
# ---------------------------------------------------------------------------


@given(method=supported_methods)
@hyp_settings(max_examples=50, deadline=None)
def test_property_routing_supported_methods(method) -> None:
    """For any method in supported set → routes to correct handler (no -32601 error).

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 8.1, 8.2**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload: dict = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                }
                # tools/call needs params with a valid tool name
                if method == "tools/call":
                    payload["params"] = {"name": "get_onenote_pages", "arguments": {}}
                elif method == "initialize":
                    payload["params"] = {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    }

                resp = await client.post("/mcp", json=payload)
                return resp

        with patch("app.routers.mcp.log_event", side_effect=_noop_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"get_onenote_pages": _mock_tool_handler}):
            resp = asyncio.run(_run())

        if method == "notifications/initialized":
            # Notification → 202
            assert resp.status_code == 202
        else:
            # All other supported methods → 200, no -32601 error
            assert resp.status_code == 200
            body = resp.json()
            # Should NOT have a -32601 error (method not found)
            if "error" in body:
                assert body["error"]["code"] != -32601, (
                    f"Supported method '{method}' should not return -32601"
                )
    finally:
        _cleanup_overrides()


@given(method=unsupported_methods)
@hyp_settings(max_examples=100, deadline=None)
def test_property_routing_unsupported_methods(method) -> None:
    """For any method NOT in supported set → returns -32601.

    **Validates: Requirements 1.6, 8.2**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                    },
                )
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body, f"Unsupported method '{method}' should return error"
        assert body["error"]["code"] == -32601, (
            f"Unsupported method '{method}' should return -32601, got {body['error']['code']}"
        )
    finally:
        _cleanup_overrides()


@given(jsonrpc_version=invalid_jsonrpc_versions)
@hyp_settings(max_examples=30, deadline=None)
def test_property_routing_invalid_jsonrpc(jsonrpc_version) -> None:
    """For any jsonrpc != '2.0' → returns -32600.

    **Validates: Requirements 1.7, 8.1**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": jsonrpc_version,
                        "id": 1,
                        "method": "ping",
                    },
                )
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body, f"Invalid jsonrpc '{jsonrpc_version}' should return error"
        assert body["error"]["code"] == -32600, (
            f"Invalid jsonrpc '{jsonrpc_version}' should return -32600, got {body['error']['code']}"
        )
    finally:
        _cleanup_overrides()


# ---------------------------------------------------------------------------
# Property 2: Initialize Idempotence
# **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
# ---------------------------------------------------------------------------


@given(repeat_count=integers(min_value=2, max_value=5))
@hyp_settings(max_examples=20, deadline=None)
def test_property_initialize_idempotence(repeat_count) -> None:
    """For any sequence of initialize requests, result body is identical (only Mcp-Session-Id varies).

    **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                results = []
                session_ids = []

                for i in range(repeat_count):
                    resp = await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": i + 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-06-18",
                                "capabilities": {},
                                "clientInfo": {"name": "test", "version": "1.0"},
                            },
                        },
                    )
                    assert resp.status_code == 200
                    body = resp.json()
                    # Normalize: result body minus the request id
                    result_body = body["result"]
                    results.append(result_body)
                    session_ids.append(resp.headers.get("mcp-session-id"))

                return results, session_ids

        results, session_ids = asyncio.run(_run())

        # All result bodies must be identical
        first_result = results[0]
        for i, result in enumerate(results[1:], start=1):
            assert result == first_result, (
                f"Initialize result at call {i} differs from first: {result} != {first_result}"
            )

        # Session IDs must all be different (UUID4 random per call)
        assert len(set(session_ids)) == len(session_ids), (
            f"Session IDs should all be unique: {session_ids}"
        )

        # Each session ID must be valid UUID4
        for sid in session_ids:
            assert sid is not None
            parsed = uuid.UUID(sid, version=4)
            assert str(parsed) == sid
    finally:
        _cleanup_overrides()


# ---------------------------------------------------------------------------
# Property 7: Notification Permissive Policy
# **Validates: Requirements 3.1, 3.2**
# ---------------------------------------------------------------------------


@given(id_value=notification_ids)
@hyp_settings(max_examples=50, deadline=None)
def test_property_notification_permissive_policy(id_value) -> None:
    """For any request with method=notifications/initialized, regardless of id presence → HTTP 202 empty body.

    **Validates: Requirements 3.1, 3.2**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload: dict = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                }
                if id_value is not None:
                    payload["id"] = id_value

                resp = await client.post("/mcp", json=payload)
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 202, (
            f"notifications/initialized with id={id_value!r} should return 202, got {resp.status_code}"
        )
        assert resp.content == b"", (
            f"notifications/initialized should have empty body, got {resp.content!r}"
        )
    finally:
        _cleanup_overrides()


# ---------------------------------------------------------------------------
# Property 8: Error Code Correctness
# **Validates: Requirements 8.1, 8.2, 8.3, 8.5**
# ---------------------------------------------------------------------------


@given(jsonrpc_version=invalid_jsonrpc_versions)
@hyp_settings(max_examples=30, deadline=None)
def test_property_error_invalid_jsonrpc_http_200(jsonrpc_version) -> None:
    """jsonrpc != '2.0' → error code -32600 with HTTP 200.

    **Validates: Requirements 8.1, 8.5**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": jsonrpc_version,
                        "id": 1,
                        "method": "ping",
                    },
                )
                return resp

        resp = asyncio.run(_run())

        # HTTP status must be 200 for JSON-RPC errors
        assert resp.status_code == 200, (
            f"JSON-RPC error should return HTTP 200, got {resp.status_code}"
        )
        body = resp.json()
        assert body["error"]["code"] == -32600
    finally:
        _cleanup_overrides()


@given(method=unsupported_methods)
@hyp_settings(max_examples=50, deadline=None)
def test_property_error_unknown_method_http_200(method) -> None:
    """Unknown method → error code -32601 with HTTP 200.

    **Validates: Requirements 8.2, 8.5**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                    },
                )
                return resp

        resp = asyncio.run(_run())

        # HTTP status must be 200 for JSON-RPC errors
        assert resp.status_code == 200, (
            f"JSON-RPC error should return HTTP 200, got {resp.status_code}"
        )
        body = resp.json()
        assert body["error"]["code"] == -32601
    finally:
        _cleanup_overrides()


@given(
    tool_name=text(min_size=1, max_size=30).filter(
        lambda s: s not in ["get_calendar_events", "search_emails", "get_onenote_pages",
                            "search_files", "web_search", "semantic_search",
                            "save_memory", "recall_memory", "get_briefing",
                            "read_file_by_url"]
    )
)
@hyp_settings(max_examples=50, deadline=None)
def test_property_error_nonexistent_tool_http_200(tool_name) -> None:
    """Non-existent tool name → error code -32601 with HTTP 200.

    **Validates: Requirements 8.2, 8.5**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {}},
                    },
                )
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 200, (
            f"JSON-RPC error should return HTTP 200, got {resp.status_code}"
        )
        body = resp.json()
        assert body["error"]["code"] == -32601
    finally:
        _cleanup_overrides()


@given(
    tool_name=sampled_from(["get_calendar_events", "search_emails", "search_files", "save_memory"])
)
@hyp_settings(max_examples=20, deadline=None)
def test_property_error_missing_required_param_http_200(tool_name) -> None:
    """Missing required tool param → error code -32602 with HTTP 200.

    **Validates: Requirements 8.3, 8.5**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {}},
                    },
                )
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 200, (
            f"JSON-RPC error should return HTTP 200, got {resp.status_code}"
        )
        body = resp.json()
        assert body["error"]["code"] == -32602, (
            f"Missing required param for '{tool_name}' should return -32602, got {body}"
        )
    finally:
        _cleanup_overrides()


# ---------------------------------------------------------------------------
# Property 9: Session Header Exclusivity
# **Validates: Requirements 2.4, 4.1**
# ---------------------------------------------------------------------------


@given(
    method=sampled_from(["ping", "tools/list", "tools/call"])
)
@hyp_settings(max_examples=30, deadline=None)
def test_property_session_header_absent_for_non_initialize(method) -> None:
    """Mcp-Session-Id header absent for non-initialize methods.

    **Validates: Requirements 2.4, 4.1**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload: dict = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                }
                if method == "tools/call":
                    # Use a tool with no required params to avoid -32602
                    payload["params"] = {"name": "get_onenote_pages", "arguments": {}}

                resp = await client.post("/mcp", json=payload)
                return resp

        with patch("app.routers.mcp.log_event", side_effect=_noop_log_event), \
             patch.dict("app.routers.mcp.TOOLS_REGISTRY", {"get_onenote_pages": _mock_tool_handler}):
            resp = asyncio.run(_run())

        # Mcp-Session-Id should NOT be present
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is None, (
            f"Mcp-Session-Id should not be present for method '{method}', got '{session_id}'"
        )
    finally:
        _cleanup_overrides()


@given(request_id=one_of(integers(min_value=1, max_value=1000), text(min_size=1, max_size=20)))
@hyp_settings(max_examples=30, deadline=None)
def test_property_session_header_present_for_initialize(request_id) -> None:
    """Mcp-Session-Id header present and valid UUID4 for initialize method.

    **Validates: Requirements 2.4, 4.1**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    },
                )
                return resp

        resp = asyncio.run(_run())

        assert resp.status_code == 200

        # Mcp-Session-Id MUST be present
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None, "Mcp-Session-Id must be present for initialize"

        # Must be valid UUID4
        parsed = uuid.UUID(session_id, version=4)
        assert str(parsed) == session_id, (
            f"Mcp-Session-Id must be valid UUID4, got '{session_id}'"
        )
    finally:
        _cleanup_overrides()


# ---------------------------------------------------------------------------
# Property 3: Statelessness
# **Validates: Requirements 4.2, 4.3**
# ---------------------------------------------------------------------------


@given(
    method_sequence=lists(
        sampled_from(["ping", "tools/list"]),
        min_size=1,
        max_size=5,
    )
)
@hyp_settings(max_examples=30, deadline=None)
def test_property_statelessness_no_initialize_required(method_sequence) -> None:
    """For any sequence of valid methods without prior initialize -> all return 200.

    **Validates: Requirements 4.2, 4.3**
    """
    _setup_overrides()

    try:
        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                statuses = []
                for i, method in enumerate(method_sequence):
                    resp = await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": i + 1,
                            "method": method,
                        },
                    )
                    statuses.append(resp.status_code)
                return statuses

        statuses = asyncio.run(_run())

        assert all(s == 200 for s in statuses), (
            f"Statelessness violated: sequence {method_sequence} -> {statuses}"
        )
    finally:
        _cleanup_overrides()
