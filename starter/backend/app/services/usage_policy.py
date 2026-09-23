from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import AIUsageEvent
from app.core.config import settings
from app.core.errors import AppError
from app.operations.models import UsageAdjustment


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def month_cost(db: AsyncSession, *, workspace_id: str) -> Decimal:
    event_value = await db.scalar(
        select(func.coalesce(func.sum(AIUsageEvent.reported_cost), 0)).where(
            AIUsageEvent.workspace_id == workspace_id,
            AIUsageEvent.created_at >= _month_start(),
        )
    )
    adjustment_value = await db.scalar(
        select(func.coalesce(func.sum(UsageAdjustment.delta_usd), 0)).where(
            UsageAdjustment.workspace_id == workspace_id,
            UsageAdjustment.created_at >= _month_start(),
        )
    )
    try:
        return Decimal(str(event_value or 0)) + Decimal(str(adjustment_value or 0))
    except Exception:
        return Decimal("0")


async def ensure_generation_allowed(db: AsyncSession, *, workspace_id: str) -> None:
    """Apply the configured global cap before an external text call.

    ``soft`` records and surfaces the limit through the operations endpoint but
    does not block the beta. ``hard`` is the only mode that refuses a call.
    A zero budget means no global cap, which keeps local/demo behavior intact.
    """

    if settings.usage_enforcement_mode != "hard" or settings.monthly_ai_budget_usd <= 0:
        return
    spent = await month_cost(db, workspace_id=workspace_id)
    if spent >= Decimal(str(settings.monthly_ai_budget_usd)):
        raise AppError(
            "COST_CAP_REACHED",
            "El límite de uso de esta beta se alcanzó. Inténtalo después o contacta soporte.",
            status_code=402,
            retryable=False,
        )


async def usage_limit_snapshot(db: AsyncSession, *, workspace_id: str) -> dict[str, object]:
    budget = Decimal(str(settings.monthly_ai_budget_usd))
    spent = await month_cost(db, workspace_id=workspace_id) if budget > 0 else Decimal("0")
    remaining = max(budget - spent, Decimal("0")) if budget > 0 else None
    alert = bool(
        budget > 0
        and spent / budget * 100 >= Decimal(str(settings.cost_alert_threshold_percent))
    )
    return {
        "mode": settings.usage_enforcement_mode,
        "period": "calendar_month",
        "budget_usd": format(budget, "f") if budget > 0 else None,
        "spent_usd": format(spent, "f") if budget > 0 else None,
        "remaining_usd": format(remaining, "f") if remaining is not None else None,
        "alert": alert,
    }
