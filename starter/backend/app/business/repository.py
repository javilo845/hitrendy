from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.models import BrandProfile, Business
from app.core.errors import NotFoundError


def _serialize_platforms(platforms: list[str]) -> str:
    return json.dumps(platforms)


def _deserialize_platforms(raw: str) -> list[str]:
    return json.loads(raw) if raw else []


def _serialize_words(words: list[str]) -> str:
    return json.dumps(words)


def _deserialize_words(raw: str) -> list[str]:
    return json.loads(raw) if raw else []


async def create_business(
    db: AsyncSession,
    workspace_id: str,
    data: dict,
) -> Business:
    business = Business(
        workspace_id=workspace_id,
        name=data["name"],
        category=data["category"],
        country=data["country"],
        city=data["city"],
        description=data.get("description"),
        website_url=data.get("website_url"),
        primary_product=data["primary_product"],
        target_audience=data["target_audience"],
        preferred_platforms=_serialize_platforms(data["preferred_platforms"]),
        primary_objective=data["primary_objective"],
        content_locale=data.get("content_locale", "es"),
        onboarding_completed_at=data.get("onboarding_completed_at"),
    )
    db.add(business)
    await db.flush()
    await db.refresh(business)
    return business


async def get_business(db: AsyncSession, workspace_id: str, business_id: str) -> Business:
    result = await db.execute(
        select(Business).where(Business.id == business_id, Business.workspace_id == workspace_id)
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Negocio")
    return business


async def update_business(
    db: AsyncSession,
    workspace_id: str,
    business_id: str,
    data: dict,
) -> Business:
    business = await get_business(db, workspace_id, business_id)
    for key, value in data.items():
        if key == "preferred_platforms":
            setattr(business, key, _serialize_platforms(value))
        elif hasattr(business, key):
            setattr(business, key, value)
    await db.flush()
    await db.refresh(business)
    return business


def business_to_dict(business: Business) -> dict:
    return {
        "id": business.id,
        "workspace_id": business.workspace_id,
        "name": business.name,
        "category": business.category,
        "country": business.country,
        "city": business.city,
        "description": business.description,
        "website_url": business.website_url,
        "primary_product": business.primary_product,
        "target_audience": business.target_audience,
        "preferred_platforms": _deserialize_platforms(business.preferred_platforms),
        "primary_objective": business.primary_objective,
        "content_locale": business.content_locale,
        "onboarding_completed_at": (
            business.onboarding_completed_at.isoformat()
            if business.onboarding_completed_at
            else None
        ),
        "created_at": business.created_at.isoformat() if business.created_at else None,
        "updated_at": business.updated_at.isoformat() if business.updated_at else None,
    }


async def upsert_brand_profile(
    db: AsyncSession,
    workspace_id: str,
    business_id: str,
    data: dict,
) -> BrandProfile:
    await get_business(db, workspace_id, business_id)
    result = await db.execute(select(BrandProfile).where(BrandProfile.business_id == business_id))
    existing = result.scalar_one_or_none()
    if existing:
        existing.voice_tones = _serialize_words(data.get("voice_tones", []))
        existing.value_proposition = data.get("value_proposition", "")
        existing.preferred_words = _serialize_words(data.get("preferred_words", []))
        existing.forbidden_words = _serialize_words(data.get("forbidden_words", []))
        existing.primary_color = data.get("primary_color")
        existing.secondary_color = data.get("secondary_color")
        existing.version += 1
        await db.flush()
        await db.refresh(existing)
        return existing
    profile = BrandProfile(
        business_id=business_id,
        voice_tones=_serialize_words(data.get("voice_tones", [])),
        value_proposition=data.get("value_proposition", ""),
        preferred_words=_serialize_words(data.get("preferred_words", [])),
        forbidden_words=_serialize_words(data.get("forbidden_words", [])),
        primary_color=data.get("primary_color"),
        secondary_color=data.get("secondary_color"),
        version=1,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


async def get_brand_profile(db: AsyncSession, workspace_id: str, business_id: str) -> BrandProfile:
    await get_business(db, workspace_id, business_id)
    result = await db.execute(select(BrandProfile).where(BrandProfile.business_id == business_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Perfil de marca")
    return profile


def brand_profile_to_dict(profile: BrandProfile) -> dict:
    return {
        "id": profile.id,
        "business_id": profile.business_id,
        "voice_tones": _deserialize_words(profile.voice_tones),
        "value_proposition": profile.value_proposition,
        "preferred_words": _deserialize_words(profile.preferred_words),
        "forbidden_words": _deserialize_words(profile.forbidden_words),
        "primary_color": profile.primary_color,
        "secondary_color": profile.secondary_color,
        "version": profile.version,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
