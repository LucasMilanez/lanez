"""Modelo Briefing para briefings automáticos de reunião.

Armazena briefings gerados pelo Claude Haiku 4.5 a partir de contexto
multi-fonte (evento, emails, OneNote, OneDrive, memórias). Cada briefing
é único por (user_id, event_id) — UniqueConstraint garante idempotência
a nível de banco mesmo sob race conditions de webhooks duplicados.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Briefing(Base):
    """Briefing automático gerado para um evento de calendar.

    Contém o conteúdo Markdown gerado pelo LLM, metadados do evento
    original, e telemetria de tokens para monitoramento de custos.
    """

    __tablename__ = "briefings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    event_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attendees: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    cache_read_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_briefing_user_event"),
        Index("ix_briefings_user_event_start", "user_id", "event_start"),
    )
