"""Testes de casos de borda para autenticação OAuth 2.0.

Caso de Borda 1: State OAuth inválido no callback (R2.4)
Caso de Borda 2: Erro do Entra ID no callback (R2.5)
Caso de Borda 3: Refresh token expirado (R3.3)
Caso de Borda 4: Token expirado durante consulta Graph (R5.5, R6.5, R7.5, R8.5)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from fastapi import HTTPException

from app.schemas.graph import GraphDataResponse, ServiceType, WebhookNotification
from app.services.graph import GraphService, _RATE_LIMIT_WINDOW


@pytest.mark.asyncio
async def test_callback_with_invalid_state_returns_400():
    """Callback com state que não existe no Redis deve retornar HTTP 400."""
    from app.routers.auth import auth_callback

    redis = AsyncMock()
    # State não existe no Redis → get retorna None
    redis.get.return_value = None

    db = AsyncMock()
    background_tasks = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_callback(
            background_tasks=background_tasks,
            code="some-auth-code",
            state="invalid-state-value",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "State inválido ou expirado" in exc_info.value.detail

    # Verifica que o Redis foi consultado com a chave correta
    redis.get.assert_called_once_with("oauth:state:invalid-state-value")


@pytest.mark.asyncio
async def test_callback_with_missing_state_returns_400():
    """Callback sem parâmetro state (None) deve retornar HTTP 400."""
    from app.routers.auth import auth_callback

    redis = AsyncMock()
    db = AsyncMock()
    background_tasks = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_callback(
            background_tasks=background_tasks,
            code="some-auth-code",
            state=None,
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "Parâmetro state ausente" in exc_info.value.detail

    # Redis não deve ser consultado quando state é None
    redis.get.assert_not_called()


# ---------------------------------------------------------------------------
# Caso de Borda 2: Erro do Entra ID no callback (R2.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_with_entra_error_access_denied_returns_400():
    """Callback com error=access_denied deve retornar HTTP 400 com a descrição."""
    from app.routers.auth import auth_callback

    redis = AsyncMock()
    db = AsyncMock()
    background_tasks = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_callback(
            background_tasks=background_tasks,
            code=None,
            state="some-state",
            error="access_denied",
            error_description="The user denied access to your application.",
            redis=redis,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "The user denied access to your application." in exc_info.value.detail

    # Redis NÃO deve ser consultado — o erro é verificado antes do state
    redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_callback_with_entra_error_without_description_returns_400():
    """Callback com error mas sem error_description deve usar o código de erro como detail."""
    from app.routers.auth import auth_callback

    redis = AsyncMock()
    db = AsyncMock()
    background_tasks = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_callback(
            background_tasks=background_tasks,
            code=None,
            state=None,
            error="server_error",
            error_description=None,
            redis=redis,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "server_error"

    redis.get.assert_not_called()


# ---------------------------------------------------------------------------
# Caso de Borda 3: Refresh token expirado (R3.3)
# ---------------------------------------------------------------------------


def _make_fake_user() -> MagicMock:
    """Cria um User mock com tokens criptografados válidos."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.microsoft_refresh_token = "old-refresh-token"
    user.token_expires_at = datetime.now(timezone.utc)
    return user


