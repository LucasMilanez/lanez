"""Orquestrador de geração de briefing automático de reunião.

Coordena: verificação de idempotência → busca de evento → coleta de contexto
multi-fonte → chamada ao Claude Haiku 4.5 → persistência. Usa flush/refresh
sem commit (regra M1 da Fase 4.5 — commit é responsabilidade do boundary).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.config import settings
from app.models.briefing import Briefing
from app.models.user import User
from app.services.anthropic_client import generate_briefing_text
from app.services.briefing_context import collect_briefing_context
from app.services.graph import GraphService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você é um assistente executivo especializado em preparar briefings para reuniões de trabalho.

Seu objetivo é gerar um briefing estruturado em Markdown que ajude o usuário a se preparar \
para a reunião de forma eficiente.

## Regras

1. Responda SEMPRE em português brasileiro (pt-BR).
2. Use formato Markdown com seções claras e hierarquia de títulos.
3. Seja objetivo e direto — o usuário vai ler isso minutos antes da reunião.
4. Estruture o briefing nas seguintes seções:
   - **Resumo da Reunião**: 2-3 frases sobre o que é a reunião, baseado no assunto e contexto.
   - **Participantes**: Liste os participantes com qualquer contexto relevante encontrado nas memórias.
   - **Contexto Relevante**: Sintetize informações dos emails, documentos e memórias que sejam \
pertinentes à pauta.
   - **Pontos de Atenção**: Destaque itens que merecem atenção especial (prazos, decisões \
pendentes, conflitos).
   - **Sugestões de Preparação**: 2-3 ações concretas que o usuário pode fazer antes da reunião.
5. Se alguma seção não tiver informação suficiente, escreva "(sem informação disponível)" \
em vez de inventar conteúdo.
6. NÃO invente informações — use apenas o que foi fornecido no contexto.
7. Limite o briefing a no máximo 800 palavras.
"""


def _render_user_content(event_data: dict, context: dict) -> str:
    """Renderiza o user_content em Markdown para envio ao LLM.

    Formato segue a especificação do design doc seção 7.
    """
    subject = event_data.get("subject", "(sem assunto)")
    start = event_data.get("start", {}).get("dateTime", "")
    end = event_data.get("end", {}).get("dateTime", "")
    location = event_data.get("location", {})
    location_name = location.get("displayName", "") if isinstance(location, dict) else str(location) if location else ""
    body_preview = event_data.get("bodyPreview", "")

    # Participantes
    attendees = [
        a["emailAddress"]["address"]
        for a in event_data.get("attendees", [])
        if "emailAddress" in a and "address" in a["emailAddress"]
    ]

    lines = [
        "# Reunião",
        "",
        f"**Assunto:** {subject}",
        f"**Quando:** {start} - {end}",
        f'**Local:** {location_name or "(não especificado)"}',
        f'**Resumo:** {body_preview or "(sem resumo)"}',
        "",
        "# Participantes",
        "",
    ]
    for email in attendees:
        lines.append(f"- {email}")

    lines.append("")
    lines.append("# Contexto coletado")
    lines.append("")

    # Emails
    lines.append("## Emails recentes com participantes (últimos 90 dias)")
    lines.append("")
    emails = context.get("emails_with_attendees", [])
    if emails:
        for em in emails:
            date_str = em.get("receivedDateTime", "")[:10]
            em_subject = em.get("subject", "(sem assunto)")
            preview = em.get("bodyPreview", "")
            lines.append(f"**[{date_str}] {em_subject}**")
            lines.append(preview)
            lines.append("")
    else:
        lines.append("(nenhum email encontrado)")
        lines.append("")

    # OneNote
    lines.append("## Páginas OneNote relacionadas")
    lines.append("")
    onenote = context.get("onenote_pages", [])
    if onenote:
        for page in onenote:
            title = page.get("resource_id", "(sem título)")
            lines.append(f"- {title}")
    else:
        lines.append("(nenhuma página encontrada)")
    lines.append("")

    # OneDrive
    lines.append("## Arquivos OneDrive relacionados")
    lines.append("")
    onedrive = context.get("onedrive_files", [])
    if onedrive:
        for f in onedrive:
            name = f.get("resource_id", "(sem nome)")
            lines.append(f"- {name}")
    else:
        lines.append("(nenhum arquivo encontrado)")
    lines.append("")

    # Memórias
    lines.append("## Memórias relevantes")
    lines.append("")
    memories = context.get("memories", [])
    if memories:
        for mem in memories:
            content = mem.get("content", "")[:200]
            lines.append(f"- {content}")
    else:
        lines.append("(nenhuma memória encontrada)")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Gere o briefing seguindo as regras do system prompt.")

    return "\n".join(lines)


