"""Teste de degradação graciosa quando SearXNG está indisponível.

Fase 9 — Tarefa 3: garante que web_search retorna mensagem amigável
em vez de erro 500 quando SearXNG não está acessível.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.searxng import SearXNGService, SearxNGUnavailable


@pytest.mark.asyncio
async def test_searxng_connect_error_raises_unavailable():
    """Quando httpx.ConnectError ocorre, SearxNGUnavailable é levantada."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")

    service = SearXNGService(client=mock_client)

    with pytest.raises(SearxNGUnavailable, match="indisponível"):
        await service.search("test query")


@pytest.mark.asyncio
async def test_handle_web_search_returns_error_dict_when_searxng_unavailable():
    """Handler handle_web_search retorna dict com 'error' (HTTP 200, não 500)."""
    from app.routers.mcp import handle_web_search

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")
    searxng = SearXNGService(client=mock_client)

    result = await handle_web_search(
        arguments={"query": "test"},
        user=None,
        db=None,
        redis=None,
        graph=None,
        searxng=searxng,
    )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["error"] == "web_search indisponível"
    assert "demo" in result[0]["message"].lower() or "SearXNG" in result[0]["message"]
