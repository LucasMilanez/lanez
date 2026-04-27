"""Property-based test para retorno de process_notification.

**Validates: Requirement 9 (Retorno Tuple de process_notification)**

Propriedade 6: Para qualquer notificação com clientState válido,
process_notification retorna tuple[UUID, ServiceType] ou None — nunca bool.

    result = await process_notification(notification, cache, db)
    assert isinstance(result, tuple) or result is None
    assert not isinstance(result, bool)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import booleans, sampled_from, uuids

from app.schemas.graph import ServiceType, WebhookNotification
from app.services.webhook import SUBSCRIPTION_RESOURCES, WebhookService


VALID_RESOURCES = list(SUBSCRIPTION_RESOURCES.values())
UNKNOWN_RESOURCES = ["/me/unknown", "/me/contacts", "/me/planner", "/invalid"]


@given(
    user_id=uuids(),
    resource=sampled_from(VALID_RESOURCES),
    sub_exists=booleans(),
)
@hyp_settings(max_examples=200, deadline=None)
@pytest.mark.asyncio
async def test_process_notification_never_returns_bool(
    user_id: uuid.UUID,
    resource: str,
    sub_exists: bool,
) -> None:
    """process_notification com clientState válido retorna tuple ou None, nunca bool."""
    notification = WebhookNotification(
        subscription_id=f"sub-{user_id}",
        client_state="test-webhook-state",
        resource=resource,
        change_type="updated",
    )

    mock_result = MagicMock()
    if sub_exists:
        mock_subscription = MagicMock()
        mock_subscription.user_id = user_id
        mock_subscription.resource = resource
        mock_result.scalar_one_or_none.return_value = mock_subscription
    else:
        mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = mock_result
    cache_service = AsyncMock()

    svc = WebhookService()
    result = await svc.process_notification(notification, cache_service, db)

    # Propriedade: retorno NUNCA é bool
    assert not isinstance(result, bool), (
        f"process_notification retornou bool ({result!r}), esperado tuple ou None"
    )

    # Propriedade: retorno é tuple(UUID, ServiceType) ou None
    if result is not None:
        assert isinstance(result, tuple), f"Esperado tuple, obteve {type(result)}"
        assert len(result) == 2, f"Esperado tuple de 2 elementos, obteve {len(result)}"
        uid, stype = result
        assert isinstance(uid, uuid.UUID), f"Primeiro elemento não é UUID: {type(uid)}"
        assert isinstance(stype, ServiceType), f"Segundo elemento não é ServiceType: {type(stype)}"


@given(
    user_id=uuids(),
    resource=sampled_from(UNKNOWN_RESOURCES),
)
@hyp_settings(max_examples=100, deadline=None)
@pytest.mark.asyncio
async def test_process_notification_unknown_resource_returns_none_not_bool(
    user_id: uuid.UUID,
    resource: str,
) -> None:
    """process_notification com resource desconhecido retorna None, nunca bool."""
    notification = WebhookNotification(
        subscription_id=f"sub-{user_id}",
        client_state="test-webhook-state",
        resource=resource,
        change_type="updated",
    )

    mock_subscription = MagicMock()
    mock_subscription.user_id = user_id
    mock_subscription.resource = resource

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription

    db = AsyncMock()
    db.execute.return_value = mock_result
    cache_service = AsyncMock()

    svc = WebhookService()
    result = await svc.process_notification(notification, cache_service, db)

    assert result is None, f"Esperado None para resource desconhecido, obteve {result!r}"
    assert not isinstance(result, bool), (
        f"process_notification retornou bool ({result!r}) para resource desconhecido"
    )
