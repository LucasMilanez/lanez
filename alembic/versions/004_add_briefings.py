"""Add briefings table for automatic meeting briefings

Revision ID: 004_briefings
Revises: 003_memories
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_briefings"
down_revision: Union[str, None] = "003_memories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "briefings",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_subject", sa.String(500), nullable=False),
        sa.Column(
            "event_start", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "event_end", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "attendees",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cache_read_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cache_write_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "event_id", name="uq_briefing_user_event"
        ),
    )

    op.create_index(
        "ix_briefings_user_event_start",
        "briefings",
        ["user_id", "event_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_briefings_user_event_start", table_name="briefings"
    )
    op.drop_table("briefings")
