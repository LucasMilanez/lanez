"""Testes — Fase 12: search_files com Graph Search API + leitura de conteúdo.

12 testes cobrindo:
- Integração com post_graph_search (entity_types, query_string, limit)
- Leitura de conteúdo (.txt, .docx, oversized, unsupported, error)
- Retry 401 e backoff 429 no post_graph_search
- read_drive_item_content com ficheiro > 100KB
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routers.mcp import handle_search_files
from app.services.graph import GraphService, _FILE_CONTENT_MAX_BYTES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user():
    """Cria um User mock com campos necessários."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.microsoft_access_token = "fake-access-token"
    user.microsoft_refresh_token = "fake-refresh-token"
    user.token_expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    return user


class FakeRedis:
    """Redis mock mínimo para rate limiting."""

    def __init__(self):
        self._store: dict = {}

    async def incr(self, key):
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key, ttl):
        pass

    async def ttl(self, key):
        return 900


def _make_hit(name: str, size: int = 1024, drive_id: str = "drive-1", item_id: str = "item-1"):
    """Cria um hit mock no formato da Graph Search API."""
    return {
        "resource": {
            "id": item_id,
            "name": name,
            "size": size,
            "webUrl": f"https://sharepoint.com/sites/docs/{name}",
            "lastModifiedDateTime": "2025-01-15T10:30:00Z",
            "parentReference": {
                "driveId": drive_id,
            },
        }
    }


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    """Cria um ficheiro .docx válido em memória com os parágrafos dados."""
    from docx import Document

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Teste 1: post_graph_search é chamado com entity_types e query_string correctos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_calls_post_graph_search():
    """Verifica que post_graph_search é chamado com entity_types=['driveItem'] e query_string correcto."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[])
    searxng = AsyncMock()

    await handle_search_files(
        arguments={"query": "relatório Q3"},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    graph.post_graph_search.assert_called_once()
    call_kwargs = graph.post_graph_search.call_args[1]
    assert call_kwargs["entity_types"] == ["driveItem"]
    assert call_kwargs["query_string"] == "relatório Q3"


# ---------------------------------------------------------------------------
# Teste 2: limit default é 10
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_default_limit_10():
    """Sem 'limit' nos argumentos → post_graph_search recebe limit=10."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[])
    searxng = AsyncMock()

    await handle_search_files(
        arguments={"query": "test"},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    call_kwargs = graph.post_graph_search.call_args[1]
    assert call_kwargs["limit"] == 10


# ---------------------------------------------------------------------------
# Teste 3: limit capped at 25
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_limit_capped_at_25():
    """limit=100 → post_graph_search recebe limit=25 (máximo)."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[])
    searxng = AsyncMock()

    await handle_search_files(
        arguments={"query": "test", "limit": 100},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    call_kwargs = graph.post_graph_search.call_args[1]
    assert call_kwargs["limit"] == 25


# ---------------------------------------------------------------------------
# Teste 4: retorna metadados sem content quando read_content ausente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_returns_metadata_without_read_content():
    """read_content ausente → resultado tem name, url, size_bytes, sem content."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("report.docx", 5000)])
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "report"},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    assert result["total"] == 1
    entry = result["files"][0]
    assert entry["name"] == "report.docx"
    assert entry["size_bytes"] == 5000
    assert entry["url"] == "https://sharepoint.com/sites/docs/report.docx"
    assert "content" not in entry
    assert "content_skipped" not in entry


# ---------------------------------------------------------------------------
# Teste 5: leitura de conteúdo .txt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_txt_content_read():
    """read_content=true + ficheiro .txt → read_drive_item_content chamado + content presente."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("notes.txt", 500)])
    graph.read_drive_item_content = AsyncMock(return_value=b"Hello World\nLine 2")
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "notes", "read_content": True},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    graph.read_drive_item_content.assert_called_once_with(
        user, "drive-1", "item-1", db, redis
    )
    entry = result["files"][0]
    assert entry["content"] == "Hello World\nLine 2"


# ---------------------------------------------------------------------------
# Teste 6: leitura de conteúdo .docx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_docx_content_parsed():
    """read_content=true + ficheiro .docx → content com texto dos parágrafos."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()

    docx_bytes = _make_docx_bytes(["Parágrafo 1", "Parágrafo 2", "Parágrafo 3"])

    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("contract.docx", len(docx_bytes))])
    graph.read_drive_item_content = AsyncMock(return_value=docx_bytes)
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "contract", "read_content": True},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    entry = result["files"][0]
    assert "content" in entry
    assert "Parágrafo 1" in entry["content"]
    assert "Parágrafo 2" in entry["content"]
    assert "Parágrafo 3" in entry["content"]


