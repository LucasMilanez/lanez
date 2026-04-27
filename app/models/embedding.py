"""Modelo Embedding para armazenamento de vetores com pgvector.

Armazena embeddings vetoriais (384 dimensões, all-MiniLM-L6-v2) de itens
do Microsoft 365 para busca semântica por cosine distance.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Embedding(Base):
    """Embedding vetorial de um item do Microsoft 365.

    Cada registro representa um trecho de texto (ou chunk) de um recurso
    Graph API, convertido em vetor de 384 dimensões para busca semântica.
    """

    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    service: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector = mapped_column(Vector(384), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "service",
            "resource_id",
            name="uq_embedding_user_service_resource",
        ),
        Index(
            "ix_embeddings_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )
