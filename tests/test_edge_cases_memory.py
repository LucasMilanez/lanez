"""Testes de casos de borda para memória persistente (Fase 4).

6.1  test_save_memory_empty_content — content vazio → ValueError
6.2  test_save_memory_no_tags — tags=None e tags=[] → tags=[]
6.3  test_save_memory_dirty_tags — tags sujas → limpas
6.4  test_recall_memory_no_results — banco vazio → []
6.5  test_recall_memory_below_threshold — distance >= 0.5 → []
6.6  test_recall_memory_with_tags_filter — overlap() aplicado (operador &&)
6.7  test_recall_memory_limit_capped — limit=100 → SQL usa 20
6.8  test_recall_memory_updates_last_accessed — last_accessed_at atualizado
6.9  test_mcp_save_memory_missing_content — JSON-RPC error -32602
6.10 test_mcp_recall_memory_missing_query — JSON-RPC error -32602
6.11 test_mcp_list_tools_returns_8 — 8 ferramentas incluindo save/recall
6.12 test_recall_memory_filters_by_user_id — isolamento multi-tenant (R4.2)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.memory import save_memory, recall_memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_VECTOR = [0.1] * 384
USER_ID = uuid.uuid4()


def _make_db() -> AsyncMock:
    """Cria um AsyncSession mock com commit/refresh/execute/add."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


# ---------------------------------------------------------------------------
# 6.1 test_save_memory_empty_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_empty_content():
    """save_memory com content='' e content='   ' → ValueError sem db op."""
    db = _make_db()

    with pytest.raises(ValueError):
        await save_memory(db, USER_ID, content="")
    db.add.assert_not_called()
    db.commit.assert_not_awaited()

    db.reset_mock()

    with pytest.raises(ValueError):
        await save_memory(db, USER_ID, content="   ")
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6.2 test_save_memory_no_tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_save_memory_no_tags(mock_emb):
    """save_memory com tags=None e tags=[] → memória persistida com tags=[]."""
    for tags_input in (None, []):
        db = _make_db()
        # Make refresh set the memory attributes for the return dict
        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
        db.refresh = fake_refresh

        result = await save_memory(db, USER_ID, content="nota importante", tags=tags_input)

        # Memory was added to session
        db.add.assert_called_once()
        memory_obj = db.add.call_args[0][0]
        assert memory_obj.tags == []
        assert result["tags"] == []


# ---------------------------------------------------------------------------
# 6.3 test_save_memory_dirty_tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_save_memory_dirty_tags(mock_emb):
    """save_memory com tags=['', 'a', ' ', 'b'] → tags=['a', 'b']."""
    db = _make_db()

    async def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
    db.refresh = fake_refresh

    result = await save_memory(
        db, USER_ID, content="nota", tags=["", "a", " ", "b"]
    )

    memory_obj = db.add.call_args[0][0]
    assert memory_obj.tags == ["a", "b"]
    assert result["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# 6.4 test_recall_memory_no_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_no_results(mock_emb):
    """recall_memory com banco retornando vazio → []."""
    db = _make_db()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    results = await recall_memory(db, USER_ID, query="algo")

    assert results == []


# ---------------------------------------------------------------------------
# 6.5 test_recall_memory_below_threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_below_threshold(mock_emb):
    """Rows com distance >= 0.5 → recall_memory retorna [] e não atualiza."""
    db = _make_db()

    # Simular rows com distance >= 0.5
    row1 = MagicMock()
    row1.Memory = MagicMock()
    row1.distance = 0.5

    row2 = MagicMock()
    row2.Memory = MagicMock()
    row2.distance = 0.8

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2]
    db.execute = AsyncMock(return_value=mock_result)

    results = await recall_memory(db, USER_ID, query="algo")

    assert results == []
    # Only one execute call (the SELECT), no UPDATE
    assert db.execute.await_count == 1
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6.6 test_recall_memory_with_tags_filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_with_tags_filter(mock_emb):
    """recall_memory com tags=['preferencia'] → SQL contém operador && (overlap)."""
    db = _make_db()

    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await recall_memory(db, USER_ID, query="preferências", tags=["preferencia"])

    # Capture the SQLAlchemy statement passed to db.execute
    stmt = db.execute.call_args[0][0]
    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql_text = str(compiled)

    # The overlap operator in PostgreSQL is &&
    assert "&&" in sql_text, f"Expected && (overlap) in SQL, got: {sql_text}"


