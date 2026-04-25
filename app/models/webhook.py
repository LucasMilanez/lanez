"""Modelo WebhookSubscription — subscrições de webhook da Microsoft Graph.

Rastreia subscrições ativas de webhook para cada usuário, permitindo
renovação proativa e validação de notificações recebidas.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WebhookSubscription(Base):
    """Subscrição de webhook da Microsoft Graph API.

    Cada registro representa uma subscrição ativa para um recurso
    (calendar, mail, onenote, onedrive) de um usuário específico.
    O índice em expires_at permite consultas eficientes de subscrições
    próximas de expirar para renovação proativa.
    """

    __tablename__ = "webhook_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    resource: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    client_state: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
