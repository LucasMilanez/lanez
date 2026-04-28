"""Property-based test para extração dual de token (Cookie + Bearer).

**Feature: lanez-fase6a-painel**
**Validates: Propriedade 1 — Extração dual de token, cookie tem prioridade**

Para qualquer par de tokens (cookie_token, bearer_token):
- Ambos presentes → retorna cookie_token
- Apenas cookie → retorna cookie_token
- Apenas Bearer → retorna bearer_token
- Nenhum → retorna None
"""

from __future__ import annotations

from unittest.mock import MagicMock

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text, booleans

from app.dependencies import _extract_token


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


# Estratégia: tokens não-vazios (min_size=1 garante que são truthy)
_token_strategy = text(min_size=1, max_size=50)


@given(cookie_token=_token_strategy, bearer_token=_token_strategy)
@hyp_settings(max_examples=100)
def test_property_extract_token_cookie_priority_both_present(
    cookie_token: str, bearer_token: str
) -> None:
    """Quando ambos cookie e Bearer presentes, cookie sempre ganha."""
    request = _make_request(cookie_token=cookie_token, bearer_token=bearer_token)
    result = _extract_token(request)
    assert result == cookie_token


@given(cookie_token=_token_strategy)
@hyp_settings(max_examples=100)
def test_property_extract_token_cookie_only(cookie_token: str) -> None:
    """Apenas cookie presente → retorna cookie."""
    request = _make_request(cookie_token=cookie_token)
    result = _extract_token(request)
    assert result == cookie_token


@given(bearer_token=_token_strategy)
@hyp_settings(max_examples=100)
def test_property_extract_token_bearer_only(bearer_token: str) -> None:
    """Apenas Bearer presente → retorna Bearer."""
    request = _make_request(bearer_token=bearer_token)
    result = _extract_token(request)
    assert result == bearer_token


def test_property_extract_token_none() -> None:
    """Sem credenciais → retorna None."""
    request = _make_request()
    result = _extract_token(request)
    assert result is None


# ---------------------------------------------------------------------------
# Propriedade 2: Validação de allowlist de return_url
# ---------------------------------------------------------------------------


@given(
    origin=text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=3,
        max_size=20,
    ),
    path=text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789/",
        min_size=1,
        max_size=30,
    ),
)
@hyp_settings(max_examples=100)
def test_property_is_allowed_return_url_accepts_matching(
    origin: str, path: str
) -> None:
    """URL que começa com uma origem da allowlist é aceita."""
    from unittest.mock import patch

    from app.routers.auth import _is_allowed_return_url

    full_origin = f"http://{origin}"
    url = f"{full_origin}/{path}"

    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.CORS_ORIGINS = full_origin
        assert _is_allowed_return_url(url) is True


@given(
    origin=text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=3,
        max_size=15,
    ),
)
@hyp_settings(max_examples=100)
def test_property_is_allowed_return_url_rejects_non_matching(origin: str) -> None:
    """URL que não começa com nenhuma origem da allowlist é rejeitada."""
    from unittest.mock import patch

    from app.routers.auth import _is_allowed_return_url

    allowed = f"http://{origin}.allowed.com"
    url = f"https://evil.{origin}.com/steal"

    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.CORS_ORIGINS = allowed
        # URL evil nunca começa com a origem allowed (different scheme + domain)
        assert _is_allowed_return_url(url) is False
