"""Serviço de embeddings — singleton do modelo, geração de vetores, extração, chunking, ingestão e busca."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import Embedding

# ---------------------------------------------------------------------------
# Singleton do modelo all-MiniLM-L6-v2
# ---------------------------------------------------------------------------

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Carrega o modelo uma vez (lazy singleton). ~2s, ~300MB."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def generate_embedding(text: str) -> list[float]:
    """Gera vetor de 384 dimensões para o texto."""
    return get_model().encode(text).tolist()


# ---------------------------------------------------------------------------
# Extração de texto por serviço
# ---------------------------------------------------------------------------


def extract_text(service: str, data: dict) -> str:
    """Extrai texto relevante de um item Graph API por tipo de serviço.

    Concatena campos com " | " usando filter(None, parts).
    Retorna string vazia para serviço desconhecido.
    Nunca levanta exceção — campos ausentes são ignorados.
    """
    try:
        if service == "calendar":
            parts: list[str] = [data.get("subject", "")]
            body_content = data.get("body", {}).get("content", "")
            if body_content:
                parts.append(body_content[:500])
            attendees = data.get("attendees", [])
            if attendees:
                names = [
                    a.get("emailAddress", {}).get("name", "")
                    for a in attendees
                ]
                filtered = list(filter(None, names))
                if filtered:
                    parts.append("Participantes: " + ", ".join(filtered))
            return " | ".join(filter(None, parts))

        if service == "mail":
            return " | ".join(filter(None, [
                data.get("subject", ""),
                data.get("from", {}).get("emailAddress", {}).get("name", ""),
                data.get("bodyPreview", ""),
            ]))

        if service == "onenote":
            return " | ".join(filter(None, [
                data.get("title", ""),
                data.get("contentUrl", ""),
            ]))

        if service == "onedrive":
            return " | ".join(filter(None, [
                data.get("name", ""),
                data.get("description", ""),
            ]))

        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Chunking por parágrafo
# ---------------------------------------------------------------------------


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Divide texto por parágrafo, respeitando limite de caracteres.

    - Divide por ``\\n\\n`` e agrupa parágrafos em chunks ≤ *max_chars*.
    - Preserva parágrafos inteiros (nunca corta uma frase no meio).
    - Se o texto não contém parágrafos, retorna ``[text[:max_chars]]``.
    - Sempre retorna pelo menos 1 chunk.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return [text[:max_chars]]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        plen = len(paragraph)
        if current_len + plen > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk, current_len = [paragraph], plen
        else:
            current_chunk.append(paragraph)
            current_len += plen

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks or [text[:max_chars]]


# ---------------------------------------------------------------------------
# Ingestão com deduplicação
# ---------------------------------------------------------------------------


async def ingest_item(
    db: AsyncSession,
    user_id: UUID,
    service: str,
    resource_id: str,
    text: str,
) -> bool:
    """Gera e upserta embedding com deduplicação por content_hash.

    Retorna ``True`` se houve INSERT ou UPDATE, ``False`` se texto vazio
    ou conteúdo não mudou (mesmo content_hash).
    """
    if not text.strip():
        return False

    content_hash = hashlib.sha256(text.encode()).hexdigest()

    result = await db.execute(
        select(Embedding).where(
            Embedding.user_id == user_id,
            Embedding.service == service,
            Embedding.resource_id == resource_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None and existing.content_hash == content_hash:
        return False

    vector = generate_embedding(text)
    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.vector = vector
        existing.content_hash = content_hash
        existing.updated_at = now
    else:
        db.add(
            Embedding(
                user_id=user_id,
                service=service,
                resource_id=resource_id,
                content_hash=content_hash,
                vector=vector,
                updated_at=now,
            )
        )

    return True


async def ingest_graph_data(
    db: AsyncSession,
    user_id: UUID,
    service: str,
    resource_id: str,
    data: dict,
) -> None:
    """Extrai texto, faz chunking e ingere embeddings.

    - Se ``extract_text`` retorna vazio, retorna sem operação.
    - Se 1 chunk, usa *resource_id* original.
    - Se múltiplos chunks, usa ``"{resource_id}__chunk_{i}"``.
    """
    text = extract_text(service, data)
    if not text:
        return

    # Remover entradas antigas do mesmo resource_id (cobrindo 1↔N chunks)
    await db.execute(
        delete(Embedding).where(
            Embedding.user_id == user_id,
            Embedding.service == service,
            or_(
                Embedding.resource_id == resource_id,
                Embedding.resource_id.like(f"{resource_id}__chunk_%"),
            ),
        )
    )

    chunks = chunk_text(text)
    if len(chunks) == 1:
        await ingest_item(db, user_id, service, resource_id, chunks[0])
    else:
        for i, chunk in enumerate(chunks):
            await ingest_item(db, user_id, service, f"{resource_id}__chunk_{i}", chunk)


# ---------------------------------------------------------------------------
# Busca semântica
# ---------------------------------------------------------------------------


async def semantic_search(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    limit: int = 10,
    services: list[str] | None = None,
) -> list[dict]:
    """Busca por significado via cosine distance.

    Gera o embedding da *query*, busca os vetores mais próximos no banco
    filtrados por *user_id* (e opcionalmente por *services*), descarta
    resultados com ``cosine_distance >= 0.5`` e retorna no máximo *limit*
    resultados ordenados por relevância decrescente.
    """
    query_vector = generate_embedding(query)

    distance_col = Embedding.vector.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Embedding, distance_col)
        .where(Embedding.user_id == user_id)
    )

    if services:
        stmt = stmt.where(Embedding.service.in_(services))

    stmt = stmt.order_by("distance").limit(limit)

    result = await db.execute(stmt)

    return [
        {
            "service": row.Embedding.service,
            "resource_id": row.Embedding.resource_id,
            "relevance_score": round(1 - row.distance, 4),
        }
        for row in result.all()
        if row.distance < 0.5
    ]
