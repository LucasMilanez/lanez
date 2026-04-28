"""Coleta de contexto multi-fonte para briefing de reunião.

Recebe o evento já resolvido (dict) e coleta 4 fontes complementares
com degradação graciosa: emails com attendees, OneNote, OneDrive, memórias.
Se qualquer fonte falhar, loga warning e retorna lista vazia para essa fonte.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.models.user import User
from app.services.embeddings import semantic_search
from app.services.graph import GraphService
from app.services.memory import recall_memory

logger = logging.getLogger(__name__)


def filter_emails_by_attendees(
    emails: list[dict],
    attendees: set[str],
) -> list[dict]:
    """Filtra emails mantendo apenas os que têm pelo menos 1 attendee em from ou to.

    Função pura extraída para facilitar testes (incluindo property-based).
    """
    result = []
    for email in emails:
        from_addr = (
            email.get("from", {}).get("emailAddress", {}).get("address", "")
        )
        to_addrs = [
            r.get("emailAddress", {}).get("address", "")
            for r in email.get("toRecipients", [])
        ]

        if from_addr in attendees or any(a in attendees for a in to_addrs):
            result.append(email)

    return result


async def collect_briefing_context(
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    user: User,
    event_data: dict,
    history_window_days: int,
) -> dict:
    """Coleta contexto de 4 fontes complementares para compor o briefing.

    Recebe evento já resolvido — NÃO busca o evento.
    Cada fonte tem try/except individual: se falhar, loga warning e
    retorna lista vazia para essa fonte (degradação graciosa).

    Returns:
        dict com chaves: event, emails_with_attendees, onenote_pages,
        onedrive_files, memories.
    """
    # Extrair attendees e subject do evento
    attendees_list = [
        a["emailAddress"]["address"]
        for a in event_data.get("attendees", [])
        if "emailAddress" in a and "address" in a["emailAddress"]
    ]
    attendees_set = set(attendees_list)
    subject = event_data.get("subject", "")

    # --- Fonte 1: Emails com attendees ---
    emails_with_attendees: list[dict] = []
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=history_window_days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "$top": "10",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime ge {cutoff_iso}",
        }
        resp = await graph.fetch_with_params(
            user, "/me/messages", params, db, redis
        )
        all_emails = resp.get("value", [])
        emails_with_attendees = filter_emails_by_attendees(all_emails, attendees_set)
    except Exception:
        logger.warning(
            "Falha ao coletar emails para briefing user_id=%s", user.id, exc_info=True
        )

    # --- Fonte 2: OneNote pages ---
    onenote_pages: list[dict] = []
    try:
        onenote_pages = await semantic_search(
            db, user.id, query=subject, limit=5, services=["onenote"]
        )
    except Exception:
        logger.warning(
            "Falha ao coletar OneNote para briefing user_id=%s", user.id, exc_info=True
        )

    # --- Fonte 3: OneDrive files ---
    onedrive_files: list[dict] = []
    try:
        onedrive_files = await semantic_search(
            db, user.id, query=subject, limit=5, services=["onedrive"]
        )
    except Exception:
        logger.warning(
            "Falha ao coletar OneDrive para briefing user_id=%s", user.id, exc_info=True
        )

    # --- Fonte 4: Memories ---
    memories: list[dict] = []
    try:
        query_str = f"{subject} {' '.join(attendees_list)}"
        memories = await recall_memory(
            db, user.id, query=query_str, limit=5
        )
    except Exception:
        logger.warning(
            "Falha ao coletar memórias para briefing user_id=%s", user.id, exc_info=True
        )

    return {
        "event": event_data,
        "emails_with_attendees": emails_with_attendees,
        "onenote_pages": onenote_pages,
        "onedrive_files": onedrive_files,
        "memories": memories,
    }