@pytest.mark.asyncio
async def test_refresh_with_expired_token_returns_401():
    """Quando o Entra ID rejeita o refresh_token (HTTP 400), o endpoint deve retornar HTTP 401.

    Simula o cenário em que o refresh_token armazenado expirou ou foi revogado
    e o Microsoft token endpoint responde com erro.
    """
    from app.routers.auth import auth_refresh

    fake_user = _make_fake_user()
    db = AsyncMock()

    # Mock httpx.AsyncClient para simular rejeição do refresh_token pelo Entra ID
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "AADSTS700082: The refresh token has expired.",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await auth_refresh(current_user=fake_user, db=db)

    assert exc_info.value.status_code == 401
    assert "Re-autenticação necessária" in exc_info.value.detail

    # Banco NÃO deve ser atualizado quando refresh falha
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_with_revoked_token_returns_401():
    """Quando o Entra ID retorna HTTP 401 (token revogado), o endpoint deve retornar HTTP 401."""
    from app.routers.auth import auth_refresh

    fake_user = _make_fake_user()
    db = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "AADSTS50173: The provided grant has expired.",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await auth_refresh(current_user=fake_user, db=db)

    assert exc_info.value.status_code == 401
    assert "Re-autenticação necessária" in exc_info.value.detail
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_with_corrupted_stored_token_returns_401():
    """Quando o refresh_token armazenado não pode ser descriptografado, deve retornar HTTP 401.

    Simula corrupção do ciphertext no banco — a propriedade microsoft_refresh_token
    lança exceção ao tentar descriptografar.
    """
    from app.routers.auth import auth_refresh

    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    fake_user.email = "test@example.com"
    # Propriedade lança exceção ao acessar (simula ciphertext corrompido)
    type(fake_user).microsoft_refresh_token = property(
        lambda self: (_ for _ in ()).throw(Exception("InvalidToken: decryption failed"))
    )

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_refresh(current_user=fake_user, db=db)

    assert exc_info.value.status_code == 401
    assert "Re-autenticação necessária" in exc_info.value.detail
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers para Caso de Borda 4
# ---------------------------------------------------------------------------


