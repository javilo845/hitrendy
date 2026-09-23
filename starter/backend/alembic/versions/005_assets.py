"""add assets and asset_analyses tables

Revision ID: 005
Revises: 004
Create Date: 2025-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("business_id", sa.String(64), nullable=True),
        sa.Column("original_name", sa.String(240), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False, server_default="image"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "asset_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False, server_default="demo"),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("strengths_json", sa.String(2000), nullable=False),
        sa.Column("improvements_json", sa.String(3000), nullable=False),
        sa.Column("revised_copy", sa.String(1200), nullable=True),
        sa.Column("accessibility_notes_json", sa.String(1000), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("asset_analyses")
    op.drop_table("assets")
