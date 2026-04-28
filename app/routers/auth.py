"""Router de autenticação OAuth 2.0 com Microsoft Entra ID.

Implementa o fluxo Authorization Code com PKCE (S256) conforme RFC 7636.
Suporta modo dual no callback: com return_url → cookie + redirect (painel);
sem return_url → JSON TokenResponse (MCP/curl).
"""

import hashlib
import json
import logging
import os
import secrets
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from jose import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db, get_redis
from app.models.user import User, encrypt_token
from app.schemas.auth import TokenResponse, UserMeResponse
from app.services.webhook import WebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "lanez_session"

# Escopos exigidos pela Fase 1
SCOPES = [
    "Calendars.Read",
    "Mail.Read",
    "Notes.Read",
    "Files.Read",
    "User.Read",
    "offline_access",
]

AUTHORIZE_URL = (
    f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
    "/oauth2/v2.0/authorize"
)

TOKEN_URL = (
    f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
    "/oauth2/v2.0/token"
)

GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_DAYS = 7
_HTTP_TIMEOUT = 30.0


def _is_allowed_return_url(url: str) -> bool:
    """Valida que return_url começa com uma origem listada em CORS_ORIGINS."""
    allowed = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    return any(url.startswith(origin) for origin in allowed)


def _generate_code_verifier() -> str:
    """Gera code_verifier de 32 bytes aleatórios em base64url sem padding."""
    return urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")


def _generate_code_challenge(code_verifier: str) -> str:
    """Calcula code_challenge = base64url(SHA256(code_verifier)) sem padding."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@router.get("/microsoft")
async def auth_microsoft(
    redis: Redis = Depends(get_redis),
    return_url: str | None = Query(default=None),
):
    """Inicia o fluxo OAuth 2.0 com PKCE redirecionando para o Entra ID.

    Se return_url fornecido, valida contra allowlist CORS_ORIGINS e armazena
    no Redis junto com code_verifier para uso no callback.
    """
    if return_url and not _is_allowed_return_url(return_url):
        raise HTTPException(status_code=400, detail="return_url não permitido")

    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_hex(16)

    # Armazenar code_verifier + return_url no Redis como JSON com TTL de 10 minutos
    state_data = json.dumps({
        "code_verifier": code_verifier,
        "return_url": return_url,
    })
    await redis.set(f"oauth:state:{state}", state_data, ex=600)

    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }

    authorization_url = f"{AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url=authorization_url, status_code=302)


def _create_jwt(user_id: str) -> str:
    """Emite JWT interno assinado com SECRET_KEY contendo user_id e exp."""
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)


async def _create_webhook_subscriptions_bg(
    user_id: str,
    access_token: str,
) -> None:
    """Background task: cria subscrições de webhook para o usuário."""
    webhook_service = WebhookService()
    try:
        async with AsyncSessionLocal() as db:
            await webhook_service.create_subscriptions(
                user_id=user_id,
                access_token=access_token,
                db=db,
            )
    except Exception:
        logger.exception(
            "Falha ao criar subscrições de webhook para user_id=%s [token=REDACTED]",
            user_id,
        )
    finally:
        await webhook_service.close()


@router.get("/callback", response_model=TokenResponse)
async def auth_callback(
    background_tasks: BackgroundTasks,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Callback OAuth 2.0 — troca código por tokens e emite JWT interno.

    Modo dual:
    - Com return_url no state → RedirectResponse 302 + Set-Cookie lanez_session
    - Sem return_url → TokenResponse JSON (legado, compatível com MCP/curl)
    """

    # 1. Verificar erro do Entra ID
    if error:
        detail = error_description or error
        logger.warning("Erro no callback OAuth: %s — %s", error, detail)
        raise HTTPException(status_code=400, detail=detail)

    # 2. Validar state contra Redis
    if not state:
        raise HTTPException(status_code=400, detail="Parâmetro state ausente")

    redis_key = f"oauth:state:{state}"
    raw = await redis.get(redis_key)
    if raw is None:
        raise HTTPException(status_code=400, detail="State inválido ou expirado")

    # Consumir o state (uso único)
    await redis.delete(redis_key)

    # Parsear state data — suporta JSON novo e string pura legada (transição)
    try:
        state_data = json.loads(raw)
        code_verifier = state_data["code_verifier"]
    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: Redis contém string pura (code_verifier) do formato antigo
        code_verifier = raw if isinstance(raw, str) else raw.decode("utf-8")
        state_data = {"code_verifier": code_verifier, "return_url": None}

    if not code:
        raise HTTPException(status_code=400, detail="Parâmetro code ausente")

    # 3. Trocar code por tokens
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        token_resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )

    if token_resp.status_code != 200:
        logger.error(
            "Falha na troca de código por tokens — status=%d [token=REDACTED]",
            token_resp.status_code,
        )
        raise HTTPException(status_code=400, detail="Falha ao obter tokens do Entra ID")

    token_data = token_resp.json()
    ms_access_token = token_data["access_token"]
    ms_refresh_token = token_data["refresh_token"]
    expires_in = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # 4. Buscar email via GET /me
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        me_resp = await client.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {ms_access_token}"},
        )

    if me_resp.status_code != 200:
        logger.error(
            "Falha ao buscar perfil do usuário — status=%d [token=REDACTED]",
            me_resp.status_code,
        )
        raise HTTPException(status_code=400, detail="Falha ao obter perfil do usuário")

    me_data = me_resp.json()
    email = me_data.get("mail") or me_data.get("userPrincipalName")
    if not email:
        raise HTTPException(status_code=400, detail="Email não encontrado no perfil do usuário")

    # 5. Criar ou atualizar User (upsert por email)
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            _microsoft_access_token=encrypt_token(ms_access_token),
            _microsoft_refresh_token=encrypt_token(ms_refresh_token),
            token_expires_at=token_expires_at,
        )
        db.add(user)
    else:
        user._microsoft_access_token = encrypt_token(ms_access_token)
        user._microsoft_refresh_token = encrypt_token(ms_refresh_token)
        user.token_expires_at = token_expires_at

    await db.commit()
    await db.refresh(user)

    # 6. Emitir JWT interno
    internal_jwt = _create_jwt(str(user.id))

    # 7. Disparar criação de subscrições webhook como background task
    background_tasks.add_task(
        _create_webhook_subscriptions_bg,
        str(user.id),
        ms_access_token,
    )

    logger.info(
        "Autenticação concluída: user_id=%s email=%s [token=REDACTED]",
        user.id,
        email,
    )

    # 8. Bifurcar resposta: com return_url → cookie + redirect; sem → JSON legado
    if state_data.get("return_url"):
        response = RedirectResponse(
            url=state_data["return_url"], status_code=302
        )
        response.set_cookie(
            key=_COOKIE_NAME,
            value=internal_jwt,
            max_age=7 * 24 * 60 * 60,  # 7 dias
            httponly=True,
            samesite="lax",
            secure=False,  # TODO Fase 6c (deploy): secure=True quando atrás de HTTPS
            path="/",
        )
        return response

    # Sem return_url: comportamento legado mantido
    return TokenResponse(
        access_token=internal_jwt,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        token_expires_at=token_expires_at,
    )


