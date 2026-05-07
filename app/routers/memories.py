"""Router REST para CRUD de memórias via painel."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import MemoryCreateRequest, MemoryResponse
from app.services.embeddings import generate_embedding
from app.services.memory import save_memory

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=10_000)
    tags: list[str] | None = None

    @field_validator("content")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("content não pode ser apenas whitespace")
            return stripped
        return v


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryResponse]:
    """Lista todas as memórias do utilizador, ordenadas por data de criação desc."""
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user.id)
        .order_by(Memory.created_at.desc())
    )
    memories = result.scalars().all()
    return [
        MemoryResponse(
            id=m.id,
            content=m.content,
            tags=m.tags,
            created_at=m.created_at,
        )
        for m in memories
    ]


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
        source="rest",
    )
    return MemoryResponse(
        id=result["id"],
        content=result["content"],
        tags=result["tags"],
        created_at=result["created_at"],
    )


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Actualiza conteúdo e/ou tags. Regenera embedding se content mudar."""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="Memória não encontrada")

    if body.content is not None and body.content != memory.content:
        memory.content = body.content
        memory.vector = generate_embedding(body.content)
    if body.tags is not None:
        memory.tags = [t.strip() for t in body.tags if t.strip()]

    await db.commit()
    await db.refresh(memory)
    return MemoryResponse(
        id=memory.id,
        content=memory.content,
        tags=memory.tags,
        created_at=memory.created_at,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove uma memória."""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="Memória não encontrada")

    await db.delete(memory)
    await db.commit()
