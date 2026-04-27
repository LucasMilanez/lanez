"""Add memories table for persistent memory

Revision ID: 003_memories
Revises: 002_embeddings
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "003_memories"
down_revision: Union[str, None] = "002_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- memories ---
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("vector", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # B-tree composite index on (user_id, created_at) for chronological listings
    op.create_index(
        "ix_memories_user_created",
        "memories",
        ["user_id", "created_at"],
    )

    # GIN index on tags for overlap filtering (raw SQL — ARRAY type needs direct SQL)
    op.execute(
        "CREATE INDEX ix_memories_tags_gin ON memories USING gin(tags)"
    )

    # HNSW index for cosine similarity search (raw SQL — vector type not native to Alembic)
    op.execute(
        "CREATE INDEX ix_memories_vector_hnsw ON memories "
        "USING hnsw (vector vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memories_tags_gin")
    op.drop_index("ix_memories_user_created", table_name="memories")
    op.drop_table("memories")
