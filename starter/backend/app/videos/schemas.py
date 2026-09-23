"""Strict public and provider-bound contracts for WAVE-013 video work."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
VideoJobStatus = Literal[
    "queued",
    "preparing",
    "submitting",
    "provider_pending",
    "downloading",
    "succeeded",
    "failed",
    "cancelled",
    "execution_unknown",
]


class _StrictVideoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoShot(_StrictVideoModel):
    order: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, le=60)
    visual: str = Field(max_length=240)
    camera: str = Field(max_length=120)
    on_screen_text: str = Field(max_length=120)
    voiceover: str = Field(max_length=240)
    transition: str = Field(max_length=60)


class VideoStoryboard(_StrictVideoModel):
    hook: str = Field(max_length=160)
    duration_seconds: int = Field(ge=1, le=60)
    aspect_ratio: Literal["9:16"]
    voiceover: str = Field(max_length=600)
    music_direction: str = Field(max_length=160)
    shots: list[VideoShot] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_timing_and_order(self) -> VideoStoryboard:
        total_duration = sum(shot.duration_seconds for shot in self.shots)
        if abs(total_duration - self.duration_seconds) > 1:
            raise ValueError("La duración de las tomas debe coincidir con la duración total.")
        expected_order = list(range(1, len(self.shots) + 1))
        if [shot.order for shot in self.shots] != expected_order:
            raise ValueError("Las tomas deben tener un orden consecutivo desde 1.")
        return self


class VideoStoryboardRequest(_StrictVideoModel):
    business_id: str = Field(pattern=_ID_PATTERN)
    publication_text: str | None = Field(None, max_length=4_000)
    trend_title: str | None = Field(None, max_length=300)
    duration_seconds: int | None = Field(None, ge=1, le=60)


class VideoBudgetView(_StrictVideoModel):
    remaining: int = Field(ge=0)
    total: int = Field(ge=0)
    next_reset_at: datetime


class VideoStoryboardDraft(_StrictVideoModel):
    storyboard: VideoStoryboard
    prompt_preview: str
    negative_prompt_preview: str | None = None
    allowed_durations: list[int] = Field(min_length=1, max_length=6)
    aspect_ratio: Literal["9:16"]
    budget: VideoBudgetView
    capability: dict[str, object]


class VideoPreflightRequest(_StrictVideoModel):
    storyboard: VideoStoryboard
    prompt: str = Field(min_length=1, max_length=4_000)
    negative_prompt: str | None = Field(None, max_length=600)
    duration_seconds: int = Field(ge=1, le=60)
    source_asset_id: str | None = Field(None, pattern=_ID_PATTERN)
    project_id: str | None = Field(None, pattern=_ID_PATTERN)


class VideoPreflightResponse(_StrictVideoModel):
    allowed: bool
    aspect_ratio: Literal["9:16"]
    duration_seconds: int = Field(ge=1, le=60)
    storyboard: VideoStoryboard
    prompt_preview: str
    negative_prompt_preview: str | None = None
    source_asset_id: str | None = None
    estimated_units: int = Field(ge=0)
    budget: VideoBudgetView
    reason_code: str | None = None
    message: str | None = None
    approval_token: str | None = None
    approval_expires_at: datetime | None = None
    capability: dict[str, object]


class VideoJobCreate(VideoPreflightRequest):
    confirmed: bool = False
    approval_token: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_confirmation(self) -> VideoJobCreate:
        if self.confirmed is not True:
            raise ValueError("Confirma la generación antes de continuar.")
        return self


class VideoJobPublic(_StrictVideoModel):
    id: str
    status: VideoJobStatus
    aspect_ratio: Literal["9:16"]
    duration_seconds: int = Field(ge=1, le=60)
    source_asset_id: str | None = None
    asset_id: str | None = None
    video_url: str | None = None
    video_expires_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None
    safe_error: str | None = None
    safe_error_code: str | None = None


class VideoLatestJobResponse(_StrictVideoModel):
    job: VideoJobPublic | None = None
