"""Add audit_log table for Fase 7

Revision ID: 005_audit_log
Revises: 004_briefings
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "005_audit_log"
down_revision: Union[str, None] = "004_briefings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "event_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_log_user_created",
        "audit_log",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_log_user_type_created",
        "audit_log",
        ["user_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_type_created", table_name="audit_log")
    op.drop_index("ix_audit_log_user_created", table_name="audit_log")
    op.drop_table("audit_log")
