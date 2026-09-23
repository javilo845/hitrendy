"""Durable state for bounded asynchronous video generation.

Only job metadata and references are persisted here.  Video bytes stay in the
private object-storage flow represented by an ``assets`` row; provider payloads,
secrets and signed URLs never belong in these tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import Asset  # noqa: F401 registers ``assets`` for the FK
from app.db.base import Base
from app.identity.models import User  # noqa: F401 registers ``users`` for the FK
from app.projects.models import Project  # noqa: F401 registers ``projects`` for the FK

VIDEO_JOB_STATUSES = (
    "queued",
    "preparing",
    "submitting",
    "provider_pending",
    "downloading",
    "succeeded",
    "failed",
    "cancelled",
    "execution_unknown",
)
TERMINAL_VIDEO_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled", "execution_unknown"})


def _uuid() -> str:
    return uuid.uuid4().hex


class VideoGenerationJob(Base):
    """One approved video request and its fenced asynchronous lifecycle."""

    __tablename__ = "video_generation_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default=text("'queued'"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    storyboard_json: Mapped[str] = mapped_column(Text, nullable=False)
    # This is an approved logical reference, deliberately not an FK with
    # ``ON DELETE SET NULL``. The worker must observe a missing source and fail
    # before submit instead of silently changing the approved request.
    source_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(191), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_generation_budgets.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    poll_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    download_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'preparing', 'submitting', 'provider_pending', "
            "'downloading', 'succeeded', 'failed', 'cancelled', 'execution_unknown')",
            name="ck_video_jobs_status",
        ),
        CheckConstraint("aspect_ratio IN ('9:16')", name="ck_video_jobs_aspect_ratio"),
        CheckConstraint(
            "duration_seconds > 0 AND duration_seconds <= 60",
            name="ck_video_jobs_duration_seconds",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_video_jobs_attempt_count"),
        CheckConstraint("poll_count >= 0", name="ck_video_jobs_poll_count"),
        CheckConstraint(
            "download_attempt_count >= 0",
            name="ck_video_jobs_download_attempt_count",
        ),
        CheckConstraint(
            "asset_id IS NULL OR status = 'succeeded'",
            name="ck_video_jobs_asset_requires_succeeded",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR asset_id IS NOT NULL",
            name="ck_video_jobs_succeeded_requires_asset",
        ),
        Index("ix_video_jobs_claim", "status", "created_at"),
        Index("ix_video_jobs_polling", "status", "last_polled_at"),
        Index("ix_video_jobs_requested_by_user", "requested_by_user_id"),
        Index(
            "ix_video_jobs_workspace_project",
            "workspace_id",
            "project_id",
            "created_at",
        ),
        UniqueConstraint("provider", "provider_job_id", name="uq_video_jobs_provider_job"),
    )


class VideoGenerationBudget(Base):
    """UTC daily reservation ledger for one workspace."""

    __tablename__ = "video_generation_budgets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    budget: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "day", name="uq_video_budgets_workspace_day"),
        CheckConstraint("consumed >= 0", name="ck_video_budgets_consumed_nonnegative"),
        CheckConstraint("budget >= 0", name="ck_video_budgets_budget_nonnegative"),
        CheckConstraint("consumed <= budget", name="ck_video_budgets_consumed_lte_budget"),
    )
