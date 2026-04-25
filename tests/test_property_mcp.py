"""Property-based tests para o Router MCP (Fase 2).

Propriedade 1: Respostas JSON-RPC sempre válidas
Propriedade 2: Descriptions de ferramentas são imutáveis
Propriedade 3: Separação de erros de protocolo vs domínio
Propriedade 4: fetch_with_params nunca usa cache
Propriedade 5: Rate limit compartilhado entre fetch_data e fetch_with_params
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import (
    dictionaries,
    integers,
    just,
    none,
    one_of,
    sampled_from,
    text,
)

from app.routers.mcp import (
    ALL_TOOLS,
    TOOLS_MAP,
    TOOLS_REGISTRY,
    call_tool,
    jsonrpc_domain_error,
    jsonrpc_error,
    jsonrpc_success,
    list_tools,
    MCPCallRequest,
)
from app.services.graph import GraphService, _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_tool_names = sampled_from(list(TOOLS_REGISTRY.keys()))
invalid_tool_names = text(min_size=1, max_size=30).filter(
    lambda s: s not in TOOLS_REGISTRY
)
all_tool_names = one_of(valid_tool_names, invalid_tool_names)

jsonrpc_ids = one_of(
    text(min_size=0, max_size=50),
    integers(min_value=-1000, max_value=1000),
    none(),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
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
# Propriedade 1: Respostas JSON-RPC sempre válidas
# ---------------------------------------------------------------------------


@given(
    tool_name=all_tool_names,
    request_id=jsonrpc_ids,
    arguments=dictionaries(text(min_size=1, max_size=10), text(max_size=20), max_size=5),
)
@hyp_settings(max_examples=200)
def test_jsonrpc_response_always_valid(tool_name, request_id, arguments) -> None:
    """Toda resposta de call_tool contém jsonrpc='2.0', id correspondente,
    e exatamente um dos campos 'result' ou 'error'."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()

    # Mock graph e searxng para retornar dados válidos
    graph = AsyncMock()
    graph.fetch_with_params = AsyncMock(return_value={"value": []})
    searxng = AsyncMock()
    searxng.search = AsyncMock(return_value=[])

    req = MCPCallRequest(
        jsonrpc="2.0",
        id=request_id,
        method="tools/call",
        params={"name": tool_name, "arguments": arguments},
    )

    resp = asyncio.get_event_loop().run_until_complete(
        call_tool(req, user, db, fake_redis, graph, searxng)
    )

    # Invariante 1: jsonrpc == "2.0"
    assert resp["jsonrpc"] == "2.0", f"jsonrpc deve ser '2.0': {resp}"

    # Invariante 2: id corresponde ao request
    assert resp["id"] == request_id, f"id deve ser {request_id!r}: {resp}"

    # Invariante 3: exatamente um de 'result' ou 'error'
    has_result = "result" in resp
    has_error = "error" in resp
    assert has_result != has_error, (
        f"Deve ter exatamente um de 'result' ou 'error': "
        f"result={has_result}, error={has_error}, resp={resp}"
    )


# ---------------------------------------------------------------------------
# Propriedade 2: Descriptions de ferramentas são imutáveis
# ---------------------------------------------------------------------------

EXPECTED_DESCRIPTIONS = {tool.name: tool.description for tool in ALL_TOOLS}


@given(iteration=integers(min_value=0, max_value=20))
@hyp_settings(max_examples=50)
def test_tool_descriptions_immutable(iteration) -> None:
    """Descriptions das ferramentas nunca mudam entre chamadas."""
    user = _make_user()

    result = asyncio.get_event_loop().run_until_complete(list_tools(user))

    tools = result["result"]["tools"]
    assert len(tools) == len(ALL_TOOLS), "Número de ferramentas deve ser constante"

    for tool in tools:
        name = tool["name"]
        assert name in EXPECTED_DESCRIPTIONS, f"Ferramenta inesperada: {name}"
        assert tool["description"] == EXPECTED_DESCRIPTIONS[name], (
            f"Description de '{name}' mudou: "
            f"esperado={EXPECTED_DESCRIPTIONS[name]!r}, obtido={tool['description']!r}"
        )


# ---------------------------------------------------------------------------
# Propriedade 3: Separação de erros de protocolo vs domínio
# ---------------------------------------------------------------------------


@given(
    tool_name=invalid_tool_names,
    request_id=jsonrpc_ids,
)
@hyp_settings(max_examples=100)
def test_protocol_error_unknown_tool(tool_name, request_id) -> None:
    """Ferramenta inexistente → campo 'error' com -32601, sem 'result'."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id=request_id,
        method="tools/call",
        params={"name": tool_name, "arguments": {}},
    )

    resp = asyncio.get_event_loop().run_until_complete(
        call_tool(req, user, db, fake_redis, graph, searxng)
    )

    assert "error" in resp, f"Deve ter campo 'error': {resp}"
    assert "result" not in resp, f"Não deve ter campo 'result': {resp}"
    assert resp["error"]["code"] == -32601


@given(
    tool_name=sampled_from(
        [n for n, t in TOOLS_MAP.items() if t.inputSchema.get("required")]
    ),
    request_id=jsonrpc_ids,
)
@hyp_settings(max_examples=100)
def test_protocol_error_missing_params(tool_name, request_id) -> None:
    """Parâmetros obrigatórios ausentes → campo 'error' com -32602, sem 'result'."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id=request_id,
        method="tools/call",
        params={"name": tool_name, "arguments": {}},
    )

    resp = asyncio.get_event_loop().run_until_complete(
        call_tool(req, user, db, fake_redis, graph, searxng)
    )

    assert "error" in resp, f"Deve ter campo 'error': {resp}"
    assert "result" not in resp, f"Não deve ter campo 'result': {resp}"
    assert resp["error"]["code"] == -32602


