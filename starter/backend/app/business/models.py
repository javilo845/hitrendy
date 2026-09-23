from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_product: Mapped[str] = mapped_column(String(240), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(500), nullable=False)
    preferred_platforms: Mapped[str] = mapped_column(String(500), nullable=False)
    primary_objective: Mapped[str] = mapped_column(String(40), nullable=False)
    content_locale: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    business_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    voice_tones: Mapped[str] = mapped_column(String(200), nullable=False)
    value_proposition: Mapped[str] = mapped_column(String(500), nullable=False)
    preferred_words: Mapped[str] = mapped_column(String(2000), nullable=False, default="[]")
    forbidden_words: Mapped[str] = mapped_column(String(2000), nullable=False, default="[]")
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
