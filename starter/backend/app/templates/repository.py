from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.templates.models import Template


def _serialize(items: list[str]) -> str:
    return json.dumps(items)


def _deserialize(raw: str) -> list[str]:
    return json.loads(raw) if raw else []


SEED_TEMPLATES: list[dict] = [
    {
        "id": "tpl_instagram_01",
        "title": "Producto destacado",
        "platforms": ["instagram"],
        "formats": ["static_post"],
        "category": "promotion",
        "objective": "sales",
        "thumbnail_url": "/templates/flores.png",
        "canva_url": "https://canva.link/jxr6r3xdtdx3p18",
        "aspect_ratio": "4:5",
        "editable_slots": ["headline", "caption", "cta", "hashtags"],
        "description": "Post vertical 4:5 para destacar un producto.",
    },
    {
        "id": "tpl_instagram_02",
        "title": "Oferta cercana",
        "platforms": ["instagram"],
        "formats": ["static_post"],
        "category": "promotion",
        "objective": "engagement",
        "thumbnail_url": "/templates/coffee.png",
        "canva_url": "https://canva.link/d5gnf0tsot7t70m",
        "aspect_ratio": "4:5",
        "editable_slots": ["headline", "body", "cta", "hashtags"],
        "description": "Post vertical 4:5 para una oferta clara y editable.",
    },
    {
        "id": "tpl_instagram_03",
        "title": "Historia de marca",
        "platforms": ["instagram"],
        "formats": ["static_post"],
        "category": "brand_awareness",
        "objective": "brand_awareness",
        "thumbnail_url": "/templates/amor.png",
        "canva_url": "https://canva.link/2hk1wscap0jikce",
        "aspect_ratio": "4:5",
        "editable_slots": ["headline", "caption", "cta"],
        "description": "Post vertical 4:5 para comunicar el valor de marca.",
    },
    {
        "id": "tpl_instagram_04",
        "title": "Novedad del negocio",
        "platforms": ["instagram"],
        "formats": ["static_post"],
        "category": "launch",
        "objective": "launch",
        "thumbnail_url": "/templates/summer.png",
        "canva_url": "https://canva.link/9667338l5l4mgwg",
        "aspect_ratio": "4:5",
        "editable_slots": ["headline", "details", "caption", "cta"],
        "description": "Post vertical 4:5 para un lanzamiento o novedad.",
    },
    {
        "id": "tpl_instagram_05",
        "title": "Invitación local",
        "platforms": ["instagram"],
        "formats": ["static_post"],
        "category": "community",
        "objective": "store_visits",
        "thumbnail_url": "/templates/comida.png",
        "canva_url": "https://canva.link/7ped4en1xal5yk7",
        "aspect_ratio": "4:5",
        "editable_slots": ["headline", "date", "location", "cta"],
        "description": "Post vertical 4:5 para invitar a visitar el negocio.",
    },
]


def template_to_dict(t: Template) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "platforms": _deserialize(t.platforms),
        "formats": _deserialize(t.formats),
        "category": t.category,
        "objective": t.objective,
        "thumbnail_url": t.thumbnail_url,
        "canva_url": t.canva_url,
        "aspect_ratio": t.aspect_ratio,
        "editable_slots": _deserialize(t.editable_slots),
        "description": t.description,
        # Distinguishes a fillable DB template from a Canva browse entry, and
        # DB templates ship a real thumbnail so they need no drawn cover.
        "source": "custom",
        "cover": None,
    }


async def seed_templates(db: AsyncSession) -> None:
    existing = (await db.execute(select(Template))).scalars().all()
    for template in existing:
        if template.id not in {item["id"] for item in SEED_TEMPLATES}:
            template.is_public = False
    for data in SEED_TEMPLATES:
        template = await db.get(Template, data["id"])
        values = {
            **data,
            "platforms": _serialize(data["platforms"]),
            "formats": _serialize(data["formats"]),
            "editable_slots": _serialize(data["editable_slots"]),
            "is_public": True,
        }
        if template is None:
            db.add(Template(**values))
        else:
            for key, value in values.items():
                setattr(template, key, value)
    await db.commit()


async def list_templates(
    db: AsyncSession,
    *,
    platform: str | None = None,
    format: str | None = None,
    category: str | None = None,
    objective: str | None = None,
    search: str | None = None,
) -> list[dict]:
    query = select(Template).where(Template.is_public.is_(True))
    if platform:
        query = query.where(Template.platforms.contains(platform))
    if format:
        query = query.where(Template.formats.contains(format))
    if category:
        query = query.where(Template.category == category)
    if objective:
        query = query.where(Template.objective == objective)
    if search:
        query = query.where(Template.title.ilike(f"%{search}%"))
    result = await db.execute(query)
    return [template_to_dict(t) for t in result.scalars().all()]


async def get_template(db: AsyncSession, template_id: str) -> dict:
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.is_public.is_(True))
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Plantilla")
    return template_to_dict(template)
