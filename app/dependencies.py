"""Dependency de autenticação — aceita JWT via cookie HttpOnly OU Authorization Bearer."""

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

_COOKIE_NAME = "lanez_session"
_JWT_ALGORITHM = "HS256"


def _extract_token(request: Request) -> str | None:
    """Extrai JWT do cookie HttpOnly OU do header Authorization Bearer.

    Cookie tem prioridade (painel é o consumidor primário). Bearer é
    o fallback para MCP e ferramentas CLI.
    """
    cookie_token = request.cookies.get(_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Valida JWT (cookie ou Bearer) e retorna User. 401 se inválido/expirado."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request)
    if token is None:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
