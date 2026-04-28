"""Router REST para consulta de briefings automáticos de reunião.

Expõe endpoint protegido por JWT para recuperar o briefing gerado
para um evento específico do calendar do usuário.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.user import User
from app.schemas.briefing import BriefingResponse

router = APIRouter(prefix="/briefings", tags=["briefings"])


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
