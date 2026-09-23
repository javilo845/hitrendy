"""create identity and business tables

Revision ID: 001
Revises:
Create Date: 2025-01-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("role", sa.String(32), default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("country", sa.String(80), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("primary_product", sa.String(240), nullable=False),
        sa.Column("target_audience", sa.String(500), nullable=False),
        sa.Column("preferred_platforms", sa.String(500), nullable=False),
        sa.Column("primary_objective", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "brand_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("voice_tones", sa.String(200), nullable=False),
        sa.Column("value_proposition", sa.String(500), nullable=False),
        sa.Column("preferred_words", sa.String(2000), nullable=False, server_default="[]"),
        sa.Column("forbidden_words", sa.String(2000), nullable=False, server_default="[]"),
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("secondary_color", sa.String(7), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("brand_profiles")
    op.drop_table("businesses")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("users")
