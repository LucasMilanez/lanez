"""Modelo GraphCache — cache persistente de dados da Microsoft Graph API.

Armazena respostas da Graph API em JSONB com metadados de expiração e ETag
para cache condicional. Índice composto unique em (user_id, service, resource_id)
garante isolamento entre usuários e serviços.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GraphCache(Base):
    """Cache persistente de dados da Microsoft Graph API.

    Cada registro representa uma resposta cacheada de um serviço Graph
    (calendar, mail, onenote, onedrive) para um usuário específico.
    O índice composto unique em (user_id, service, resource_id) permite
    upsert eficiente e garante que não haja duplicatas.
    """

    __tablename__ = "graph_cache"

    __table_args__ = (
        Index(
            "ix_graph_cache_user_service_resource",
            "user_id",
            "service",
            "resource_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    service: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    data: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    etag: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
