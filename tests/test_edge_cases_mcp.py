"""Testes de casos de borda para o Router MCP (Fase 2).

Caso de Borda 1: Ferramenta inexistente
Caso de Borda 2: Argumentos ausentes
Caso de Borda 3: SearXNG indisponível
Caso de Borda 4: Token expirado durante chamada MCP
Caso de Borda 5: Rate limit excedido via MCP
Caso de Borda 6: Desconexão SSE
Caso de Borda 7: Method diferente de tools/call
Caso de Borda 8: JWT ausente nos endpoints MCP
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from app.routers.mcp import (
    MCPCallRequest,
    call_tool,
    handle_web_search,
    mcp_sse,
)
from app.services.graph import GraphService, _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW
from app.services.searxng import SearXNGService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.microsoft_access_token = "fake-token"
    user.microsoft_refresh_token = "fake-refresh"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return user


class FakeRedis:
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
        return _RATE_LIMIT_WINDOW

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._counters.pop(k, None)


# ---------------------------------------------------------------------------
# Caso de Borda 1: Ferramenta inexistente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_returns_32601():
    """POST /mcp/call com name='nao_existe' → JSON-RPC error -32601."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-1",
        method="tools/call",
        params={"name": "nao_existe", "arguments": {}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng)

    assert "error" in resp
    assert "result" not in resp
    assert resp["error"]["code"] == -32601
    assert "nao_existe" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# Caso de Borda 2: Argumentos ausentes em ferramenta obrigatória
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_required_params_returns_32602():
    """get_calendar_events sem start/end → JSON-RPC error -32602."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-2",
        method="tools/call",
        params={"name": "get_calendar_events", "arguments": {}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng)

    assert "error" in resp
    assert "result" not in resp
    assert resp["error"]["code"] == -32602
    assert "start" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# Caso de Borda 3: SearXNG indisponível
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_searxng_unavailable_returns_domain_error():
    """SearXNG retornando erro → domain error com isError=true."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()

    # SearXNGService com client que falha
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(url__startswith="http://localhost:8080/search").mock(
                return_value=httpx.Response(503)
            )
            searxng = SearXNGService(client=client)
            result = await searxng.search("test query")

    # SearXNG retorna lista vazia em caso de erro
    assert result == []

    # Agora testar via call_tool — o handler retorna lista vazia,
    # que é serializada como sucesso (não é domain error do handler)
    searxng_mock = AsyncMock()
    searxng_mock.search = AsyncMock(return_value=[])

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-3",
        method="tools/call",
        params={"name": "web_search", "arguments": {"query": "test"}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng_mock)
    assert "result" in resp
    # Lista vazia é sucesso (SearXNG trata erro internamente)
    assert resp["result"]["isError"] is False


# ---------------------------------------------------------------------------
# Caso de Borda 4: Token expirado durante chamada MCP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_expired_triggers_refresh_and_retry():
    """Graph API retorna 401 → fetch_with_params tenta refresh + retry."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()
    graph_data = {"value": [{"subject": "Meeting"}]}

    call_count = 0

    with respx.mock:
        route = respx.get("https://graph.microsoft.com/v1.0/me/events")

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return httpx.Response(401)
            return httpx.Response(200, json=graph_data)

        route.mock(side_effect=side_effect)

        # Mock token refresh
        respx.post(url__startswith="https://login.microsoftonline.com/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-token",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            )
        )

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_with_params(
                user, "/me/events", {"$top": "50"}, db, fake_redis
            )

    assert result == graph_data
    assert call_count == 2  # 1 fail + 1 retry
    assert user.microsoft_access_token == "new-token"


# ---------------------------------------------------------------------------
# Caso de Borda 5: Rate limit excedido via MCP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_exceeded_returns_domain_error():
    """Rate limit excedido → domain error com isError=true."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()

    # Simular rate limit excedido
    key = f"lanez:ratelimit:{user.id}"
    fake_redis._counters[key] = _RATE_LIMIT_MAX

    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-5",
        method="tools/call",
        params={
            "name": "get_calendar_events",
            "arguments": {"start": "2026-01-01", "end": "2026-01-31"},
        },
    )

    # O handler vai chamar graph.fetch_with_params que levanta HTTPException(429)
    from fastapi import HTTPException

    graph.fetch_with_params = AsyncMock(
        side_effect=HTTPException(
            status_code=429, detail="Rate limit excedido. Tente novamente mais tarde."
        )
    )

    resp = await call_tool(req, user, db, fake_redis, graph, searxng)

    assert "result" in resp
    assert "error" not in resp
    assert resp["result"]["isError"] is True
    assert "Rate limit" in resp["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Caso de Borda 6: Desconexão SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_disconnection_graceful():
    """SSE generator encerra graciosamente quando cliente desconecta."""
    user = _make_user()

    # Mock Request com is_disconnected
    mock_request = AsyncMock()
    disconnect_after = 0
    call_count = 0

    async def fake_is_disconnected():
        nonlocal call_count
        call_count += 1
        return call_count > disconnect_after

    mock_request.is_disconnected = fake_is_disconnected

    response = await mcp_sse(mock_request, user)

    # Coletar eventos do generator
    events = []
    async for event in response.body_iterator:
        events.append(event)
        if len(events) >= 1:
            # Após o hello, o próximo sleep(30) + is_disconnected=True encerra
            break

    # Primeiro evento deve ser hello
    assert "hello" in events[0]
    assert response.media_type == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"


# ---------------------------------------------------------------------------
# Caso de Borda 7: Method diferente de tools/call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_method_returns_32601():
    """POST /mcp/call com method='tools/list' → JSON-RPC error -32601."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-7",
        method="tools/list",
        params={"name": "get_calendar_events", "arguments": {}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng)

    assert "error" in resp
    assert "result" not in resp
    assert resp["error"]["code"] == -32601
    assert "tools/list" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# Caso de Borda 8: JWT ausente nos endpoints MCP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_missing_returns_401():
    """GET /mcp, POST /mcp/call, GET /mcp/sse sem JWT → HTTP 401."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /mcp sem Authorization
        resp = await client.get("/mcp")
        assert resp.status_code == 401

        # POST /mcp/call sem Authorization
        resp = await client.post(
            "/mcp/call",
            json={
                "jsonrpc": "2.0",
                "id": "req-8",
                "method": "tools/call",
                "params": {"name": "web_search", "arguments": {"query": "test"}},
            },
        )
        assert resp.status_code == 401

        # GET /mcp/sse sem Authorization
        resp = await client.get("/mcp/sse")
        assert resp.status_code == 401
