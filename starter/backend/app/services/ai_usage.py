from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import AIUsageEvent
from app.core.errors import AppError


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def combine_usage_metadata(*entries: dict[str, object] | None) -> dict[str, object] | None:
    """Combine provider calls from one logical artifact without inventing cost data."""
    present = [entry for entry in entries if entry is not None]
    if not present:
        return None

    combined: dict[str, object] = {}
    for field in ("requested_model", "currency"):
        value = next(
            (entry[field] for entry in present if isinstance(entry.get(field), str)),
            None,
        )
        if value is not None:
            combined[field] = value

    for field in ("actual_model", "provider_request_id"):
        value = next(
            (entry[field] for entry in reversed(present) if isinstance(entry.get(field), str)),
            None,
        )
        if value is not None:
            combined[field] = value

    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [entry.get(field) for entry in present]
        if all(isinstance(value, int) and value >= 0 for value in values):
            combined[field] = sum(values)

    costs = [_decimal(entry.get("reported_cost")) for entry in present]
    if all(cost is not None for cost in costs):
        combined["reported_cost"] = sum(costs, Decimal("0"))
    return combined


async def record_usage(
    db: AsyncSession, *, workspace_id: str, user_id: str, capability: str,
    quality_level: str, provider: str, requested_model: str,
    metadata: dict[str, object] | None, outcome: str,
) -> AIUsageEvent:
    metadata = metadata or {}
    event = AIUsageEvent(
        workspace_id=workspace_id, user_id=user_id, capability=capability,
        quality_level=quality_level, provider=provider, requested_model=str(metadata.get("requested_model") or requested_model),
        actual_model=metadata.get("actual_model") if isinstance(metadata.get("actual_model"), str) else None,
        prompt_tokens=metadata.get("prompt_tokens") if isinstance(metadata.get("prompt_tokens"), int) else None,
        completion_tokens=metadata.get("completion_tokens") if isinstance(metadata.get("completion_tokens"), int) else None,
        total_tokens=metadata.get("total_tokens") if isinstance(metadata.get("total_tokens"), int) else None,
        reported_cost=_decimal(metadata.get("reported_cost")),
        currency=metadata.get("currency") if isinstance(metadata.get("currency"), str) else None,
        provider_request_id=metadata.get("provider_request_id") if isinstance(metadata.get("provider_request_id"), str) else None,
        outcome=outcome,
    )
    db.add(event)
    return event


def outcome_for_error(exc: Exception) -> str:
    if not isinstance(exc, AppError):
        return "provider_error"
    if exc.status_code == 402 or exc.code == "PAYMENT_REQUIRED":
        return "payment_required"
    if exc.status_code == 429:
        return "quota_exhausted" if "quota" in exc.code.lower() else "rate_limited"
    if exc.status_code == 504 or "TIMEOUT" in exc.code:
        return "timeout"
    if "INVALID_RESPONSE" in exc.code or "CONTRACT_INVALID" in exc.code:
        return "invalid_response"
    return "provider_error"
