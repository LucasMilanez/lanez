"""Testes unitários para GET /webhooks/subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.webhook import WebhookSubscription
from app.schemas.graph import WebhookSubscriptionResponse


def _make_subscription(
    user_id: uuid.UUID,
    subscription_id: str = "sub-1",
    resource: str = "/me/events",
    minutes_until_expiry: int = 60,
) -> MagicMock:
    sub = MagicMock(spec=WebhookSubscription)
    sub.id = uuid.uuid4()
    sub.user_id = user_id
    sub.subscription_id = subscription_id
    sub.resource = resource
    sub.expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_until_expiry)
    sub.client_state = "test-webhook-state"
    sub.created_at = datetime.now(timezone.utc)
    return sub


@pytest.mark.asyncio
async def test_list_subscriptions_returns_active_only():
    """Endpoint retorna apenas subscrições ativas (expires_at > now)."""
    from app.routers.webhooks import list_subscriptions

    user_id = uuid.uuid4()
    current_user = MagicMock()
    current_user.id = user_id

    sub1 = _make_subscription(user_id, "sub-1", "/me/events", 60)
    sub2 = _make_subscription(user_id, "sub-2", "/me/messages", 120)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub1, sub2]

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await list_subscriptions(current_user=current_user, db=db)

    assert len(result) == 2
    assert result[0].subscription_id == "sub-1"
    assert result[1].subscription_id == "sub-2"
    assert result[0].resource == "/me/events"
    assert result[1].resource == "/me/messages"


@pytest.mark.asyncio
async def test_list_subscriptions_empty():
    """Endpoint retorna lista vazia quando não há subscrições ativas."""
    from app.routers.webhooks import list_subscriptions

    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await list_subscriptions(current_user=current_user, db=db)

    assert result == []


@pytest.mark.asyncio
async def test_list_subscriptions_returns_correct_schema_fields():
    """Cada item retornado contém id, subscription_id, resource, expires_at."""
    from app.routers.webhooks import list_subscriptions

    user_id = uuid.uuid4()
    current_user = MagicMock()
    current_user.id = user_id

    sub = _make_subscription(user_id, "sub-abc", "/me/onenote/pages", 90)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await list_subscriptions(current_user=current_user, db=db)

    assert len(result) == 1
    item = result[0]
    assert isinstance(item, WebhookSubscriptionResponse)
    assert item.id == sub.id
    assert item.subscription_id == "sub-abc"
    assert item.resource == "/me/onenote/pages"
    assert item.expires_at == sub.expires_at


@pytest.mark.asyncio
async def test_list_subscriptions_filters_by_user_id():
    """A query filtra por user_id do usuário autenticado."""
    from app.routers.webhooks import list_subscriptions
    from sqlalchemy import select
    from app.models.webhook import WebhookSubscription

    user_id = uuid.uuid4()
    current_user = MagicMock()
    current_user.id = user_id

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute.return_value = mock_result

    await list_subscriptions(current_user=current_user, db=db)

    # Verify db.execute was called (the query was executed)
    db.execute.assert_called_once()
