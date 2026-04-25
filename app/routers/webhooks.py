from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_redis
from app.models.webhook import WebhookSubscription
from app.dependencies import get_current_user as _get_current_user
from app.schemas.graph import WebhookNotification, WebhookSubscriptionResponse
from app.services.cache import CacheService
from app.services.webhook import WebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

async def get_webhook_service() -> AsyncGenerator[WebhookService, None]:
    service = WebhookService()
    try:
        yield service
    finally:
        await service.close()

def get_cache_service(redis: aioredis.Redis = Depends(get_redis)) -> CacheService:
    return CacheService(redis)


@router.post("/graph")
async def receive_graph_notification(
    request: Request,
    validation_token: str | None = Query(None, alias="validationToken"),
    webhook_service: WebhookService = Depends(get_webhook_service),
    cache_service: CacheService = Depends(get_cache_service),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if validation_token is not None:
        return PlainTextResponse(validation_token, status_code=200)

    body: dict[str, Any] = await request.json()
    for item in body.get("value", []):
        notification = WebhookNotification(
            subscription_id=item.get("subscriptionId", ""),
            client_state=item.get("clientState", ""),
            resource=item.get("resource", ""),
            change_type=item.get("changeType", ""),
        )
        try:
            await webhook_service.process_notification(notification, cache_service, db)
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "Erro ao processar notificações subscription_id=%s",
                notification.subscription_id,
            )

    return Response(status_code=202)


@router.get("/subscriptions", response_model=list[WebhookSubscriptionResponse])
async def list_subscriptions(
    current_user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookSubscriptionResponse]:
    """Retorna subscrições ativas (não expiradas) do usuário autenticado."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(WebhookSubscription)
        .where(
            WebhookSubscription.user_id == current_user.id,
            WebhookSubscription.expires_at > now,
        )
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        WebhookSubscriptionResponse(
            id=row.id,
            subscription_id=row.subscription_id,
            resource=row.resource,
            expires_at=row.expires_at,
        )
        for row in rows
    ]
