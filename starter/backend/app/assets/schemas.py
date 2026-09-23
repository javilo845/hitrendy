from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(max_length=280)]


class Improvement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: Literal["high", "medium", "low"]
    area: Literal[
        "message", "hierarchy", "readability", "brand", "cta", "platform", "accessibility"
    ]
    reason: str = Field(max_length=300)
    action: str = Field(max_length=300)


class CanvaTemplateRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(max_length=200)
    canva_url: str = Field(max_length=500)
    thumbnail_url: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=500)
    # No Canva template has a thumbnail we are allowed to fetch, so the card is
    # drawn from this niche token instead. Declared here because extra="ignore"
    # would otherwise drop it between the provider and the response.
    cover: str | None = Field(default=None, max_length=40)


class AssetAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = Field(min_length=1, max_length=1000)
    strengths: list[ShortText] = Field(min_length=1, max_length=6)
    improvements: list[Improvement] = Field(min_length=1, max_length=8)
    revised_copy: str | None = Field(None, max_length=1200)
    accessibility_notes: list[ShortText] = Field(default_factory=list, max_length=6)
    ai_hallmarks: list[str] = Field(default_factory=list)
    canva_templates: list[CanvaTemplateRecommendation] = Field(default_factory=list)
    canva_slots_guide: dict[str, str] = Field(default_factory=dict)
    #: What we searched Canva for, and other angles worth trying. Both seed the
    #: refine control beside the results so the user can search again in place.
    canva_query: str = Field(default="", max_length=200)
    canva_query_suggestions: list[ShortText] = Field(default_factory=list, max_length=4)
