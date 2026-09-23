"""add templates table

Revision ID: 004
Revises: 003
Create Date: 2025-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("platforms", sa.String(500), nullable=False),
        sa.Column("formats", sa.String(500), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("objective", sa.String(40), nullable=False, server_default="reach"),
        sa.Column("thumbnail_url", sa.String(500), nullable=False),
        sa.Column("editable_slots", sa.Text, nullable=False, server_default="[]"),
        sa.Column("description", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("templates")
