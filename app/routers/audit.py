"""Router de audit log — listagem paginada com filtros. Fase 7."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogItem, AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_log(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event_type: list[str] | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(default=None),
) -> AuditLogListResponse:
    """Lista eventos de auditoria do usuário com filtros e paginação."""
    # Base filter — sempre isolado por user
    filters = [AuditLog.user_id == user.id]

    if event_type:
        filters.append(AuditLog.event_type.in_(event_type))

    if since:
        filters.append(AuditLog.created_at >= since)

    if until:
        filters.append(AuditLog.created_at <= until)

    if q:
        escaped_q = q.replace("%", r"\%").replace("_", r"\_")
        filters.append(
            AuditLog.event_type.ilike(f"%{escaped_q}%")
            | func.cast(AuditLog.event_data, String).ilike(f"%{escaped_q}%")
        )

    # Count total (mesmos filtros, sem offset/limit)
    count_stmt = select(func.count()).select_from(AuditLog).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    # Paged query
    paged_stmt = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(paged_stmt)).scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
