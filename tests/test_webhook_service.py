"""Testes unitários para WebhookService.create_subscriptions().

Usa respx para mockar chamadas HTTP à Graph API.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest
import respx

from app.schemas.graph import ServiceType
from app.services.webhook import (
    RESOURCE_TO_SERVICE,
    SUBSCRIPTION_RESOURCES,
    WebhookService,
    _EXPIRATION_MINUTES,
)


# ---------------------------------------------------------------------------
# Tests — SUBSCRIPTION_RESOURCES mapping
# ---------------------------------------------------------------------------


def test_subscription_resources_has_all_services():
    """SUBSCRIPTION_RESOURCES deve mapear todos os 4 ServiceTypes."""
    assert set(SUBSCRIPTION_RESOURCES.keys()) == {
        ServiceType.CALENDAR,
        ServiceType.MAIL,
        ServiceType.ONENOTE,
        ServiceType.ONEDRIVE,
    }


def test_subscription_resources_values():
    """SUBSCRIPTION_RESOURCES deve mapear para os recursos Graph corretos."""
    assert SUBSCRIPTION_RESOURCES[ServiceType.CALENDAR] == "/me/events"
    assert SUBSCRIPTION_RESOURCES[ServiceType.MAIL] == "/me/messages"
    assert SUBSCRIPTION_RESOURCES[ServiceType.ONENOTE] == "/me/onenote/pages"
    assert SUBSCRIPTION_RESOURCES[ServiceType.ONEDRIVE] == "/me/drive/root"


# ---------------------------------------------------------------------------
# Tests — create_subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_subscriptions_success():
    """Cria subscrições para os 4 serviços com sucesso."""
    user_id = uuid.uuid4()
    access_token = "fake-access-token"
    db = AsyncMock()

    sub_counter = 0

    def make_response(request):
        nonlocal sub_counter
        sub_counter += 1
        return httpx.Response(201, json={"id": f"sub-{sub_counter}"})

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            side_effect=make_response
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            result = await svc.create_subscriptions(user_id, access_token, db)

    assert len(result) == 4
    assert db.add.call_count == 4
    db.commit.assert_called_once()

    # Verificar que cada subscrição tem os campos corretos
    for sub in result:
        assert sub.user_id == user_id
        assert sub.subscription_id.startswith("sub-")
        assert sub.resource in SUBSCRIPTION_RESOURCES.values()


@pytest.mark.asyncio
async def test_create_subscriptions_sends_correct_body():
    """Verifica que o body do POST contém os campos obrigatórios."""
    user_id = uuid.uuid4()
    access_token = "fake-token"
    db = AsyncMock()
    captured_bodies = []

    def capture_request(request):
        import json
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(201, json={"id": f"sub-{len(captured_bodies)}"})

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            side_effect=capture_request
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.create_subscriptions(user_id, access_token, db)

    assert len(captured_bodies) == 4
    for body in captured_bodies:
        assert body["changeType"] == "created,updated,deleted"
        assert "notificationUrl" in body
        assert body["notificationUrl"].endswith("/webhooks/graph")
        assert "resource" in body
        assert "expirationDateTime" in body
        assert body["clientState"] == "test-webhook-state"


@pytest.mark.asyncio
async def test_create_subscriptions_partial_failure():
    """Se uma subscrição falha, as outras ainda são criadas."""
    user_id = uuid.uuid4()
    access_token = "fake-token"
    db = AsyncMock()

    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return httpx.Response(400, json={"error": "bad request"})
        return httpx.Response(201, json={"id": f"sub-{call_count}"})

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            side_effect=side_effect
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            result = await svc.create_subscriptions(user_id, access_token, db)

    assert len(result) == 3
    assert db.add.call_count == 3
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_subscriptions_all_fail():
    """Se todas as subscrições falham, retorna lista vazia sem commit."""
    user_id = uuid.uuid4()
    access_token = "fake-token"
    db = AsyncMock()

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            result = await svc.create_subscriptions(user_id, access_token, db)

    assert len(result) == 0
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_subscriptions_http_error():
    """Erros de rede são tratados sem interromper o loop."""
    user_id = uuid.uuid4()
    access_token = "fake-token"
    db = AsyncMock()

    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(201, json={"id": f"sub-{call_count}"})

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            side_effect=side_effect
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            result = await svc.create_subscriptions(user_id, access_token, db)

    assert len(result) == 3
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_subscriptions_uses_bearer_token():
    """Verifica que o header Authorization contém o Bearer token."""
    user_id = uuid.uuid4()
    access_token = "my-secret-token"
    db = AsyncMock()
    captured_headers = []

    def capture_request(request):
        captured_headers.append(dict(request.headers))
        return httpx.Response(201, json={"id": "sub-1"})

    with respx.mock:
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            side_effect=capture_request
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.create_subscriptions(user_id, access_token, db)

    for headers in captured_headers:
        assert headers["authorization"] == f"Bearer {access_token}"


# ---------------------------------------------------------------------------
# Tests — RESOURCE_TO_SERVICE reverse mapping
# ---------------------------------------------------------------------------


def test_resource_to_service_has_all_resources():
    """RESOURCE_TO_SERVICE deve mapear todos os 4 recursos de volta para ServiceType."""
    assert len(RESOURCE_TO_SERVICE) == 4
    for service_type, resource in SUBSCRIPTION_RESOURCES.items():
        assert RESOURCE_TO_SERVICE[resource] == service_type


# ---------------------------------------------------------------------------
# Tests — process_notification
# ---------------------------------------------------------------------------

from unittest.mock import patch, PropertyMock

from fastapi import HTTPException

from app.schemas.graph import WebhookNotification


@pytest.mark.asyncio
async def test_process_notification_invalid_client_state():
    """Notificação com clientState inválido deve levantar HTTPException 403."""
    notification = WebhookNotification(
        subscription_id="sub-1",
        client_state="wrong-state",
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
async def test_process_notification_subscription_not_found():
    """Retorna False quando subscription_id não existe no banco."""
    notification = WebhookNotification(
        subscription_id="nonexistent-sub",
        client_state="test-webhook-state",
        resource="/me/events",
        change_type="updated",
    )

    # Mock db.execute para retornar resultado vazio
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is False
    cache_service.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_process_notification_unknown_resource():
    """Retorna False quando o resource da subscrição não mapeia para nenhum ServiceType."""
    user_id = uuid.uuid4()
    notification = WebhookNotification(
        subscription_id="sub-1",
        client_state="test-webhook-state",
        resource="/me/unknown",
        change_type="updated",
    )

    # Mock subscrição com resource desconhecido
    mock_subscription = MagicMock()
    mock_subscription.user_id = user_id
    mock_subscription.resource = "/me/unknown"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription
    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is False
    cache_service.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_process_notification_success_calendar():
    """Processa notificação de calendar com sucesso e invalida cache."""
    user_id = uuid.uuid4()
    notification = WebhookNotification(
        subscription_id="sub-calendar",
        client_state="test-webhook-state",
        resource="/me/events",
        change_type="updated",
    )

    mock_subscription = MagicMock()
    mock_subscription.user_id = user_id
    mock_subscription.resource = "/me/events"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription
    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is True
    cache_service.invalidate.assert_called_once_with(str(user_id), ServiceType.CALENDAR)


@pytest.mark.asyncio
async def test_process_notification_success_mail():
    """Processa notificação de mail com sucesso e invalida cache."""
    user_id = uuid.uuid4()
    notification = WebhookNotification(
        subscription_id="sub-mail",
        client_state="test-webhook-state",
        resource="/me/messages",
        change_type="created",
    )

    mock_subscription = MagicMock()
    mock_subscription.user_id = user_id
    mock_subscription.resource = "/me/messages"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription
    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is True
    cache_service.invalidate.assert_called_once_with(str(user_id), ServiceType.MAIL)


@pytest.mark.asyncio
async def test_process_notification_success_onedrive():
    """Processa notificação de onedrive com sucesso e invalida cache."""
    user_id = uuid.uuid4()
    notification = WebhookNotification(
        subscription_id="sub-drive",
        client_state="test-webhook-state",
        resource="/me/drive/root",
        change_type="deleted",
    )

    mock_subscription = MagicMock()
    mock_subscription.user_id = user_id
    mock_subscription.resource = "/me/drive/root"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_subscription
    db = AsyncMock()
    db.execute.return_value = mock_result

    cache_service = AsyncMock()
    svc = WebhookService()

    result = await svc.process_notification(notification, cache_service, db)

    assert result is True
    cache_service.invalidate.assert_called_once_with(str(user_id), ServiceType.ONEDRIVE)


# ---------------------------------------------------------------------------
# Tests — renew_subscriptions
# ---------------------------------------------------------------------------

from app.models.webhook import WebhookSubscription


def _make_mock_subscription(
    user_id: uuid.UUID,
    subscription_id: str = "sub-expiring",
    resource: str = "/me/events",
    expires_at: datetime | None = None,
) -> MagicMock:
    """Helper para criar um mock de WebhookSubscription."""
    sub = MagicMock(spec=WebhookSubscription)
    sub.user_id = user_id
    sub.subscription_id = subscription_id
    sub.resource = resource
    sub.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(minutes=30))
    sub.client_state = "test-webhook-state"
    return sub


def _make_mock_user(user_id: uuid.UUID, access_token: str = "fake-access-token") -> MagicMock:
    """Helper para criar um mock de User com access_token descriptografado."""
    user = MagicMock()
    user.id = user_id
    user.microsoft_access_token = access_token
    return user


@pytest.mark.asyncio
async def test_renew_subscriptions_no_expiring():
    """Quando não há subscrições expirando, não faz nada."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = mock_result

    async with httpx.AsyncClient() as client:
        svc = WebhookService(client=client)
        await svc.renew_subscriptions(db)

    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_renew_subscriptions_patch_success():
    """PATCH com sucesso atualiza expires_at da subscrição."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id)
    user = _make_mock_user(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            return_value=httpx.Response(200, json={"id": sub.subscription_id})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    # expires_at should have been updated
    assert sub.expires_at > datetime.now(timezone.utc) + timedelta(minutes=4000)
    db.commit.assert_called_once()
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_renew_subscriptions_patch_fails_recreates():
    """Quando PATCH falha, deleta subscrição antiga e cria nova via POST."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id, resource="/me/events")
    user = _make_mock_user(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            return_value=httpx.Response(201, json={"id": "new-sub-id"})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    db.delete.assert_called_once_with(sub)
    db.add.assert_called_once()
    new_sub = db.add.call_args[0][0]
    assert new_sub.subscription_id == "new-sub-id"
    assert new_sub.resource == "/me/events"
    assert new_sub.user_id == user_id
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_renew_subscriptions_patch_http_error_recreates():
    """Quando PATCH lança HTTPError, deleta e recria subscrição."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id)
    user = _make_mock_user(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            return_value=httpx.Response(201, json={"id": "recreated-sub"})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    db.delete.assert_called_once_with(sub)
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_renew_subscriptions_user_not_found():
    """Se o usuário não existe, remove a subscrição órfã."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = None  # Usuário não encontrado

    async with httpx.AsyncClient() as client:
        svc = WebhookService(client=client)
        await svc.renew_subscriptions(db)

    db.delete.assert_called_once_with(sub)
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_renew_subscriptions_recreate_post_fails():
    """Se o POST de recriação falha, não adiciona nova subscrição."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id)
    user = _make_mock_user(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    db.delete.assert_called_once_with(sub)
    db.add.assert_not_called()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_renew_subscriptions_sends_correct_patch_body():
    """Verifica que o PATCH envia expirationDateTime no body."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id, subscription_id="sub-check-body")
    user = _make_mock_user(user_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    captured_body = {}

    def capture_patch(request):
        import json
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={"id": sub.subscription_id})

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            side_effect=capture_patch
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    assert "expirationDateTime" in captured_body
    assert captured_body["expirationDateTime"].endswith("Z")


@pytest.mark.asyncio
async def test_renew_subscriptions_uses_bearer_token():
    """Verifica que o PATCH usa o Bearer token do usuário."""
    user_id = uuid.uuid4()
    sub = _make_mock_subscription(user_id, subscription_id="sub-auth")
    user = _make_mock_user(user_id, access_token="user-secret-token")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = user

    captured_headers = []

    def capture_headers(request):
        captured_headers.append(dict(request.headers))
        return httpx.Response(200, json={"id": sub.subscription_id})

    with respx.mock:
        respx.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}").mock(
            side_effect=capture_headers
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    assert len(captured_headers) == 1
    assert captured_headers[0]["authorization"] == "Bearer user-secret-token"


@pytest.mark.asyncio
async def test_renew_subscriptions_exception_does_not_propagate():
    """Exceções inesperadas são capturadas e não propagam (background loop safety)."""
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("DB connection lost")

    async with httpx.AsyncClient() as client:
        svc = WebhookService(client=client)
        # Should not raise
        await svc.renew_subscriptions(db)
