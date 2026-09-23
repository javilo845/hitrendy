"""Reset a workspace's current usage through an audited CLI adjustment.

The AI usage ledger remains append-only. A reset adds a compensating row to
``usage_adjustments`` and an administrative event; it never edits or deletes
historical provider events.

    python -m app.admin.usage reset \
        --email demo@example.com \
        --actor ops@hitrendy.example \
        --reason "feria" \
        --confirm RESET_USAGE
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.identity.admin_cli import is_authorized
from app.identity.models import AdminAuditEvent, User, WorkspaceMember
from app.operations.models import UsageAdjustment
from app.services.usage_policy import month_cost

ACTION = "usage_reset"
CONFIRMATION = "RESET_USAGE"
REASON_MAX_LENGTH = 240


@dataclass(frozen=True)
class UsageResetOutcome:
    result: str
    workspaces_reset: int = 0

    @property
    def ok(self) -> bool:
        return self.result.startswith("ok:")


def _audit(
    db: AsyncSession,
    *,
    actor: str,
    reason: str,
    result: str,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    db.add(
        AdminAuditEvent(
            actor=actor[:255],
            action=ACTION,
            target_user_id=user_id[:64] if user_id else None,
            target_workspace_id=workspace_id[:64] if workspace_id else None,
            reason=reason,
            result=result,
        )
    )


async def execute_reset(
    db: AsyncSession,
    *,
    email: str,
    actor: str,
    reason: str,
    confirm: str,
) -> UsageResetOutcome:
    """Authorize and apply one compensating adjustment per owned workspace."""

    normalized_actor = actor.strip().casefold()
    normalized_email = email.strip().casefold()
    if not is_authorized(normalized_actor):
        _audit(db, actor=normalized_actor, reason=reason, result="denied:not_authorized")
        await db.commit()
        return UsageResetOutcome("denied:not_authorized")
    if confirm != CONFIRMATION:
        _audit(db, actor=normalized_actor, reason=reason, result="denied:confirmation")
        await db.commit()
        return UsageResetOutcome("denied:confirmation")

    user = await db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if user is None:
        _audit(db, actor=normalized_actor, reason=reason, result="denied:not_found")
        await db.commit()
        return UsageResetOutcome("denied:not_found")

    workspace_result = await db.scalars(
        select(WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(WorkspaceMember.workspace_id)
    )
    workspace_ids = list(workspace_result.all())
    if not workspace_ids:
        _audit(
            db,
            actor=normalized_actor,
            reason=reason,
            result="denied:no_workspace",
            user_id=user.id,
        )
        await db.commit()
        return UsageResetOutcome("denied:no_workspace")

    for workspace_id in workspace_ids:
        spent = await month_cost(db, workspace_id=workspace_id)
        db.add(
            UsageAdjustment(
                workspace_id=workspace_id,
                actor=normalized_actor[:255],
                delta_usd=-spent,
                reason=reason,
            )
        )
        _audit(
            db,
            actor=normalized_actor,
            reason=reason,
            result="ok:reset",
            user_id=user.id,
            workspace_id=workspace_id,
        )
    await db.commit()
    return UsageResetOutcome("ok:reset", workspaces_reset=len(workspace_ids))


def _reason(raw: str) -> str | None:
    value = raw.strip()
    return value if value and len(value) <= REASON_MAX_LENGTH else None


async def _run(args: argparse.Namespace) -> int:
    actor = args.actor.strip()
    reason = _reason(args.reason)
    if not actor or reason is None:
        print("actor y motivo son obligatorios", file=sys.stderr)
        return 2

    factory = get_session_factory()
    async with factory() as db:
        outcome = await execute_reset(
            db,
            email=args.email,
            actor=actor,
            reason=reason,
            confirm=args.confirm,
        )
    if outcome.ok:
        print(f"usage_reset: {outcome.workspaces_reset} workspace(s)")
        return 0
    print(outcome.result, file=sys.stderr)
    return 2


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset auditado del uso de beta HiTrendy")
    parser.add_argument("action", choices=("reset",))
    parser.add_argument("--email", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm", default="")
    return asyncio.run(_run(parser.parse_args(argv)))


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
