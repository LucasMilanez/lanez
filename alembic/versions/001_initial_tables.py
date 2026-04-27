"""Initial tables: users, graph_cache, webhook_subscriptions

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("microsoft_access_token", sa.Text(), nullable=False),
        sa.Column("microsoft_refresh_token", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # --- graph_cache ---
    op.create_table(
        "graph_cache",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_graph_cache_user_id"), "graph_cache", ["user_id"])
    op.create_index(
        "ix_graph_cache_user_service_resource",
        "graph_cache",
        ["user_id", "service", "resource_id"],
        unique=True,
    )

    # --- webhook_subscriptions ---
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("client_state", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id"),
    )
    op.create_index(op.f("ix_webhook_subscriptions_user_id"), "webhook_subscriptions", ["user_id"])
    op.create_index(op.f("ix_webhook_subscriptions_expires_at"), "webhook_subscriptions", ["expires_at"])


def downgrade() -> None:
    # Drop in reverse order to respect foreign key constraints
    op.drop_index(op.f("ix_webhook_subscriptions_expires_at"), table_name="webhook_subscriptions")
    op.drop_index(op.f("ix_webhook_subscriptions_user_id"), table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")

    op.drop_index("ix_graph_cache_user_service_resource", table_name="graph_cache")
    op.drop_index(op.f("ix_graph_cache_user_id"), table_name="graph_cache")
    op.drop_table("graph_cache")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
