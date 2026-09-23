"""Repair the public-template flag on databases with schema drift.

Revision ID: 026
Revises: 025
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_APPROVED_TEMPLATE_IDS = (
    "tpl_instagram_01",
    "tpl_instagram_02",
    "tpl_instagram_03",
    "tpl_instagram_04",
    "tpl_instagram_05",
)


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("templates")}
    if "is_public" in columns:
        return

    op.add_column(
        "templates",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    templates = sa.table(
        "templates",
        sa.column("id", sa.String()),
        sa.column("is_public", sa.Boolean()),
    )
    connection.execute(
        templates.update()
        .where(templates.c.id.in_(_APPROVED_TEMPLATE_IDS))
        .values(is_public=True)
    )


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("templates")}
    if "is_public" in columns:
        op.drop_column("templates", "is_public")
