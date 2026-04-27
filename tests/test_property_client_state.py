"""Property-based test para validação de clientState em webhooks.

**Validates: Requirements 10.1, 10.2**

Propriedade 5: Notificações com clientState correto devem ser aceitas;
notificações com clientState incorreto devem ser rejeitadas com HTTP 403.

    validate(correct_state) == True AND validate(any_other_state) == False
    para todo state diferente do configurado.
"""

import uuid

import pytest
from fastapi import HTTPException
from hypothesis import assume, given, settings as hyp_settings
from hypothesis.strategies import text
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.schemas.graph import WebhookNotification
from app.services.webhook import WebhookService


@given(random_state=text(min_size=0))
@hyp_settings(max_examples=200, deadline=None)
@pytest.mark.asyncio
async def test_invalid_client_state_raises_403(random_state: str) -> None:
    """Qualquer clientState diferente do configurado deve resultar em HTTP 403."""
    assume(random_state != settings.WEBHOOK_CLIENT_STATE)

    notification = WebhookNotification(
        subscription_id="sub-prop-test",
        client_state=random_state,
        resource="/me/events",
        change_type="updated",
    )
    db = AsyncMock()
    cache_service = AsyncMock()
    svc = WebhookService()

    with pytest.raises(HTTPException) as exc_info:
        await svc.process_notification(notification, cache_service, db)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_correct_client_state_is_accepted() -> None:
    """O clientState configurado deve ser aceito sem levantar HTTP 403."""
    mock_subscription = MagicMock()
    mock_subscription.user_id = uuid.uuid4()
    mock_subscription.resource = "/me/events"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription

    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()

    notification = WebhookNotification(
        subscription_id="sub-valid",
        client_state=settings.WEBHOOK_CLIENT_STATE,
        resource="/me/events",
        change_type="updated",
    )
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is not None
    assert isinstance(result, tuple)
    cache_service.invalidate.assert_called_once()
