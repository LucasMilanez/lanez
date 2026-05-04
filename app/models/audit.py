"""Modelo AuditLog — registro persistente de eventos significativos. Fase 7."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """Evento auditado — auth, MCP call, briefing, memory, voice, webhook.

    ``event_type`` é um discriminador String (não enum Postgres) — o app
    valida via ``AuditEventType`` em audit.py. ``event_data`` é JSONB livre
    com schema definido pelo tipo (sem versionamento — queries devem ser
    tolerantes a campos ausentes).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_audit_log_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_audit_log_user_type_created",
            "user_id",
            "event_type",
            "created_at",
        ),
    )
