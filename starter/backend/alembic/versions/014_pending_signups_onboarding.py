"""add pending signups and onboarding account data

Revision ID: 014
Revises: 013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("interface_locale", sa.String(16), nullable=False, server_default="es"),
    )
    op.add_column(
        "users",
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.add_column("businesses", sa.Column("website_url", sa.String(500), nullable=True))
    op.add_column(
        "businesses",
        sa.Column("content_locale", sa.String(16), nullable=False, server_default="es"),
    )
    op.add_column(
        "businesses",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("interface_locale", sa.String(16), nullable=False, server_default="es"),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pending_signups",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email_normalized", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("oauth_provider", sa.String(64), nullable=True),
        sa.Column("oauth_subject", sa.String(255), nullable=True),
        sa.Column("interface_locale", sa.String(16), nullable=False, server_default="es"),
        sa.Column("draft_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("current_step", sa.String(32), nullable=False, server_default="business"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_idempotency_key", sa.String(255), nullable=True),
        sa.Column("completion_response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pending_signups_email_normalized", "pending_signups", ["email_normalized"])
    op.create_index("ix_pending_signups_token_hash", "pending_signups", ["token_hash"])
    op.create_index("ix_pending_signups_expires_at", "pending_signups", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pending_signups_expires_at", table_name="pending_signups")
    op.drop_index("ix_pending_signups_token_hash", table_name="pending_signups")
    op.drop_index("ix_pending_signups_email_normalized", table_name="pending_signups")
    op.drop_table("pending_signups")
    op.drop_table("user_preferences")
    op.drop_column("businesses", "onboarding_completed_at")
    op.drop_column("businesses", "content_locale")
    op.drop_column("businesses", "website_url")
    op.drop_column("users", "status")
    op.drop_column("users", "interface_locale")
