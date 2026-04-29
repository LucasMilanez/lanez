"""Router REST para criação de memórias via painel — Fase 6b.

Reaproveita app.services.memory.save_memory (função standalone).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryCreateRequest, MemoryResponse
from app.services.memory import save_memory

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Cria nova memória. Gera embedding internamente via save_memory."""
    result = await save_memory(
        db=db,
        user_id=user.id,
        content=body.content,
        tags=body.tags,
    )
    return MemoryResponse(
        id=result["id"],
        content=result["content"],
        tags=result["tags"],
        created_at=result["created_at"],
    )
