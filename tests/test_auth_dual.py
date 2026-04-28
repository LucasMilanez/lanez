"""Testes de autenticação dual (Cookie + Bearer) — Fase 6a.

Verifica que get_current_user aceita JWT via cookie HttpOnly OU header
Authorization Bearer, com prioridade para cookie.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.dependencies import _extract_token, get_current_user

_JWT_ALGORITHM = "HS256"


def _make_jwt(user_id: str | uuid.UUID) -> str:
    """Cria JWT válido assinado com SECRET_KEY de teste."""
    payload = {
        "user_id": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)


def _make_request(
    cookie_token: str | None = None,
    bearer_token: str | None = None,
) -> MagicMock:
    """Cria mock de Request com cookies e/ou headers configurados."""
    request = MagicMock()
    request.cookies = {}
    if cookie_token:
        request.cookies["lanez_session"] = cookie_token

    auth_header = ""
    if bearer_token:
        auth_header = f"Bearer {bearer_token}"
    request.headers = MagicMock()
    request.headers.get = lambda key, default="": (
        auth_header if key == "Authorization" else default
    )
    return request


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    """Cria User mock."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = "test@example.com"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_sync_at = None
    user.created_at = datetime.now(timezone.utc)
    return user


# ---------------------------------------------------------------------------
# _extract_token
# ---------------------------------------------------------------------------


def test_extract_token_cookie_only():
    """Cookie presente → retorna token do cookie."""
    request = _make_request(cookie_token="cookie-jwt")
    assert _extract_token(request) == "cookie-jwt"


def test_extract_token_bearer_only():
    """Apenas Bearer → retorna token do header."""
    request = _make_request(bearer_token="bearer-jwt")
    assert _extract_token(request) == "bearer-jwt"


def test_extract_token_cookie_takes_priority():
    """Ambos presentes → cookie tem prioridade."""
    request = _make_request(cookie_token="cookie-jwt", bearer_token="bearer-jwt")
    assert _extract_token(request) == "cookie-jwt"


def test_extract_token_none():
    """Sem credenciais → retorna None."""
    request = _make_request()
    assert _extract_token(request) is None


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_accepts_cookie():
    """Request com cookie lanez_session=<jwt> retorna user."""
    user_id = uuid.uuid4()
    token = _make_jwt(user_id)
    request = _make_request(cookie_token=token)

    fake_user = _make_user(user_id)
    db = AsyncMock()
    db.get.return_value = fake_user

    result = await get_current_user(request=request, db=db)
    assert result == fake_user
    db.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_accepts_bearer():
    """Request com header Authorization: Bearer <jwt> retorna user."""
    user_id = uuid.uuid4()
    token = _make_jwt(user_id)
    request = _make_request(bearer_token=token)

    fake_user = _make_user(user_id)
    db = AsyncMock()
    db.get.return_value = fake_user

    result = await get_current_user(request=request, db=db)
    assert result == fake_user
    db.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_cookie_takes_priority():
    """Quando ambos cookie e Bearer presentes com tokens diferentes, cookie é usado."""
    cookie_user_id = uuid.uuid4()
    bearer_user_id = uuid.uuid4()
    cookie_token = _make_jwt(cookie_user_id)
    bearer_token = _make_jwt(bearer_user_id)
    request = _make_request(cookie_token=cookie_token, bearer_token=bearer_token)

    cookie_user = _make_user(cookie_user_id)
    db = AsyncMock()
    db.get.return_value = cookie_user

    result = await get_current_user(request=request, db=db)
    assert result == cookie_user
    # Verifica que o user_id do cookie foi usado (não o do Bearer)
    call_args = db.get.call_args
    from app.models.user import User
    assert call_args[0][0] is User
    assert str(call_args[0][1]) == str(cookie_user_id)


