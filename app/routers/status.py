"""Router de status — métricas agregadas para o painel. Fase 6a."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.embedding import Embedding
from app.models.memory import Memory
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.schemas.status import (
    RecentBriefing,
    ServiceCount,
    StatusConfig,
    StatusResponse,
    TokenUsageBucket,
    WebhookInfo,
)

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=StatusResponse)
async def get_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Retorna métricas agregadas do usuário para o dashboard."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Webhooks — WebhookSubscription tem `resource` (String), NÃO `service`
    webhook_stmt = select(WebhookSubscription).where(
        WebhookSubscription.user_id == user.id
    )
    webhooks = (await db.execute(webhook_stmt)).scalars().all()

    # Embeddings por serviço — Embedding.service é String(20), sem .value
    emb_stmt = (
        select(Embedding.service, func.count())
        .where(Embedding.user_id == user.id)
        .group_by(Embedding.service)
    )
    emb_rows = (await db.execute(emb_stmt)).all()
    embeddings_by_service = [
        ServiceCount(service=row[0], count=row[1])
        for row in emb_rows
    ]

    # Memórias — contagem total
    mem_count_stmt = (
        select(func.count())
        .select_from(Memory)
        .where(Memory.user_id == user.id)
    )
    memories_count = (await db.execute(mem_count_stmt)).scalar_one()

    # Briefings últimos 30 dias — contagem
    briefing_count_stmt = (
        select(func.count())
        .select_from(Briefing)
        .where(
            Briefing.user_id == user.id,
            Briefing.generated_at >= thirty_days_ago,
        )
    )
    briefings_count_30d = (await db.execute(briefing_count_stmt)).scalar_one()

    # Briefings recentes — 5 mais recentes por event_start
    recent_briefings_stmt = (
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .order_by(Briefing.event_start.desc())
        .limit(5)
    )
    recent_briefings = (await db.execute(recent_briefings_stmt)).scalars().all()

    # Tokens últimos 30 dias — somatório com coalesce para evitar NULL
    token_sum_stmt = select(
        func.coalesce(func.sum(Briefing.input_tokens), 0),
        func.coalesce(func.sum(Briefing.output_tokens), 0),
        func.coalesce(func.sum(Briefing.cache_read_tokens), 0),
        func.coalesce(func.sum(Briefing.cache_write_tokens), 0),
    ).where(
        Briefing.user_id == user.id,
        Briefing.generated_at >= thirty_days_ago,
    )
    in_t, out_t, cache_r, cache_w = (await db.execute(token_sum_stmt)).one()

    return StatusResponse(
        user_email=user.email,
        token_expires_at=user.token_expires_at,
        token_expires_in_seconds=int(
            (user.token_expires_at - now).total_seconds()
        ),
        last_sync_at=user.last_sync_at,
        webhook_subscriptions=[
            WebhookInfo(resource=w.resource, expires_at=w.expires_at)
            for w in webhooks
        ],
        embeddings_by_service=embeddings_by_service,
        memories_count=memories_count,
        briefings_count_30d=briefings_count_30d,
        recent_briefings=[
            RecentBriefing(
                event_id=b.event_id,
                event_subject=b.event_subject,
                event_start=b.event_start,
            )
            for b in recent_briefings
        ],
        tokens_30d=TokenUsageBucket(
            input=in_t,
            output=out_t,
            cache_read=cache_r,
            cache_write=cache_w,
        ),
        config=StatusConfig(
            briefing_history_window_days=settings.BRIEFING_HISTORY_WINDOW_DAYS,
        ),
    )
