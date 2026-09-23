"""Seed the Phase 1 system templates.

Revision ID: 012
Revises: 011
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


# Keep this copy owned by the migration so historical data cannot drift with application code.
TEMPLATES = (
    {
        "id": "tpl_reel_01",
        "title": "Reel promocional",
        "platforms": _json(["instagram", "tiktok"]),
        "formats": _json(["reel", "short_video"]),
        "category": "promotion",
        "objective": "sales",
        "thumbnail_url": "/static/thumbnails/reel-promo.svg",
        "editable_slots": _json(["title_text", "caption", "cta"]),
        "description": "Video corto presentando un producto nuevo.",
    },
    {
        "id": "tpl_static_01",
        "title": "Publicación estática",
        "platforms": _json(["instagram", "facebook"]),
        "formats": _json(["static_post", "carousel"]),
        "category": "promotion",
        "objective": "engagement",
        "thumbnail_url": "/static/thumbnails/static-post.svg",
        "editable_slots": _json(["headline", "body", "cta", "hashtags"]),
        "description": "Publicación con imagen principal y texto descriptivo.",
    },
    {
        "id": "tpl_story_01",
        "title": "Historia de producto",
        "platforms": _json(["instagram", "facebook"]),
        "formats": _json(["story"]),
        "category": "awareness",
        "objective": "brand_awareness",
        "thumbnail_url": "/static/thumbnails/story-product.svg",
        "editable_slots": _json(["caption", "cta"]),
        "description": "Historia efímera destacando un producto o servicio.",
    },
    {
        "id": "tpl_video_01",
        "title": "Video testimonial",
        "platforms": _json(["tiktok", "instagram", "youtube"]),
        "formats": _json(["short_video", "reel"]),
        "category": "social_proof",
        "objective": "community",
        "thumbnail_url": "/static/thumbnails/video-testimonial.svg",
        "editable_slots": _json(["intro", "question", "cta"]),
        "description": "Formato de entrevista rápida con un cliente satisfecho.",
    },
    {
        "id": "tpl_carousel_01",
        "title": "Carrusel educativo",
        "platforms": _json(["instagram", "linkedin", "facebook"]),
        "formats": _json(["carousel"]),
        "category": "education",
        "objective": "engagement",
        "thumbnail_url": "/static/thumbnails/carousel-edu.svg",
        "editable_slots": _json(["slide_1", "slide_2", "slide_3", "cta"]),
        "description": "Carrusel de 3 diapositivas explicando un concepto.",
    },
    {
        "id": "tpl_whatsapp_01",
        "title": "Oferta por WhatsApp",
        "platforms": _json(["whatsapp"]),
        "formats": _json(["static_post"]),
        "category": "promotion",
        "objective": "sales",
        "thumbnail_url": "/static/thumbnails/whatsapp-offer.svg",
        "editable_slots": _json(["greeting", "offer", "cta"]),
        "description": "Mensaje promocional optimizado para WhatsApp.",
    },
    {
        "id": "tpl_launch_01",
        "title": "Lanzamiento de producto",
        "platforms": _json(["instagram", "tiktok", "facebook"]),
        "formats": _json(["reel", "static_post", "story"]),
        "category": "launch",
        "objective": "launch",
        "thumbnail_url": "/static/thumbnails/launch-product.svg",
        "editable_slots": _json(["announcement", "details", "cta"]),
        "description": "Anuncio de lanzamiento con entusiasmo y detalles clave.",
    },
    {
        "id": "tpl_event_01",
        "title": "Invitación a evento",
        "platforms": _json(["instagram", "facebook"]),
        "formats": _json(["static_post", "story"]),
        "category": "events",
        "objective": "store_visits",
        "thumbnail_url": "/static/thumbnails/event-invite.svg",
        "editable_slots": _json(["title", "date", "location", "cta"]),
        "description": "Invitación visual para un evento presencial o virtual.",
    },
)


def _templates_table() -> sa.TableClause:
    return sa.table(
        "templates",
        sa.column("id", sa.String(64)),
        sa.column("title", sa.String(120)),
        sa.column("platforms", sa.String(500)),
        sa.column("formats", sa.String(500)),
        sa.column("category", sa.String(40)),
        sa.column("objective", sa.String(40)),
        sa.column("thumbnail_url", sa.String(500)),
        sa.column("editable_slots", sa.Text()),
        sa.column("description", sa.Text()),
    )


def upgrade() -> None:
    templates = _templates_table()
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statement = postgresql_insert(templates).values(list(TEMPLATES))
        bind.execute(statement.on_conflict_do_nothing(index_elements=["id"]))
        return

    for template in TEMPLATES:
        exists = bind.execute(
            sa.select(templates.c.id).where(templates.c.id == template["id"])
        ).scalar_one_or_none()
        if exists is None:
            bind.execute(sa.insert(templates).values(**template))


def downgrade() -> None:
    # Rows are intentionally preserved: this migration cannot distinguish a seeded row
    # from a later customized row, and projects do not enforce a template FK historically.
    pass
