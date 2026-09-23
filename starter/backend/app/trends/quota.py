from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session_factory
from app.trends.models import TrendProviderBudget


class BudgetPeriod(StrEnum):
    DAY = "day"
    MONTH = "month"


@dataclass(frozen=True)
class BudgetReservation:
    granted: bool
    next_reset_at: datetime


def utc_period(now: datetime, period: BudgetPeriod) -> tuple[datetime, datetime]:
    normalized = now.astimezone(UTC)
    if period == BudgetPeriod.DAY:
        start = normalized.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    start = normalized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        return start, start.replace(year=start.year + 1, month=1)
    return start, start.replace(month=start.month + 1)


class TrendQuotaBudget:
    """Durably reserve a global source budget before any provider call.

    The short transaction is intentionally independent of a request's unit of
    work.  Once the provider may have received a request, the reservation is
    never returned merely because later trend persistence rolls back.
    """

    def __init__(
        self,
        *,
        now: datetime | None = None,
        session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self.now = (now or datetime.now(UTC)).astimezone(UTC)

    async def reserve(
        self,
        *,
        provider: str,
        operation: str,
        period: BudgetPeriod,
        budget: int,
    ) -> BudgetReservation:
        start, end = utc_period(self.now, period)
        async with self._session_factory() as db, db.begin():
            row = await db.scalar(
                    select(TrendProviderBudget)
                    .where(
                        TrendProviderBudget.provider == provider,
                        TrendProviderBudget.operation == operation,
                        TrendProviderBudget.period_start == start,
                    )
                    .with_for_update()
            )
            if row is None:
                row = await self._create_or_lock(
                    db,
                    provider=provider,
                    operation=operation,
                    start=start,
                    end=end,
                    budget=budget,
                )
            # Reductions take effect immediately without rewriting the stored
            # budget below ``consumed`` (which would violate the schema
            # constraint). Increases are intentionally deferred until the
            # next UTC period, preserving the original conservative ceiling.
            effective_budget = min(row.budget, budget)
            if row.consumed >= effective_budget:
                return BudgetReservation(False, row.period_end)
            row.consumed += 1
            return BudgetReservation(True, row.period_end)

    @staticmethod
    async def _create_or_lock(
        db: AsyncSession,
        *,
        provider: str,
        operation: str,
        start: datetime,
        end: datetime,
        budget: int,
    ) -> TrendProviderBudget:
        row = TrendProviderBudget(
            provider=provider,
            operation=operation,
            period_start=start,
            period_end=end,
            budget=budget,
            consumed=0,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            return row
        except IntegrityError:
            existing = await db.scalar(
                select(TrendProviderBudget)
                .where(
                    TrendProviderBudget.provider == provider,
                    TrendProviderBudget.operation == operation,
                    TrendProviderBudget.period_start == start,
                )
                .with_for_update()
            )
            if existing is None:
                raise
            return existing
