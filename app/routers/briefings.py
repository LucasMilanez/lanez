"""Router REST para consulta de briefings automáticos de reunião.

Expõe endpoint protegido por JWT para recuperar o briefing gerado
para um evento específico do calendar do usuário.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from collections.abc import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_redis
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.briefing import (
    BriefingListItem,
    BriefingListResponse,
    BriefingResponse,
)
from app.services.briefing import generate_briefing
from app.services.graph import GraphService

router = APIRouter(prefix="/briefings", tags=["briefings"])


async def _get_graph_service() -> AsyncGenerator[GraphService, None]:
    service = GraphService()
    try:
        yield service
    finally:
        await service.close()


@router.get("", response_model=BriefingListResponse)
async def list_briefings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Busca em event_subject"),
) -> BriefingListResponse:
    """Lista briefings do usuário, paginados por event_start desc.

    Suporta filtro textual em event_subject (ILIKE %q%).
    """
    filters = [Briefing.user_id == user.id]
    if q:
        # Escape SQL LIKE wildcards in user input to prevent unintended matches
        escaped_q = q.replace("%", r"\%").replace("_", r"\_")
        filters.append(Briefing.event_subject.ilike(f"%{escaped_q}%"))

    count_stmt = select(func.count()).select_from(Briefing).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    paged_stmt = (
        select(Briefing)
        .where(*filters)
        .order_by(Briefing.event_start.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    briefings = (await db.execute(paged_stmt)).scalars().all()

    return BriefingListResponse(
        items=[
            BriefingListItem.model_validate(b, from_attributes=True)
            for b in briefings
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=BriefingResponse)
async def get_briefing_by_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BriefingResponse:
    """Retorna o briefing do usuário autenticado para o evento especificado.

    Consulta por (user_id, event_id) — coberto pelo unique constraint.
    Retorna 404 se não houver briefing para o par.
    """
    result = await db.execute(
        select(Briefing).where(
            Briefing.user_id == user.id,
            Briefing.event_id == event_id,
        )
    )
    briefing = result.scalar_one_or_none()

    if briefing is None:
        raise HTTPException(status_code=404, detail="Briefing não encontrado")

    return briefing


@router.post("/generate/{event_id}", response_model=BriefingResponse)
@limiter.limit("5/minute")
async def generate_briefing_on_demand(
    request: Request,
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph: GraphService = Depends(_get_graph_service),
) -> BriefingResponse:
    """Força a geração de um briefing agora, sem esperar o webhook do Graph.

    Útil para demonstrações (vídeo no LinkedIn, smoke tests após deploy) e
    para preencher retroativamente briefings de eventos que já passaram.

    Idempotente por (user_id, event_id) — chamar duas vezes para o mesmo
    evento retorna o briefing existente sem gastar tokens extra.

    Retorna 404 se o evento não existir no calendar do usuário.
    """
    return await generate_briefing(db, redis, graph, user, event_id)
