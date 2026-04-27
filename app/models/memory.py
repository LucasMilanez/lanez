"""Modelo Memory para memória persistente do AI assistant.

Armazena memórias explícitas (texto + tags + vetor 384 dims) salvas pelo
usuário ou pelo AI via MCP. Cada save_memory é sempre INSERT — sem
deduplicação. Busca semântica via cosine_distance com pgvector.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Memory(Base):
    """Memória persistente de um usuário.

    Cada registro é um fato, decisão, preferência ou contexto salvo
    explicitamente pelo usuário ou AI assistant. O vetor de 384 dimensões
    (all-MiniLM-L6-v2) permite recuperação por busca semântica.
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    vector = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_memories_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
        Index("ix_memories_user_created", "user_id", "created_at"),
        Index("ix_memories_tags_gin", "tags", postgresql_using="gin"),
    )
