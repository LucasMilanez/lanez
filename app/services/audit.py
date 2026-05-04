"""Service helper para registrar eventos no audit log. Fase 7.

Helper único ``log_event`` que cria a entrada AuditLog e faz ``flush`` na
sessão recebida — segue regra M1 da Fase 4.5 (services não fazem commit).
O commit fica a cargo de quem dirige a sessão (get_db no caso de request,
ou o caller direto no caso de background tasks como ``_briefing_background``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditEventType(StrEnum):
    """Inventário fechado de tipos de evento. Não estender sem revisão de spec."""

    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_REFRESH = "auth.refresh"
    MCP_CALL = "mcp.call"
    BRIEFING_GENERATED = "briefing.generated"
    MEMORY_CREATED = "memory.created"
    VOICE_TRANSCRIBED = "voice.transcribed"
    WEBHOOK_RECEIVED = "webhook.received"


_MAX_ERROR_LENGTH = 500


async def log_event(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: AuditEventType,
    event_data: dict[str, Any] | None = None,
    success: bool = True,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Registra um evento no audit log. NÃO faz commit — o caller é responsável.

    Trunca ``error_message`` a 500 chars para encaixar na coluna. Falhas em
    ``flush`` são logadas mas NÃO levantadas — auditoria não pode quebrar a
    operação principal.
    """
    if error_message and len(error_message) > _MAX_ERROR_LENGTH:
        error_message = error_message[: _MAX_ERROR_LENGTH - 3] + "..."

    entry = AuditLog(
        user_id=user_id,
        event_type=str(event_type),
        event_data=event_data or {},
        success=success,
        error_message=error_message,
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)

    try:
        await db.flush()
    except Exception:
        # Audit não pode derrubar request — log e segue
        logger.exception(
            "Falha ao registrar evento de auditoria event_type=%s user_id=%s",
            event_type,
            user_id,
        )