# ---------------------------------------------------------------------------
# Dependency centralizada importada de app/dependencies.py
# ---------------------------------------------------------------------------

from app.dependencies import get_current_user as _get_current_user


# ---------------------------------------------------------------------------
# GET /auth/me + POST /auth/logout — Fase 6a
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserMeResponse)
async def auth_me(
    current_user: User = Depends(_get_current_user),
) -> UserMeResponse:
    """Retorna dados básicos do usuário autenticado.

    Usado pelo painel para decidir se mostra /login ou /dashboard.
    """
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        token_expires_at=current_user.token_expires_at,
        last_sync_at=current_user.last_sync_at,
        created_at=current_user.created_at,
    )


@router.post("/logout", status_code=204)
async def auth_logout() -> Response:
    """Limpa o cookie de sessão. Idempotente — sempre retorna 204."""
    response = Response(status_code=204)
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return response


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=TokenResponse)
async def auth_refresh(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Renova tokens Microsoft usando o refresh_token armazenado.

    Fluxo:
    1. Obter user_id do JWT via dependency _get_current_user
    2. Descriptografar refresh_token do User
    3. POST token endpoint com grant_type=refresh_token
    4. Atualizar tokens criptografados e token_expires_at
    5. Emitir novo JWT interno
    6. Retornar 401 se falhar
    """

    # 1-2. Descriptografar refresh_token
    try:
        refresh_token = current_user.microsoft_refresh_token
    except Exception:
        logger.error(
            "Falha ao descriptografar refresh_token para user_id=%s [token=REDACTED]",
            current_user.id,
        )
        raise HTTPException(
            status_code=401,
            detail="Re-autenticação necessária",
        )

    # 3. POST token endpoint com grant_type=refresh_token
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        token_resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )

    if token_resp.status_code != 200:
        logger.warning(
            "Falha ao renovar tokens para user_id=%s — status=%d [token=REDACTED]",
            current_user.id,
            token_resp.status_code,
        )
        raise HTTPException(
            status_code=401,
            detail="Re-autenticação necessária",
        )

    token_data = token_resp.json()
    new_access_token = token_data["access_token"]
    new_refresh_token = token_data.get("refresh_token", refresh_token)
    expires_in = token_data.get("expires_in", 3600)
    new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # 4. Atualizar tokens criptografados e token_expires_at
    current_user._microsoft_access_token = encrypt_token(new_access_token)
    current_user._microsoft_refresh_token = encrypt_token(new_refresh_token)
    current_user.token_expires_at = new_expires_at

    await db.commit()
    await db.refresh(current_user)

    # 5. Emitir novo JWT interno
    new_jwt = _create_jwt(str(current_user.id))

    logger.info(
        "Tokens renovados: user_id=%s [token=REDACTED]",
        current_user.id,
    )

    # 6. Retornar TokenResponse
    return TokenResponse(
        access_token=new_jwt,
        token_type="bearer",
        user_id=current_user.id,
        email=current_user.email,
        token_expires_at=new_expires_at,
    )
