"""Testes do allowlist ALLOWED_EMAILS no callback OAuth.

Defesa em profundidade contra misconfiguration no Azure (multi-tenant,
common endpoint). Quando ALLOWED_EMAILS está configurado, só emails na
lista conseguem concluir o callback.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException


def _build_mocks(email_from_graph: str):
    """Retorna (redis, db, mock_httpx_client, background_tasks) configurados."""
    redis = AsyncMock()
    redis.get.return_value = json.dumps({
        "code_verifier": "test-verifier",
        "return_url": None,
    })
    redis.delete = AsyncMock()

    db = AsyncMock()
    # db.execute retorna algo cujo scalar_one_or_none() devolve None (user novo)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    # db.add é síncrono — AsyncMock por default faz awaitable. Forçamos sync
    # e populamos user.id já que em teste não há flush real do SQLAlchemy.
    def _add(user):
        user.id = uuid4()
    db.add = MagicMock(side_effect=_add)

    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json = MagicMock(return_value={
        "access_token": "ms-access",
        "refresh_token": "ms-refresh",
        "expires_in": 3600,
    })

    me_resp = MagicMock()
    me_resp.status_code = 200
    me_resp.json = MagicMock(return_value={"mail": email_from_graph})

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=me_resp)

    return redis, db, mock_client, BackgroundTasks()


@pytest.mark.asyncio
async def test_callback_rejects_email_not_in_allowlist(monkeypatch):
    """Com ALLOWED_EMAILS setado, email fora da lista → 403."""
    from app.routers import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "owner@example.com")

    redis, db, mock_client, bg = _build_mocks("someone.else@outlook.com")

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            await auth_module.auth_callback(
                background_tasks=bg,
                code="code",
                state="state",
                error=None,
                error_description=None,
                redis=redis,
                db=db,
            )

    assert exc.value.status_code == 403
    # Não deve ter persistido nada — db.commit nunca é chamado
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_callback_allows_email_in_allowlist(monkeypatch):
    """Com ALLOWED_EMAILS setado, email na lista → prossegue normalmente."""
    from app.routers import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "owner@example.com,admin@example.com")

    redis, db, mock_client, bg = _build_mocks("admin@example.com")

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client), \
         patch("app.routers.auth.log_event", new=AsyncMock()):
        # Não deve lançar
        await auth_module.auth_callback(
            background_tasks=bg,
            code="code",
            state="state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    db.commit.assert_called()


@pytest.mark.asyncio
async def test_callback_is_case_insensitive(monkeypatch):
    """Comparação do allowlist ignora case."""
    from app.routers import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "Owner@Example.COM")

    redis, db, mock_client, bg = _build_mocks("OWNER@example.com")

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client), \
         patch("app.routers.auth.log_event", new=AsyncMock()):
        await auth_module.auth_callback(
            background_tasks=bg,
            code="code",
            state="state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    db.commit.assert_called()


@pytest.mark.asyncio
async def test_callback_empty_allowlist_allows_any_email(monkeypatch):
    """Allowlist vazio = sem restrição (comportamento de dev)."""
    from app.routers import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "")

    redis, db, mock_client, bg = _build_mocks("anybody@example.com")

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client), \
         patch("app.routers.auth.log_event", new=AsyncMock()):
        await auth_module.auth_callback(
            background_tasks=bg,
            code="code",
            state="state",
            error=None,
            error_description=None,
            redis=redis,
            db=db,
        )

    db.commit.assert_called()


def test_is_email_allowed_unit(monkeypatch):
    """Unit test direto da função _is_email_allowed."""
    from app.routers import auth as auth_module

    # Vazio: sempre permite
    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "")
    assert auth_module._is_email_allowed("anything@any.com") is True

    # Whitespace: tratado como vazio
    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "   ")
    assert auth_module._is_email_allowed("anything@any.com") is True

    # Configurado: só aceita emails da lista
    monkeypatch.setattr(auth_module.settings, "ALLOWED_EMAILS", "a@x.com, b@y.com")
    assert auth_module._is_email_allowed("a@x.com") is True
    assert auth_module._is_email_allowed("B@Y.COM") is True
    assert auth_module._is_email_allowed("c@z.com") is False
    assert auth_module._is_email_allowed(" a@x.com ") is True  # strip
