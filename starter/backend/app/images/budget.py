"""Per-workspace daily reservation for paid image generation.

A reservation is taken *before* the provider is called and inside the same
transaction that creates the job, so two concurrent confirmations can never
overspend: the ledger row is locked with ``SELECT ... FOR UPDATE`` and the
check constraint ``consumed <= budget`` is the last line of defence.

A reservation is released only when the job fails without having reached the
provider. A failure after the call is still spend, and is kept consumed.

A release is addressed by ledger row id, never by "today". A job confirmed at
23:59 UTC that fails at 00:01 must return its unit to the period that took it,
and must leave the new day's counter alone.

What a caller is told about the allowance is always the *effective* budget --
the smaller of the stored row and the currently configured daily limit. Lowering
the limit mid-day must not leave a user looking at credit the server will refuse
to reserve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.images.models import ImageGenerationBudget


@dataclass(frozen=True)
class ImageBudgetState:
    """What the user may safely be told about their allowance."""

    budget: int
    consumed: int
    next_reset_at: datetime

    @property
    def remaining(self) -> int:
        return max(self.budget - self.consumed, 0)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0


@dataclass(frozen=True)
class BudgetReservation:
    """One consumed unit plus the ledger row that must receive any refund."""

    budget_id: str
    state: ImageBudgetState


def _effective_budget(row: ImageGenerationBudget) -> int:
    """The smaller of what was stored and what is configured right now."""

    return min(row.budget, settings.image_generation_daily_budget)


def utc_day(now: datetime) -> tuple[datetime, datetime]:
    """Return the UTC day containing ``now`` as a half-open interval."""

    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def _load_or_create(
    db: AsyncSession, *, workspace_id: str, now: datetime, lock: bool
) -> ImageGenerationBudget:
    period_start, period_end = utc_day(now)
    query = select(ImageGenerationBudget).where(
        ImageGenerationBudget.workspace_id == workspace_id,
        ImageGenerationBudget.period_start == period_start,
    )
    if lock:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is not None:
        return row

    row = ImageGenerationBudget(
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
        budget=settings.image_generation_daily_budget,
        consumed=0,
    )
    try:
        async with db.begin_nested():
            db.add(row)
    except IntegrityError:
        # Another request created today's row first; take theirs under lock.
        query = select(ImageGenerationBudget).where(
            ImageGenerationBudget.workspace_id == workspace_id,
            ImageGenerationBudget.period_start == period_start,
        )
        if lock:
            query = query.with_for_update()
        existing = await db.scalar(query)
        if existing is None:  # pragma: no cover - the unique index guarantees one
            raise
        return existing
    return row


async def read_budget(
    db: AsyncSession, *, workspace_id: str, now: datetime | None = None
) -> ImageBudgetState:
    """Report the *effective* allowance without reserving anything."""

    moment = now or datetime.now(UTC)
    row = await _load_or_create(db, workspace_id=workspace_id, now=moment, lock=False)
    return _state(row)


async def reserve(
    db: AsyncSession, *, workspace_id: str, now: datetime | None = None
) -> BudgetReservation | None:
    """Consume one unit, or return ``None`` when today's allowance is gone.

    The returned ``budget_id`` is what a later refund is addressed to: the job
    stores it, so releasing never has to guess which period paid.
    """

    moment = now or datetime.now(UTC)
    row = await _load_or_create(db, workspace_id=workspace_id, now=moment, lock=True)
    if row.consumed >= _effective_budget(row):
        return None
    row.consumed += 1
    await db.flush()
    return BudgetReservation(budget_id=row.id, state=_state(row))


async def release(db: AsyncSession, *, budget_id: str) -> None:
    """Give back one unreached reservation to the exact period that took it.

    Addressed by row id rather than by clock: the failure may be noticed on a
    later UTC day, and crediting that day's counter would both hide the refund
    and hand out an extra image.
    """

    row = await db.scalar(
        select(ImageGenerationBudget)
        .where(ImageGenerationBudget.id == budget_id)
        .with_for_update()
    )
    if row is None or row.consumed <= 0:
        return
    row.consumed -= 1
    await db.flush()


def _state(row: ImageGenerationBudget) -> ImageBudgetState:
    effective = _effective_budget(row)
    return ImageBudgetState(
        budget=effective,
        # A lowered limit can leave the row already over the new ceiling. Report
        # it as fully spent rather than as a negative remainder.
        consumed=min(row.consumed, effective),
        next_reset_at=_aware(row.period_end),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
