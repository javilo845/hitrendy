from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    platforms: Mapped[str] = mapped_column(String(500), nullable=False)
    formats: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    objective: Mapped[str] = mapped_column(String(40), nullable=False, default="reach")
    thumbnail_url: Mapped[str] = mapped_column(String(500), nullable=False)
    canva_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False, default="4:5")
    is_public: Mapped[bool] = mapped_column(default=True, nullable=False)
    editable_slots: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
