"""Módulo de banco de dados e conexão Redis.

Gerencia o engine assíncrono do SQLAlchemy (asyncpg), a factory de sessões
e a conexão Redis via redis.asyncio.
"""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ---------------------------------------------------------------------------
# SQLAlchemy async engine + session factory
# ---------------------------------------------------------------------------

engine = create_async_engine(settings.DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Base declarativa para os modelos
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency injection — sessão do banco
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency que fornece uma sessão assíncrona do banco."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """Inicializa e retorna a conexão Redis."""
    global redis_client  # noqa: PLW0603
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    return redis_client


async def close_redis() -> None:
    """Fecha a conexão Redis."""
    global redis_client  # noqa: PLW0603
    if redis_client is not None:
        await redis_client.close()
        redis_client = None


def get_redis() -> aioredis.Redis:
    """Retorna a instância Redis ativa. Levanta erro se não inicializada."""
    if redis_client is None:
        raise RuntimeError("Redis não inicializado. Chame init_redis() primeiro.")
    return redis_client
