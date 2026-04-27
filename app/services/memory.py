"""Serviço de memória persistente — salvar e recuperar memórias via busca semântica.

Reutiliza ``generate_embedding`` de ``app.services.embeddings`` (mesmo singleton
all-MiniLM-L6-v2 da Fase 3). Cada ``save_memory`` é sempre INSERT (sem
deduplicação). ``recall_memory`` filtra por cosine_distance < 0.5 e atualiza
``last_accessed_at`` em batch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.embeddings import generate_embedding

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_RECALL_DISTANCE_THRESHOLD = 0.5
_RECALL_LIMIT_DEFAULT = 5
_RECALL_LIMIT_MAX = 20


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------


async def save_memory(
    db: AsyncSession,
    user_id: UUID,
    content: str,
    tags: list[str] | None = None,
) -> dict:
    """Persiste uma nova memória. Sempre INSERT — nunca update.

    Raises ``ValueError`` se *content* for vazio ou só whitespace.
    """
    if not content.strip():
        raise ValueError("content não pode ser vazio")

    clean_tags = [t.strip() for t in (tags or []) if t.strip()]
    vector = generate_embedding(content)
    now = datetime.now(timezone.utc)

    memory = Memory(
        user_id=user_id,
        content=content,
        tags=clean_tags,
        vector=vector,
        created_at=now,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)

    return {
        "id": str(memory.id),
        "content": memory.content,
        "tags": memory.tags,
        "created_at": memory.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# recall_memory
# ---------------------------------------------------------------------------


async def recall_memory(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    tags: list[str] | None = None,
    limit: int = _RECALL_LIMIT_DEFAULT,
) -> list[dict]:
    """Recupera memórias por busca semântica + filtro de tags (OR).

    Retorna lista vazia se *query* for vazia/whitespace (sem hit no banco).
    Descarta resultados com ``cosine_distance >= 0.5``. Atualiza
    ``last_accessed_at`` em batch para os IDs retornados.
    """
    if not query.strip():
        return []

    limit = min(max(limit, 1), _RECALL_LIMIT_MAX)
    query_vector = generate_embedding(query)

    distance_col = Memory.vector.cosine_distance(query_vector).label("distance")

    stmt = select(Memory, distance_col).where(Memory.user_id == user_id)

    if tags:
        clean_tags = [t.strip() for t in tags if t.strip()]
        if clean_tags:
            stmt = stmt.where(Memory.tags.overlap(clean_tags))

    stmt = stmt.order_by("distance").limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    filtered = [
        (row.Memory, row.distance)
        for row in rows
        if row.distance < _RECALL_DISTANCE_THRESHOLD
    ]

    if filtered:
        ids = [m.id for m, _ in filtered]
        now = datetime.now(timezone.utc)
        await db.execute(
            update(Memory).where(Memory.id.in_(ids)).values(last_accessed_at=now)
        )

    return [
        {
            "id": str(memory.id),
            "content": memory.content,
            "tags": memory.tags,
            "created_at": memory.created_at.isoformat(),
            "relevance_score": round(1 - distance, 4),
        }
        for memory, distance in filtered
    ]