# ---------------------------------------------------------------------------
# Teste 7: ficheiro oversized → content_skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_oversized_file_skipped():
    """read_drive_item_content retorna None → content_skipped com 'demasiado grande'."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("big.txt", 200_000)])
    graph.read_drive_item_content = AsyncMock(return_value=None)
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "big", "read_content": True},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    entry = result["files"][0]
    assert "content_skipped" in entry
    assert "demasiado grande" in entry["content_skipped"]


# ---------------------------------------------------------------------------
# Teste 8: extensão não suportada → content_skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_unsupported_extension_skipped():
    """.pdf com read_content=true → content_skipped com 'formato não suportado'."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("report.pdf", 5000)])
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "report", "read_content": True},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    entry = result["files"][0]
    assert entry["content_skipped"] == "formato não suportado"


# ---------------------------------------------------------------------------
# Teste 9: erro de leitura gracioso
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_content_read_error_graceful():
    """read_drive_item_content levanta excepção → content_skipped com 'erro ao ler'."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()
    graph = AsyncMock()
    graph.post_graph_search = AsyncMock(return_value=[_make_hit("broken.txt", 500)])
    graph.read_drive_item_content = AsyncMock(side_effect=Exception("Network timeout"))
    searxng = AsyncMock()

    result = await handle_search_files(
        arguments={"query": "broken", "read_content": True},
        user=user,
        db=db,
        redis=redis,
        graph=graph,
        searxng=searxng,
    )

    entry = result["files"][0]
    assert "content_skipped" in entry
    assert "erro ao ler" in entry["content_skipped"]


# ---------------------------------------------------------------------------
# Teste 10: post_graph_search retry on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_graph_search_retry_on_401():
    """_post_graph retorna 401 → token refresh chamado + retry."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()

    # Simular: primeiro POST retorna 401, segundo retorna 200
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_200 = httpx.Response(200, json={
        "value": [{
            "hitsContainers": [{
                "hits": [_make_hit("found.txt")]
            }]
        }]
    })

    client = AsyncMock()
    client.post = AsyncMock(side_effect=[resp_401, resp_200])
    # Mock token refresh
    client.post_for_token = AsyncMock()

    svc = GraphService(client=client)

    with patch.object(svc, "_refresh_access_token", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = "new-token"

        hits = await svc.post_graph_search(
            user=user,
            entity_types=["driveItem"],
            query_string="test",
            fields=["name"],
            limit=10,
            db=db,
            redis=redis,
        )

    mock_refresh.assert_called_once_with(user, db)
    assert len(hits) == 1
    assert hits[0]["resource"]["name"] == "found.txt"


# ---------------------------------------------------------------------------
# Teste 11: _post_graph 429 backoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_graph_search_429_backoff():
    """_post_graph retorna 429 na primeira tentativa e 200 na segunda → resultado correcto."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()

    resp_429 = httpx.Response(429, headers={"Retry-After": "0"})
    resp_200 = httpx.Response(200, json={
        "value": [{
            "hitsContainers": [{
                "hits": [_make_hit("delayed.txt")]
            }]
        }]
    })

    client = AsyncMock()
    client.post = AsyncMock(side_effect=[resp_429, resp_200])

    svc = GraphService(client=client)

    with patch("app.services.graph.asyncio.sleep", new_callable=AsyncMock):
        hits = await svc.post_graph_search(
            user=user,
            entity_types=["driveItem"],
            query_string="test",
            fields=["name"],
            limit=10,
            db=db,
            redis=redis,
        )

    assert len(hits) == 1
    assert hits[0]["resource"]["name"] == "delayed.txt"
    assert client.post.call_count == 2


# ---------------------------------------------------------------------------
# Teste 12: read_drive_item_content com ficheiro > 100KB retorna None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_drive_item_content_too_large_returns_none():
    """resp.content com 101KB → retorna None."""
    user = _make_user()
    db = AsyncMock()
    redis = FakeRedis()

    # Criar resposta com conteúdo > 100KB
    large_content = b"x" * (_FILE_CONTENT_MAX_BYTES + 1)
    resp_200 = httpx.Response(200, content=large_content)

    client = AsyncMock()
    client.get = AsyncMock(return_value=resp_200)

    svc = GraphService(client=client)

    result = await svc.read_drive_item_content(
        user=user,
        drive_id="drive-1",
        item_id="item-1",
        db=db,
        redis=redis,
    )

    assert result is None
