"""Testes de edge cases para o serviço de coleta de contexto de briefing.

Cobre: passthrough de event_data, filtro de emails por attendees,
e degradação graciosa quando uma fonte falha.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.briefing_context import collect_briefing_context


def _make_user() -> MagicMock:
    """Cria mock de User com id."""
    user = MagicMock()
    user.id = uuid4()
    return user


def _make_event_data(
    subject: str = "Weekly Sync",
    attendees_emails: list[str] | None = None,
) -> dict:
    """Cria event_data dict no formato Graph API."""
    if attendees_emails is None:
        attendees_emails = ["alice@example.com", "bob@example.com"]
    return {
        "subject": subject,
        "start": {"dateTime": "2024-06-01T10:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-01T11:00:00", "timeZone": "UTC"},
        "attendees": [
            {"emailAddress": {"address": email, "name": email.split("@")[0]}}
            for email in attendees_emails
        ],
    }


def _make_email(from_addr: str, to_addrs: list[str], subject: str = "Re: test") -> dict:
    """Cria email dict no formato Graph API."""
    return {
        "subject": subject,
        "from": {"emailAddress": {"address": from_addr}},
        "toRecipients": [
            {"emailAddress": {"address": addr}} for addr in to_addrs
        ],
        "bodyPreview": "Preview do email",
        "receivedDateTime": "2024-05-30T09:00:00Z",
    }


@pytest.mark.asyncio
async def test_briefing_context_collects_event():
    """Verifica que o dict retornado contém event com os dados passados (passthrough)."""
    user = _make_user()
    event_data = _make_event_data()
    db = AsyncMock()
    redis = AsyncMock()
    graph = AsyncMock()
    graph.fetch_with_params = AsyncMock(return_value={"value": []})

    with patch(
        "app.services.briefing_context.semantic_search",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.briefing_context.recall_memory",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await collect_briefing_context(
            db, redis, graph, user, event_data, history_window_days=90
        )

    assert result["event"] is event_data
    assert result["event"]["subject"] == "Weekly Sync"
    assert len(result["event"]["attendees"]) == 2


@pytest.mark.asyncio
async def test_briefing_context_filters_emails_by_attendees():
    """Mocka graph retornando 5 emails (3 com attendees, 2 sem) — resultado deve ter apenas 3."""
    user = _make_user()
    attendees = ["alice@example.com", "bob@example.com"]
    event_data = _make_event_data(attendees_emails=attendees)

    # 3 emails com attendees em from/to
    email_from_alice = _make_email("alice@example.com", ["charlie@other.com"])
    email_to_bob = _make_email("charlie@other.com", ["bob@example.com"])
    email_from_bob = _make_email("bob@example.com", ["dave@other.com"])
    # 2 emails sem attendees
    email_no_match_1 = _make_email("charlie@other.com", ["dave@other.com"])
    email_no_match_2 = _make_email("eve@other.com", ["frank@other.com"])

    all_emails = [
        email_from_alice,
        email_to_bob,
        email_from_bob,
        email_no_match_1,
        email_no_match_2,
    ]

    db = AsyncMock()
    redis = AsyncMock()
    graph = AsyncMock()
    graph.fetch_with_params = AsyncMock(return_value={"value": all_emails})

    with patch(
        "app.services.briefing_context.semantic_search",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.briefing_context.recall_memory",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await collect_briefing_context(
            db, redis, graph, user, event_data, history_window_days=90
        )

    assert len(result["emails_with_attendees"]) == 3
    assert email_from_alice in result["emails_with_attendees"]
    assert email_to_bob in result["emails_with_attendees"]
    assert email_from_bob in result["emails_with_attendees"]
    assert email_no_match_1 not in result["emails_with_attendees"]
    assert email_no_match_2 not in result["emails_with_attendees"]


@pytest.mark.asyncio
async def test_briefing_context_handles_partial_failure():
    """Mocka 1 das 4 fontes para levantar Exception — as outras 3 retornam dados."""
    user = _make_user()
    event_data = _make_event_data()

    db = AsyncMock()
    redis = AsyncMock()
    graph = AsyncMock()
    # Emails (fonte 1) falha
    graph.fetch_with_params = AsyncMock(side_effect=Exception("Graph API down"))

    onenote_results = [{"service": "onenote", "resource_id": "page1", "relevance_score": 0.8}]
    onedrive_results = [{"service": "onedrive", "resource_id": "file1", "relevance_score": 0.7}]
    memory_results = [{"id": "mem1", "content": "memory", "tags": [], "created_at": "2024-01-01", "relevance_score": 0.9}]

    async def mock_semantic_search(db, user_id, query, limit=10, services=None):
        if services == ["onenote"]:
            return onenote_results
        if services == ["onedrive"]:
            return onedrive_results
        return []

    async def mock_recall_memory(db, user_id, query, limit=5):
        return memory_results

    with patch(
        "app.services.briefing_context.semantic_search",
        side_effect=mock_semantic_search,
    ), patch(
        "app.services.briefing_context.recall_memory",
        side_effect=mock_recall_memory,
    ):
        result = await collect_briefing_context(
            db, redis, graph, user, event_data, history_window_days=90
        )

    # Nenhuma exceção propagou
    assert result["event"] is event_data
    # Emails falharam — lista vazia
    assert result["emails_with_attendees"] == []
    # As outras 3 fontes retornaram dados
    assert len(result["onenote_pages"]) == 1
    assert len(result["onedrive_files"]) == 1
    assert len(result["memories"]) == 1


# --- Testes do orquestrador (app.services.briefing) ---

from app.models.briefing import Briefing
from app.services.briefing import generate_briefing


@pytest.mark.asyncio
async def test_briefing_idempotent():
    """Se já existe Briefing para (user_id, event_id), retorna o existente sem chamar Anthropic."""
    user = _make_user()
    existing_briefing = MagicMock(spec=Briefing)
    existing_briefing.user_id = user.id
    existing_briefing.event_id = "evt-123"

    # Mock db.execute para retornar o briefing existente
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_briefing

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    redis = AsyncMock()
    graph = AsyncMock()

    with patch(
        "app.services.briefing.generate_briefing_text",
        new_callable=AsyncMock,
    ) as mock_gen:
        result = await generate_briefing(db, redis, graph, user, "evt-123")

    assert result is existing_briefing
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_briefing_uses_flush_not_commit():
    """generate_briefing usa db.flush() e NÃO db.commit() (regra M1)."""
    user = _make_user()

    # Mock db.execute para retornar None (sem briefing existente)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    redis = AsyncMock()
    graph = AsyncMock()

    event_data = {
        "subject": "Sprint Planning",
        "start": {"dateTime": "2024-06-01T10:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-01T11:00:00", "timeZone": "UTC"},
        "location": {"displayName": "Sala 1"},
        "bodyPreview": "Planejamento do sprint",
        "attendees": [
            {"emailAddress": {"address": "alice@example.com", "name": "Alice"}},
        ],
    }
    graph.fetch_with_params = AsyncMock(return_value=event_data)

    mock_context = {
        "event": event_data,
        "emails_with_attendees": [],
        "onenote_pages": [],
        "onedrive_files": [],
        "memories": [],
    }

    mock_llm_result = MagicMock()
    mock_llm_result.content = "# Briefing gerado"
    mock_llm_result.model = "claude-haiku-4-5-20251001"
    mock_llm_result.input_tokens = 500
    mock_llm_result.cache_read_tokens = 0
    mock_llm_result.cache_write_tokens = 200
    mock_llm_result.output_tokens = 300

    with patch(
        "app.services.briefing.collect_briefing_context",
        new_callable=AsyncMock,
        return_value=mock_context,
    ), patch(
        "app.services.briefing.generate_briefing_text",
        new_callable=AsyncMock,
        return_value=mock_llm_result,
    ):
        await generate_briefing(db, redis, graph, user, "evt-new-456")

    # flush DEVE ter sido chamado
    db.flush.assert_awaited_once()
    # commit NÃO deve ter sido chamado
    db.commit.assert_not_awaited()


# --- Testes do endpoint REST /briefings/{event_id} (Tarefa 7.3) ---

import uuid as _uuid_mod
from datetime import datetime as _dt, timezone as _tz

from httpx import ASGITransport, AsyncClient


def _make_briefing_row(user_id, event_id="evt-abc-123"):
    """Cria um objeto Briefing completo para testes de endpoint."""
    b = MagicMock(spec=Briefing)
    b.id = _uuid_mod.uuid4()
    b.user_id = user_id
    b.event_id = event_id
    b.event_subject = "Sprint Planning"
    b.event_start = _dt(2024, 6, 1, 10, 0, 0, tzinfo=_tz.utc)
    b.event_end = _dt(2024, 6, 1, 11, 0, 0, tzinfo=_tz.utc)
    b.attendees = ["alice@example.com", "bob@example.com"]
    b.content = "# Briefing gerado\n\nConteúdo do briefing."
    b.generated_at = _dt(2024, 6, 1, 9, 30, 0, tzinfo=_tz.utc)
    b.model_used = "claude-haiku-4-5-20251001"
    b.input_tokens = 500
    b.cache_read_tokens = 0
    b.cache_write_tokens = 200
    b.output_tokens = 300
    return b


@pytest.mark.asyncio
async def test_briefings_endpoint_returns_briefing():
    """GET /briefings/{event_id} com briefing existente retorna 200 + BriefingResponse."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()
    event_id = "evt-abc-123"
    briefing = _make_briefing_row(user.id, event_id)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = briefing

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/briefings/{event_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == event_id
        assert body["event_subject"] == "Sprint Planning"
        assert body["content"] == "# Briefing gerado\n\nConteúdo do briefing."
        assert body["model_used"] == "claude-haiku-4-5-20251001"
        assert body["input_tokens"] == 500
        assert body["cache_read_tokens"] == 0
        assert body["cache_write_tokens"] == 200
        assert body["output_tokens"] == 300
        assert len(body["attendees"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_briefings_endpoint_404_when_missing():
    """GET /briefings/inexistente com auth header retorna 404."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    user = _make_user()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/briefings/inexistente")

        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"] == "Briefing não encontrado"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