# ---------------------------------------------------------------------------
# 6.7 test_recall_memory_limit_capped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_limit_capped(mock_emb):
    """recall_memory com limit=100 → SQL usa LIMIT 20."""
    db = _make_db()

    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await recall_memory(db, USER_ID, query="algo", limit=100)

    stmt = db.execute.call_args[0][0]
    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql_text = str(compiled)

    # Verify the SQL contains LIMIT 20 (not 100)
    assert "LIMIT 20" in sql_text.upper(), f"Expected LIMIT 20 in SQL, got: {sql_text}"


# ---------------------------------------------------------------------------
# 6.8 test_recall_memory_updates_last_accessed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_updates_last_accessed(mock_emb):
    """recall_memory com resultados abaixo do threshold → atualiza last_accessed_at."""
    db = _make_db()

    mem_id = uuid.uuid4()
    mem_obj = MagicMock()
    mem_obj.id = mem_id
    mem_obj.content = "memória relevante"
    mem_obj.tags = ["tag1"]
    mem_obj.created_at = datetime.now(timezone.utc)

    row = MagicMock()
    row.Memory = mem_obj
    row.distance = 0.2  # Below threshold (< 0.5)

    mock_result = MagicMock()
    mock_result.all.return_value = [row]

    # First call returns SELECT results, second call is the UPDATE
    db.execute = AsyncMock(return_value=mock_result)

    results = await recall_memory(db, USER_ID, query="algo relevante")

    assert len(results) == 1
    assert results[0]["id"] == str(mem_id)

    # db.execute should be called twice: SELECT + UPDATE
    assert db.execute.await_count == 2

    # Inspect the UPDATE statement
    update_stmt = db.execute.call_args_list[1][0][0]
    from sqlalchemy.dialects import postgresql

    compiled = str(update_stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))

    assert "UPDATE memories" in compiled.upper() or "UPDATE" in compiled.upper()
    assert "last_accessed_at" in compiled

    # After M1, recall_memory no longer commits — commit is handled by get_db
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6.9 test_mcp_save_memory_missing_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_save_memory_missing_content():
    """POST /mcp/call save_memory sem content → JSON-RPC error -32602."""
    from app.routers.mcp import MCPCallRequest, call_tool

    user = _make_user()
    db = AsyncMock()
    redis = MagicMock()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-save-no-content",
        method="tools/call",
        params={"name": "save_memory", "arguments": {}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng)

    assert "error" in resp
    assert resp["error"]["code"] == -32602
    assert "content" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# 6.10 test_mcp_recall_memory_missing_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_recall_memory_missing_query():
    """POST /mcp/call recall_memory sem query → JSON-RPC error -32602."""
    from app.routers.mcp import MCPCallRequest, call_tool

    user = _make_user()
    db = AsyncMock()
    redis = MagicMock()
    graph = AsyncMock()
    searxng = AsyncMock()

    req = MCPCallRequest(
        jsonrpc="2.0",
        id="req-recall-no-query",
        method="tools/call",
        params={"name": "recall_memory", "arguments": {}},
    )

    resp = await call_tool(req, user, db, redis, graph, searxng)

    assert "error" in resp
    assert resp["error"]["code"] == -32602
    assert "query" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# 6.11 test_mcp_list_tools_returns_8
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_list_tools_returns_8():
    """GET /mcp retorna 8 ferramentas incluindo save_memory e recall_memory."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/mcp")

        assert resp.status_code == 200
        body = resp.json()
        tools = body["result"]["tools"]

        assert len(tools) == 8, f"Expected 8 tools, got {len(tools)}"

        tool_names = {t["name"] for t in tools}
        assert "save_memory" in tool_names
        assert "recall_memory" in tool_names
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# 6.12 test_recall_memory_filters_by_user_id (R4.2 — multi-tenant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_recall_memory_filters_by_user_id(mock_emb):
    """recall_memory filtra por user_id no SQL — isolamento multi-tenant."""
    db = _make_db()
    uuid_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await recall_memory(db, uuid_a, query="algo")

    stmt = db.execute.call_args[0][0]
    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql_text = str(compiled)

    # Verify user_id filter is present in the SQL
    assert "memories.user_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'" in sql_text, (
        f"Expected user_id filter in SQL, got: {sql_text}"
    )


# ---------------------------------------------------------------------------
# test_save_memory_does_not_commit (M1 invariant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_save_memory_does_not_commit(mock_emb):
    """save_memory chama db.flush() exatamente uma vez e db.commit() zero vezes."""
    db = _make_db()

    async def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)

    db.refresh = fake_refresh

    await save_memory(db, USER_ID, content="nota importante", tags=["test"])

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