@pytest.mark.asyncio
async def test_get_current_user_no_token_returns_401():
    """Sem credenciais retorna 401."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, db=db)

    assert exc_info.value.status_code == 401
    assert "Não autenticado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_invalid_jwt_returns_401():
    """JWT inválido retorna 401."""
    request = _make_request(cookie_token="not-a-valid-jwt")
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, db=db)

    assert exc_info.value.status_code == 401
    assert "Não autenticado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_expired_jwt_returns_401():
    """JWT expirado retorna 401."""
    payload = {
        "user_id": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)
    request = _make_request(cookie_token=expired_token)
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, db=db)

    assert exc_info.value.status_code == 401
    assert "Não autenticado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_user_not_found_returns_401():
    """user_id válido no JWT mas não existe no banco retorna 401."""
    user_id = uuid.uuid4()
    token = _make_jwt(user_id)
    request = _make_request(cookie_token=token)

    db = AsyncMock()
    db.get.return_value = None  # User não encontrado

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, db=db)

    assert exc_info.value.status_code == 401
    assert "Usuário não encontrado" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Callback OAuth Dual — Tarefa 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_callback_with_return_url_sets_cookie_and_redirects():
    """Com return_url allowlisted, response é 302 com Set-Cookie: lanez_session."""
    import json
    from unittest.mock import patch

    from app.routers.auth import auth_callback

    user_id = uuid.uuid4()
    return_url = "http://localhost:5173/dashboard"

    # Redis retorna JSON com code_verifier + return_url
    redis = AsyncMock()
    redis.get.return_value = json.dumps({
        "code_verifier": "test-verifier",
        "return_url": return_url,
    })

    # Mock DB: execute retorna user existente
    fake_user = _make_user(user_id)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user
    db = AsyncMock()
    db.execute.return_value = mock_result

    background_tasks = MagicMock()

    # Mock httpx para token exchange e /me
    mock_token_response = MagicMock()
    mock_token_response.status_code = 200
    mock_token_response.json.return_value = {
        "access_token": "ms-access-token",
        "refresh_token": "ms-refresh-token",
        "expires_in": 3600,
    }

    mock_me_response = MagicMock()
    mock_me_response.status_code = 200
    mock_me_response.json.return_value = {
        "mail": "test@example.com",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_response
    mock_client.get.return_value = mock_me_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client):
        response = await auth_callback(
            background_tasks=background_tasks,
            code="auth-code",
            state="valid-state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    # Deve ser RedirectResponse 302
    assert response.status_code == 302
    assert response.headers.get("location") == return_url

    # Verificar Set-Cookie
    set_cookie = response.headers.get("set-cookie", "")
    assert "lanez_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()


@pytest.mark.asyncio
async def test_auth_callback_without_return_url_returns_json():
    """Sem return_url, comportamento JSON atual preservado (TokenResponse)."""
    import json
    from unittest.mock import patch

    from app.routers.auth import auth_callback

    user_id = uuid.uuid4()

    # Redis retorna JSON sem return_url
    redis = AsyncMock()
    redis.get.return_value = json.dumps({
        "code_verifier": "test-verifier",
        "return_url": None,
    })

    fake_user = _make_user(user_id)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user
    db = AsyncMock()
    db.execute.return_value = mock_result

    background_tasks = MagicMock()

    mock_token_response = MagicMock()
    mock_token_response.status_code = 200
    mock_token_response.json.return_value = {
        "access_token": "ms-access-token",
        "refresh_token": "ms-refresh-token",
        "expires_in": 3600,
    }

    mock_me_response = MagicMock()
    mock_me_response.status_code = 200
    mock_me_response.json.return_value = {
        "mail": "test@example.com",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_response
    mock_client.get.return_value = mock_me_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client):
        response = await auth_callback(
            background_tasks=background_tasks,
            code="auth-code",
            state="valid-state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    # Deve ser TokenResponse (não redirect)
    from app.schemas.auth import TokenResponse
    assert isinstance(response, TokenResponse)
    assert response.email == "test@example.com"
    assert response.token_type == "bearer"


@pytest.mark.asyncio
async def test_auth_microsoft_rejects_return_url_outside_allowlist():
    """return_url=https://evil.com retorna 400."""
    from app.routers.auth import auth_microsoft

    redis = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_microsoft(
            redis=redis,
            return_url="https://evil.com/steal",
        )

    assert exc_info.value.status_code == 400
    assert "return_url não permitido" in exc_info.value.detail
    # Redis não deve ser chamado quando return_url é rejeitado
    redis.set.assert_not_called()


# ---------------------------------------------------------------------------
# Endpoints de Sessão — Tarefa 3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_me_returns_user_info():
    """GET /auth/me autenticado via cookie retorna email, token_expires_at, etc."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user
    from app.main import app

    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.email = "me@example.com"
    fake_user.token_expires_at = now + timedelta(days=1)
    fake_user.last_sync_at = now
    fake_user.created_at = now - timedelta(days=30)

    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/auth/me")

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me@example.com"
        assert body["id"] == str(user_id)
        assert "token_expires_at" in body
        assert "last_sync_at" in body
        assert "created_at" in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_auth_logout_clears_cookie():
    """POST /auth/logout retorna 204 com Set-Cookie contendo Max-Age=0."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/logout")

    assert resp.status_code == 204

    # Verificar que Set-Cookie limpa o cookie lanez_session
    set_cookie = resp.headers.get("set-cookie", "")
    assert "lanez_session=" in set_cookie
    # delete_cookie define Max-Age=0 para expirar imediatamente
    assert 'max-age=0' in set_cookie.lower() or 'expires=' in set_cookie.lower()
    assert "path=/" in set_cookie.lower()
