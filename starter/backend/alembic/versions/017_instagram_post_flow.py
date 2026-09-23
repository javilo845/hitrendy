"""Approved Instagram templates and minimal five-minute-flow timing.

Revision ID: 017
Revises: 016
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("canva_url", sa.String(length=500), nullable=True))
    op.add_column(
        "templates",
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False, server_default="4:5"),
    )
    op.add_column(
        "templates", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    templates = sa.table(
        "templates",
        sa.column("id", sa.String(64)),
        sa.column("title", sa.String(120)),
        sa.column("platforms", sa.String(500)),
        sa.column("formats", sa.String(500)),
        sa.column("category", sa.String(40)),
        sa.column("objective", sa.String(40)),
        sa.column("thumbnail_url", sa.String(500)),
        sa.column("canva_url", sa.String(500)),
        sa.column("aspect_ratio", sa.String(16)),
        sa.column("editable_slots", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("is_public", sa.Boolean()),
    )
    approved = [
        ("tpl_instagram_01", "Producto destacado", "promotion", "sales", "/templates/flores.png", "https://canva.link/jxr6r3xdtdx3p18", ["headline", "caption", "cta", "hashtags"], "Post vertical 4:5 para destacar un producto."),
        ("tpl_instagram_02", "Oferta cercana", "promotion", "engagement", "/templates/coffee.png", "https://canva.link/d5gnf0tsot7t70m", ["headline", "body", "cta", "hashtags"], "Post vertical 4:5 para una oferta clara y editable."),
        ("tpl_instagram_03", "Historia de marca", "brand_awareness", "brand_awareness", "/templates/amor.png", "https://canva.link/2hk1wscap0jikce", ["headline", "caption", "cta"], "Post vertical 4:5 para comunicar el valor de marca."),
        ("tpl_instagram_04", "Novedad del negocio", "launch", "launch", "/templates/summer.png", "https://canva.link/9667338l5l4mgwg", ["headline", "details", "caption", "cta"], "Post vertical 4:5 para un lanzamiento o novedad."),
        ("tpl_instagram_05", "Invitación local", "community", "store_visits", "/templates/comida.png", "https://canva.link/7ped4en1xal5yk7", ["headline", "date", "location", "cta"], "Post vertical 4:5 para invitar a visitar el negocio."),
    ]
    bind = op.get_bind()
    # Keep old template rows for historical project references, but do not expose
    # them in the public catalogue.
    bind.execute(sa.update(templates).values(is_public=False))
    for item in approved:
        values = {
            "id": item[0], "title": item[1], "platforms": json.dumps(["instagram"]),
            "formats": json.dumps(["static_post"]), "category": item[2], "objective": item[3],
            "thumbnail_url": item[4], "canva_url": item[5], "aspect_ratio": "4:5",
            "editable_slots": json.dumps(item[6]), "description": item[7], "is_public": True,
        }
        exists = bind.execute(sa.select(templates.c.id).where(templates.c.id == item[0])).scalar()
        if exists:
            bind.execute(sa.update(templates).where(templates.c.id == item[0]).values(**values))
        else:
            bind.execute(sa.insert(templates).values(**values))
    op.create_table(
        "creation_flow_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_key", sa.String(length=160), nullable=True),
        sa.Column("flow_started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("first_generation_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("completion_status", sa.String(length=32), nullable=False, server_default="started"),
        sa.UniqueConstraint("workspace_id", "flow_key", name="uq_creation_flow_key"),
    )
    op.create_index("ix_creation_flow_events_workspace_id", "creation_flow_events", ["workspace_id"])
    op.create_index("ix_creation_flow_events_business_id", "creation_flow_events", ["business_id"])


def downgrade() -> None:
    op.drop_constraint("uq_creation_flow_key", "creation_flow_events", type_="unique")
    op.drop_index("ix_creation_flow_events_business_id", table_name="creation_flow_events")
    op.drop_index("ix_creation_flow_events_workspace_id", table_name="creation_flow_events")
    op.drop_table("creation_flow_events")
    approved_ids = ["tpl_instagram_01", "tpl_instagram_02", "tpl_instagram_03", "tpl_instagram_04", "tpl_instagram_05"]
    op.execute(sa.text("DELETE FROM templates WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)).params(ids=approved_ids))
    op.drop_column("templates", "is_public")
    op.drop_column("templates", "aspect_ratio")
    op.drop_column("templates", "canva_url")
