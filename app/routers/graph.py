"""Router para consulta de dados da Microsoft Graph API.

Expõe endpoints protegidos por JWT que delegam ao GraphService
a busca de eventos, mensagens, páginas do OneNote e arquivos do OneDrive.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_redis
from app.dependencies import get_current_user as _get_current_user
from app.schemas.graph import GraphDataResponse, ServiceType
from app.services.graph import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


async def get_graph_service() -> AsyncGenerator[GraphService, None]:
    """Dependency que fornece uma instância de GraphService e a fecha após uso."""
    service = GraphService()
    try:
        yield service
    finally:
        await service.close()


@router.get("/me/events", response_model=GraphDataResponse)
async def get_events(
    current_user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph_service: GraphService = Depends(get_graph_service),
) -> GraphDataResponse:
    """Retorna eventos do calendário do usuário autenticado."""
    return await graph_service.fetch_data(
        current_user.id, ServiceType.CALENDAR, db, redis
    )


@router.get("/me/messages", response_model=GraphDataResponse)
async def get_messages(
    current_user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph_service: GraphService = Depends(get_graph_service),
) -> GraphDataResponse:
    """Retorna mensagens de email do usuário autenticado."""
    return await graph_service.fetch_data(
        current_user.id, ServiceType.MAIL, db, redis
    )


@router.get("/me/onenote/pages", response_model=GraphDataResponse)
async def get_onenote_pages(
    current_user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph_service: GraphService = Depends(get_graph_service),
) -> GraphDataResponse:
    """Retorna páginas do OneNote do usuário autenticado."""
    return await graph_service.fetch_data(
        current_user.id, ServiceType.ONENOTE, db, redis
    )


@router.get("/me/drive/root/children", response_model=GraphDataResponse)
async def get_onedrive_files(
    current_user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph_service: GraphService = Depends(get_graph_service),
) -> GraphDataResponse:
    """Retorna arquivos do OneDrive do usuário autenticado."""
    return await graph_service.fetch_data(
        current_user.id, ServiceType.ONEDRIVE, db, redis
    )