def _make_graph_user(
    user_id: uuid.UUID | None = None,
    access_token: str = "expired-access-token",
    refresh_token: str = "valid-refresh-token",
) -> MagicMock:
    """Cria um mock de User com propriedades de token para testes Graph."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.microsoft_access_token = access_token
    user.microsoft_refresh_token = refresh_token
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return user


class FakeRedis:
    """Redis fake in-memory para testes (suporta get/set/incr/expire/ttl/delete)."""

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
        pass  # no-op para testes

    async def ttl(self, key: str) -> int:
        return _RATE_LIMIT_WINDOW

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._counters.pop(k, None)


# ---------------------------------------------------------------------------
# Caso de Borda 4: Token expirado durante consulta Graph
# (R5.5, R6.5, R7.5, R8.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_401_triggers_token_refresh_and_retry():
    """Quando a Graph API retorna 401 (token expirado), o sistema deve
    renovar o token via Entra ID e repetir a requisição uma vez,
    retornando os dados com sucesso.

    Valida Caso de Borda 4: Mock da Graph API retornando 401 na primeira
    chamada e 200 na segunda, verificar que dados são retornados.
    """
    user_id = uuid.uuid4()
    user = _make_graph_user(user_id=user_id)
    expected_data = {"value": [{"id": "evt-1", "subject": "Reunião"}]}

    fake_redis = FakeRedis()
    db = AsyncMock()
    db.get.return_value = user
    # Mock execute for _persist_graph_cache upsert query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    call_count = 0

    with respx.mock:
        # Graph API: 401 na primeira chamada, 200 na segunda
        route = respx.get("https://graph.microsoft.com/v1.0/me/events")

        def graph_side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(401)
            return httpx.Response(200, json=expected_data)

        route.mock(side_effect=graph_side_effect)

        # Token refresh endpoint: retorna novos tokens
        respx.post(
            url__startswith="https://login.microsoftonline.com/"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-refreshed-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                },
            )
        )

        async with httpx.AsyncClient() as client:
            svc = GraphService(client=client)
            result = await svc.fetch_data(
                user_id, ServiceType.CALENDAR, db, fake_redis
            )

    # 1. Dados retornados corretamente (from_cache=False)
    assert result.from_cache is False
    assert result.service == ServiceType.CALENDAR
    assert result.data == expected_data

    # 2. Token foi renovado no objeto user
    assert user.microsoft_access_token == "new-refreshed-token"

    # 3. Graph API foi chamada 2 vezes (401 + retry 200)
    assert call_count == 2

    # 4. Dados foram cacheados no Redis após sucesso
    cached = await fake_redis.get(f"lanez:{user_id}:calendar")
    assert cached is not None
    assert json.loads(cached) == expected_data


# ---------------------------------------------------------------------------
# Caso de Borda 5: clientState inválido em webhook (R10.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_invalid_client_state_returns_403():
    """Notificação de webhook com clientState incorreto deve ser rejeitada com HTTP 403.

    Valida Caso de Borda 5 / Requisito R10 (10.2): o sistema deve rejeitar
    notificações cujo clientState não corresponde ao WEBHOOK_CLIENT_STATE configurado.
    """
    from app.services.webhook import WebhookService

    notification = WebhookNotification(
        subscription_id="fake-sub-id",
        client_state="wrong-client-state",
        resource="/me/events",
        change_type="updated",
    )

    service = WebhookService()
    cache_service = MagicMock()
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.process_notification(notification, cache_service, db)

    assert exc_info.value.status_code == 403
    assert "clientState inválido" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Caso de Borda 6: Falha na renovação de subscrição (R11 / 11.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_renewal_failure_creates_new_subscription():
    """Quando a renovação (PATCH) de uma subscrição falha, o sistema deve
    deletar a subscrição antiga e criar uma nova via POST.

    Valida Caso de Borda 6 / Requisito R11 (11.6): mock PATCH retornando
    erro 404, verificar que nova subscrição é criada com POST 201.
    """
    from app.models.webhook import WebhookSubscription
    from app.services.webhook import WebhookService

    user_id = uuid.uuid4()

    # Mock da subscrição expirando
    old_sub = MagicMock(spec=WebhookSubscription)
    old_sub.user_id = user_id
    old_sub.subscription_id = "old-sub-id"
    old_sub.resource = "/me/events"
    old_sub.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    old_sub.client_state = "test-webhook-state"

    # Mock do usuário dono da subscrição
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.microsoft_access_token = "fake-access-token"

    # Mock do banco de dados
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [old_sub]
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.get.return_value = mock_user

    with respx.mock:
        # PATCH falha com 404 (subscrição não encontrada na Graph API)
        respx.patch(
            f"https://graph.microsoft.com/v1.0/subscriptions/{old_sub.subscription_id}"
        ).mock(return_value=httpx.Response(404, json={"error": "not found"}))

        # POST cria nova subscrição com sucesso
        respx.post("https://graph.microsoft.com/v1.0/subscriptions").mock(
            return_value=httpx.Response(201, json={"id": "new-sub-id"})
        )

        async with httpx.AsyncClient() as client:
            svc = WebhookService(client=client)
            await svc.renew_subscriptions(db)

    # 1. Subscrição antiga foi deletada
    db.delete.assert_called_once_with(old_sub)

    # 2. Nova subscrição foi adicionada ao banco
    db.add.assert_called_once()
    new_sub = db.add.call_args[0][0]

    # 3. Nova subscrição tem os campos corretos
    assert new_sub.subscription_id == "new-sub-id"
    assert new_sub.resource == "/me/events"
    assert new_sub.user_id == user_id

    # 4. Commit foi chamado para persistir as alterações
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Caso de Borda 7: Email Duplicado na Criação de User (R13 / 13.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_email_results_in_upsert():
    """Duas chamadas ao auth_callback com o mesmo email devem resultar em
    upsert: o segundo callback atualiza o User existente em vez de criar
    um novo registro.

    Valida Caso de Borda 7 / Requisito R13 (13.3): Tentativa de criar dois
    Users com o mesmo email deve resultar em upsert (atualizar o existente).
    """
    from app.models.user import User, encrypt_token
    from app.routers.auth import auth_callback

    test_email = "duplicate@example.com"
    first_access_token = "first-access-token"
    first_refresh_token = "first-refresh-token"
    second_access_token = "second-access-token"
    second_refresh_token = "second-refresh-token"

    # Variável para capturar o User criado na primeira chamada
    created_user: User | None = None

    # --- Mock Redis ---
    redis = AsyncMock()
    redis.get.return_value = "fake-code-verifier"

    # --- Mock DB ---
    # Precisamos de dois comportamentos distintos para db.execute:
    #   1ª chamada: scalar_one_or_none retorna None (user não existe)
    #   2ª chamada: scalar_one_or_none retorna o user criado na 1ª chamada
    db = AsyncMock()
    execute_call_count = 0

    async def db_execute_side_effect(stmt):
        nonlocal execute_call_count, created_user
        execute_call_count += 1
        mock_result = MagicMock()
        if execute_call_count == 1:
            # Primeira chamada: user não existe
            mock_result.scalar_one_or_none.return_value = None
        else:
            # Segunda chamada: retorna o user criado anteriormente
            mock_result.scalar_one_or_none.return_value = created_user
        return mock_result

    db.execute.side_effect = db_execute_side_effect

    # db.add é síncrono no SQLAlchemy — usar MagicMock (não AsyncMock)
    assigned_user_id = uuid.uuid4()

    def capture_add(obj):
        nonlocal created_user
        if isinstance(obj, User):
            obj.id = assigned_user_id
            created_user = obj

    db.add = MagicMock(side_effect=capture_add)

    # db.refresh é no-op para o mock
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    background_tasks = MagicMock()

    # --- 1ª chamada: criar User ---
    token_call_count = 0

    with respx.mock:
        # Token endpoint retorna tokens diferentes em cada chamada
        def token_side_effect(request):
            nonlocal token_call_count
            token_call_count += 1
            if token_call_count == 1:
                return httpx.Response(200, json={
                    "access_token": first_access_token,
                    "refresh_token": first_refresh_token,
                    "expires_in": 3600,
                })
            return httpx.Response(200, json={
                "access_token": second_access_token,
                "refresh_token": second_refresh_token,
                "expires_in": 3600,
            })

        respx.post(url__startswith="https://login.microsoftonline.com/").mock(
            side_effect=token_side_effect
        )

        # /me endpoint retorna sempre o mesmo email
        respx.get("https://graph.microsoft.com/v1.0/me").mock(
            return_value=httpx.Response(200, json={"mail": test_email})
        )

        result1 = await auth_callback(
            background_tasks=background_tasks,
            code="auth-code-1",
            state="state-1",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    # Verificações após 1ª chamada
    assert created_user is not None, "User deveria ter sido criado na 1ª chamada"
    first_user_id = created_user.id
    assert result1.email == test_email
    assert result1.user_id == first_user_id
    # db.add foi chamado (novo user)
    db.add.assert_called_once()

    # --- 2ª chamada: mesmo email, tokens diferentes → upsert ---
    with respx.mock:
        respx.post(url__startswith="https://login.microsoftonline.com/").mock(
            side_effect=token_side_effect
        )
        respx.get("https://graph.microsoft.com/v1.0/me").mock(
            return_value=httpx.Response(200, json={"mail": test_email})
        )

        result2 = await auth_callback(
            background_tasks=background_tasks,
            code="auth-code-2",
            state="state-2",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    # --- Verificações de upsert ---

    # 1. Apenas um db.add foi chamado (somente na 1ª chamada, não na 2ª)
    db.add.assert_called_once()

    # 2. O id do user permaneceu o mesmo (mesmo registro, atualizado in-place)
    assert result2.user_id == first_user_id

    # 3. O email permaneceu o mesmo
    assert result2.email == test_email

    # 4. Os tokens foram atualizados para os novos valores
    from app.models.user import decrypt_token
    assert decrypt_token(created_user._microsoft_access_token) == second_access_token
    assert decrypt_token(created_user._microsoft_refresh_token) == second_refresh_token

    # 5. db.commit foi chamado duas vezes (uma por chamada)
    assert db.commit.call_count == 2