@given(request_id=jsonrpc_ids)
@hyp_settings(max_examples=50)
def test_domain_error_has_result_not_error(request_id) -> None:
    """Erros de domínio (exceção no handler) → campo 'result' com isError=true, sem 'error'."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()
    graph = AsyncMock()
    graph.fetch_with_params = AsyncMock(
        side_effect=Exception("Simulated domain error")
    )
    searxng = AsyncMock()

    # Usar get_calendar_events com params válidos para forçar execução do handler
    req = MCPCallRequest(
        jsonrpc="2.0",
        id=request_id,
        method="tools/call",
        params={
            "name": "get_calendar_events",
            "arguments": {"start": "2026-01-01", "end": "2026-01-31"},
        },
    )

    resp = asyncio.get_event_loop().run_until_complete(
        call_tool(req, user, db, fake_redis, graph, searxng)
    )

    assert "result" in resp, f"Deve ter campo 'result': {resp}"
    assert "error" not in resp, f"Não deve ter campo 'error': {resp}"
    assert resp["result"]["isError"] is True


# ---------------------------------------------------------------------------
# Propriedade 4: fetch_with_params nunca usa cache
# ---------------------------------------------------------------------------


@given(
    endpoint=sampled_from(["/me/events", "/me/messages", "/me/onenote/pages"]),
    param_key=text(min_size=1, max_size=10),
    param_val=text(max_size=20),
)
@hyp_settings(max_examples=100, deadline=None)
def test_fetch_with_params_never_uses_cache(endpoint, param_key, param_val) -> None:
    """fetch_with_params nunca invoca cache.get() ou cache.set()."""
    user = _make_user()
    db = AsyncMock()
    fake_redis = FakeRedis()
    graph_data = {"value": []}

    with respx.mock:
        respx.get(url__startswith="https://graph.microsoft.com/").mock(
            return_value=httpx.Response(200, json=graph_data)
        )

        async def _run():
            async with httpx.AsyncClient() as client:
                svc = GraphService(client=client)

                # Patch CacheService para rastrear chamadas
                with patch("app.services.cache.CacheService") as MockCache:
                    mock_cache_instance = MockCache.return_value
                    mock_cache_instance.get = AsyncMock(return_value=None)
                    mock_cache_instance.set = AsyncMock()

                    result = await svc.fetch_with_params(
                        user, endpoint, {param_key: param_val}, db, fake_redis
                    )

                    # Verificar que cache nunca foi usado
                    mock_cache_instance.get.assert_not_called()
                    mock_cache_instance.set.assert_not_called()

                return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result == graph_data


# ---------------------------------------------------------------------------
# Propriedade 5: Rate limit compartilhado entre fetch_data e fetch_with_params
# ---------------------------------------------------------------------------


@given(user_id=just(uuid.uuid4()))
@hyp_settings(max_examples=50, deadline=None)
def test_rate_limit_shared_key(user_id) -> None:
    """fetch_data e fetch_with_params usam a mesma chave Redis de rate limit."""

    class SpyRedis(FakeRedis):
        def __init__(self):
            super().__init__()
            self.incr_keys: list[str] = []

        async def incr(self, key: str) -> int:
            self.incr_keys.append(key)
            return await super().incr(key)

    user = _make_user()
    user.id = user_id
    db = AsyncMock()
    graph_data = {"value": []}

    expected_key = f"lanez:ratelimit:{user_id}"

    with respx.mock:
        respx.get(url__startswith="https://graph.microsoft.com/").mock(
            return_value=httpx.Response(200, json=graph_data)
        )

        async def _run():
            async with httpx.AsyncClient() as client:
                svc = GraphService(client=client)

                # Testar fetch_with_params
                spy_redis_1 = SpyRedis()
                await svc.fetch_with_params(
                    user, "/me/events", {"$top": "10"}, db, spy_redis_1
                )

                # Testar fetch_data
                spy_redis_2 = SpyRedis()
                db.get = AsyncMock(return_value=user)
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                db.execute = AsyncMock(return_value=mock_result)

                from app.schemas.graph import ServiceType

                await svc.fetch_data(user_id, ServiceType.CALENDAR, db, spy_redis_2)

                return spy_redis_1.incr_keys, spy_redis_2.incr_keys

        keys_1, keys_2 = asyncio.get_event_loop().run_until_complete(_run())

        # Ambos devem usar a mesma chave de rate limit
        assert expected_key in keys_1, (
            f"fetch_with_params deve usar chave '{expected_key}': {keys_1}"
        )
        assert expected_key in keys_2, (
            f"fetch_data deve usar chave '{expected_key}': {keys_2}"
        )
