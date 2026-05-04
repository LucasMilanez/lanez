"""Schemas Pydantic para o endpoint GET /audit — Fase 7."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogItem(BaseModel):
    """Item individual do audit log."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    event_data: dict[str, Any]
    success: bool
    error_message: str | None
    latency_ms: int | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Resposta paginada do endpoint GET /audit."""

    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
