from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db, get_redis
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.dependencies import get_current_user as _get_current_user
from app.schemas.graph import ServiceType, WebhookNotification, WebhookSubscriptionResponse
from app.services.briefing import generate_briefing
from app.services.cache import CacheService
from app.services.embeddings import ingest_graph_data
from app.services.graph import GraphService
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


async def _reingest_background(user_id: uuid.UUID, service_type: ServiceType) -> None:
    """Background task: busca dados frescos via GraphService e regenera embeddings.

    Cria sessão própria (não compartilha a do request), loga erros sem propagar.
    """
    graph_svc = GraphService()
    try:
        async with AsyncSessionLocal() as db:
            redis = get_redis()
            response = await graph_svc.fetch_data(user_id, service_type, db, redis)
            data = response.data
            items = data.get("value", []) if isinstance(data, dict) else []

            for item in items:
                resource_id = item.get("id", "")
                if resource_id:
                    await ingest_graph_data(db, user_id, service_type.value, resource_id, item)
            await db.commit()
    except Exception:
        logger.exception(
            "Erro no re-embedding user_id=%s service=%s [token=REDACTED]",
            user_id,
            service_type.value,
        )
    finally:
        await graph_svc.close()


async def _briefing_background(user_id: uuid.UUID, event_id: str) -> None:
    """Background task: gera briefing para evento de calendar.

    Cria sessão própria via AsyncSessionLocal() — fora do get_db dependency.
    Faz commit manual ao final — ÚNICA EXCEÇÃO justificada à regra M1 (Fase 4.5),
    pois a sessão não passa pelo get_db que faz commit/rollback no boundary.
    """
    graph_svc = GraphService()
    try:
        async with AsyncSessionLocal() as db:
            redis = get_redis()
            user = await db.get(User, user_id)
            if user is None:
                logger.warning(
                    "Usuário não encontrado para briefing: user_id=%s event_id=%s",
                    user_id,
                    event_id,
                )
                return
            await generate_briefing(db, redis, graph_svc, user, event_id)
            # Commit manual — exceção justificada à regra M1:
            # sessão criada via AsyncSessionLocal(), fora do get_db dependency
            await db.commit()
    except Exception:
        logger.exception(
            "Erro ao gerar briefing user_id=%s event_id=%s [token=REDACTED]",
            user_id,
            event_id,
        )
    finally:
        await graph_svc.close()


@router.post("/graph")
async def receive_graph_notification(
    request: Request,
    background_tasks: BackgroundTasks,
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
            result = await webhook_service.process_notification(notification, cache_service, db)
            if result is not None:
                user_id, service_type, event_id = result
                background_tasks.add_task(_reingest_background, user_id, service_type)
                if event_id is not None and service_type == ServiceType.CALENDAR:
                    background_tasks.add_task(_briefing_background, user_id, event_id)
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