async def generate_briefing(
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    user: User,
    event_id: str,
) -> Briefing:
    """Orquestra coleta de contexto, chamada ao LLM e persistência do briefing.

    Idempotente: se já existe Briefing para (user_id, event_id), retorna o
    existente sem chamar a Anthropic API.

    Fluxo:
    1. Verifica existência (idempotência)
    2. Busca evento via Graph API (pré-condição obrigatória)
    3. Coleta contexto multi-fonte (degradação graciosa)
    4. Renderiza user_content em Markdown
    5. Chama generate_briefing_text (Claude Haiku 4.5)
    6. Persiste Briefing com flush/refresh (sem commit — regra M1)
    7. Retorna Briefing

    Raises:
        HTTPException(404): Se o evento não for encontrado na Graph API.
    """
    # 1. Verificar existência — idempotência
    stmt = select(Briefing).where(
        Briefing.user_id == user.id,
        Briefing.event_id == event_id,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # 2. Buscar evento via Graph API — pré-condição obrigatória
    params = {
        "$select": "subject,start,end,location,bodyPreview,attendees",
    }
    try:
        event_data = await graph.fetch_with_params(
            user, f"/me/events/{event_id}", params, db, redis
        )
    except HTTPException:
        raise
    except Exception:
        logger.warning(
            "Falha ao buscar evento %s para user_id=%s",
            event_id,
            user.id,
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    if not event_data:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    # 3. Coletar contexto multi-fonte
    context = await collect_briefing_context(
        db, redis, graph, user, event_data, settings.BRIEFING_HISTORY_WINDOW_DAYS
    )

    # 4. Renderizar user_content
    user_content = _render_user_content(event_data, context)

    # 5. Chamar LLM
    llm_result = await generate_briefing_text(SYSTEM_PROMPT, user_content)

    # 6. Extrair dados do evento para persistência
    attendees_list = [
        a["emailAddress"]["address"]
        for a in event_data.get("attendees", [])
        if "emailAddress" in a and "address" in a["emailAddress"]
    ]
    event_start = datetime.fromisoformat(event_data["start"]["dateTime"])
    event_end = datetime.fromisoformat(event_data["end"]["dateTime"])

    # Garantir timezone-aware
    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    if event_end.tzinfo is None:
        event_end = event_end.replace(tzinfo=timezone.utc)

    briefing = Briefing(
        user_id=user.id,
        event_id=event_id,
        event_subject=event_data.get("subject", ""),
        event_start=event_start,
        event_end=event_end,
        attendees=attendees_list,
        content=llm_result.content,
        model_used=llm_result.model,
        input_tokens=llm_result.input_tokens,
        cache_read_tokens=llm_result.cache_read_tokens,
        cache_write_tokens=llm_result.cache_write_tokens,
        output_tokens=llm_result.output_tokens,
        generated_at=datetime.now(timezone.utc),
    )

    # 7. Persistir — flush/refresh sem commit (regra M1)
    db.add(briefing)
    await db.flush()
    await db.refresh(briefing)

    return briefing
