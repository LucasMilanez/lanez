"""Caso de Borda 8: Integridade referencial em GraphCache e WebhookSubscription.

Requisitos: R14 (14.3), R15 (15.3)

Verifica que inserir GraphCache ou WebhookSubscription com user_id inexistente
resulta em erro de integridade referencial (ForeignKey violation).

Usa SQLite in-memory com PRAGMA foreign_keys=ON e DDL manual para validar
FK constraints sem depender de PostgreSQL rodando. As tabelas são criadas
com SQL puro para evitar incompatibilidades de tipos (JSONB etc.).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# DDL manual — espelha as FK constraints dos modelos sem tipos PG-only
# ---------------------------------------------------------------------------

_CREATE_USERS = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    microsoft_access_token TEXT NOT NULL,
    microsoft_refresh_token TEXT NOT NULL,
    token_expires_at TEXT NOT NULL,
    created_at TEXT,
    last_sync_at TEXT
)
"""

_CREATE_GRAPH_CACHE = """
CREATE TABLE graph_cache (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    service TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    data TEXT NOT NULL,
    cached_at TEXT,
    expires_at TEXT NOT NULL,
    etag TEXT
)
"""

_CREATE_WEBHOOK_SUBSCRIPTIONS = """
CREATE TABLE webhook_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    subscription_id TEXT UNIQUE NOT NULL,
    resource TEXT NOT NULL,
    client_state TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT
)
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Cria engine SQLite in-memory com FK enforcement e tabelas via DDL manual."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_USERS))
        await conn.execute(text(_CREATE_GRAPH_CACHE))
        await conn.execute(text(_CREATE_WEBHOOK_SUBSCRIPTIONS))

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


# ---------------------------------------------------------------------------
# Testes de integridade referencial
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_cache_with_nonexistent_user_id_raises_integrity_error(db_session: AsyncSession):
    """Inserir GraphCache com user_id que não existe na tabela users
    deve levantar IntegrityError (FK violation).

    Valida Requisito R14 (14.3): WHEN um registro GraphCache é inserido
    com um user_id inexistente, THE Repositório_Dados SHALL rejeitar a
    operação com erro de integridade referencial.
    """
    fake_user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    stmt = text(
        "INSERT INTO graph_cache (id, user_id, service, resource_id, data, cached_at, expires_at) "
        "VALUES (:id, :user_id, :service, :resource_id, :data, :cached_at, :expires_at)"
    )

    with pytest.raises(IntegrityError):
        await db_session.execute(
            stmt,
            {
                "id": str(uuid.uuid4()),
                "user_id": fake_user_id,
                "service": "calendar",
                "resource_id": "test-resource",
                "data": '{"value": []}',
                "cached_at": now,
                "expires_at": expires,
            },
        )


@pytest.mark.asyncio
async def test_webhook_subscription_with_nonexistent_user_id_raises_integrity_error(db_session: AsyncSession):
    """Inserir WebhookSubscription com user_id que não existe na tabela users
    deve levantar IntegrityError (FK violation).

    Valida Requisito R15 (15.3): WHEN um registro WebhookSubscription é
    inserido com um user_id inexistente, THE Repositório_Dados SHALL
    rejeitar a operação com erro de integridade referencial.
    """
    fake_user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    stmt = text(
        "INSERT INTO webhook_subscriptions (id, user_id, subscription_id, resource, client_state, expires_at, created_at) "
        "VALUES (:id, :user_id, :subscription_id, :resource, :client_state, :expires_at, :created_at)"
    )

    with pytest.raises(IntegrityError):
        await db_session.execute(
            stmt,
            {
                "id": str(uuid.uuid4()),
                "user_id": fake_user_id,
                "subscription_id": f"sub-{uuid.uuid4()}",
                "resource": "/me/events",
                "client_state": "test-state",
                "expires_at": expires,
                "created_at": now,
            },
        )
