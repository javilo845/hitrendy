"""UTC daily budget reservations for video generation."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.videos.models import VideoGenerationBudget
from app.videos.schemas import VideoBudgetView


class VideoQuotaExceeded(AppError):
    """Safe, expected response when the workspace has no unit left."""

    def __init__(self) -> None:
        super().__init__(
            "VIDEO_QUOTA_EXHAUSTED",
            "Alcanzaste el límite de videos de hoy.",
            status_code=429,
        )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _effective_budget(row: VideoGenerationBudget) -> int:
    return min(row.budget, settings.video_generation_daily_budget)


def _next_reset(moment: datetime) -> datetime:
    current_day = _aware(moment).astimezone(UTC).date()
    return datetime.combine(current_day + timedelta(days=1), time.min, tzinfo=UTC)


async def _load_or_create(
    session: AsyncSession,
    *,
    workspace_id: str,
    day: date,
    lock: bool,
) -> VideoGenerationBudget:
    query = select(VideoGenerationBudget).where(
        VideoGenerationBudget.workspace_id == workspace_id,
        VideoGenerationBudget.day == day,
    )
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is not None:
        return row

    row = VideoGenerationBudget(
        workspace_id=workspace_id,
        day=day,
        budget=settings.video_generation_daily_budget,
        consumed=0,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        query = select(VideoGenerationBudget).where(
            VideoGenerationBudget.workspace_id == workspace_id,
            VideoGenerationBudget.day == day,
        )
        if lock:
            query = query.with_for_update()
        existing = await session.scalar(query)
        if existing is None:  # pragma: no cover - guarded by the unique constraint
            raise
        return existing
    return row


async def reserve(
    session: AsyncSession,
    workspace_id: str,
    *,
    now: datetime | None = None,
) -> VideoGenerationBudget:
    """Lock today's row, consume one unit, or raise a quota error."""

    moment = _aware(now or datetime.now(UTC)).astimezone(UTC)
    row = await _load_or_create(
        session,
        workspace_id=workspace_id,
        day=moment.date(),
        lock=True,
    )
    if row.consumed >= _effective_budget(row):
        raise VideoQuotaExceeded()
    try:
        async with session.begin_nested():
            row.consumed += 1
            await session.flush()
    except IntegrityError as exc:
        # The database check is the final race-safety boundary. Surface it as
        # the same expected quota response instead of leaking a 500.
        raise VideoQuotaExceeded() from exc
    return row


async def refund(session: AsyncSession, budget_id: str) -> None:
    """Return one reservation to the exact ledger row that paid for it."""

    row = await session.scalar(
        select(VideoGenerationBudget).where(VideoGenerationBudget.id == budget_id).with_for_update()
    )
    if row is None or row.consumed <= 0:
        return
    row.consumed -= 1
    await session.flush()


async def view(
    session: AsyncSession,
    workspace_id: str,
    *,
    now: datetime | None = None,
) -> VideoBudgetView:
    """Read the effective allowance without consuming a unit."""

    moment = _aware(now or datetime.now(UTC)).astimezone(UTC)
    row = await _load_or_create(
        session,
        workspace_id=workspace_id,
        day=moment.date(),
        lock=False,
    )
    total = _effective_budget(row)
    consumed = min(row.consumed, total)
    return VideoBudgetView(
        remaining=max(total - consumed, 0),
        total=total,
        next_reset_at=_next_reset(moment),
    )
