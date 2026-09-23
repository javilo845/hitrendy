"""Audited administration of account purge jobs.

This is a command line tool on purpose: there is no HTTP endpoint, no master
password and no argument that carries a secret. Authorization comes from the
``HITRENDY_ADMIN_IDENTITIES`` allowlist of the machine that runs it, and every
attempt made by an identified actor is recorded in ``admin_audit_events``.

    python -m app.identity.admin_cli status --user-id usr_x --actor ops@hitrendy --reason "soporte #12"
    python -m app.identity.admin_cli retry  --user-id usr_x --actor ops@hitrendy --reason "..." --confirm RETRY
    python -m app.identity.admin_cli reset  --user-id usr_x --actor ops@hitrendy --reason "..." --confirm RESET

Actions:

``status``
    Read-only. Reports the coarse status of the purge job.
``retry``
    Runs the pending purge now, in this process. Already completed jobs are
    reported as completed without repeating any destructive work.
``reset``
    Returns a job abandoned by a dead worker to ``pending`` so the durable
    worker can claim it again. It only touches the job row: the account stays
    blocked in ``deletion_pending`` and is never reactivated.

Arguments are parsed by ``argparse`` and no shell is ever invoked.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.identity.models import AccountPurgeJob, AdminAuditEvent
from app.identity.purge import run_account_purge

ALLOWLIST_ENV = "HITRENDY_ADMIN_IDENTITIES"

ACTIONS = ("status", "retry", "reset")
#: Mutating actions require the operator to spell the action out.
CONFIRMATIONS: dict[str, str] = {"retry": "RETRY", "reset": "RESET"}

REASON_MAX_LENGTH = 240
ACTOR_MAX_LENGTH = 255

#: Statuses a ``reset`` may return to the queue. ``completed`` is terminal.
RESETTABLE = ("processing", "failed", "pending")

EXIT_OK = 0
EXIT_DENIED = 2

DENIED_NOT_AUTHORIZED = "denied:not_authorized"
DENIED_CONFIRMATION = "denied:confirmation"
DENIED_NOT_FOUND = "denied:not_found"
DENIED_INVALID_STATE = "denied:invalid_state"


@dataclass(frozen=True)
class AdminOutcome:
    """What happened, in a form that is safe to print and to persist."""

    result: str
    message: str

    @property
    def ok(self) -> bool:
        return self.result.startswith("ok:")

    @property
    def exit_code(self) -> int:
        return EXIT_OK if self.ok else EXIT_DENIED


def _ok(status: str) -> AdminOutcome:
    return AdminOutcome(f"ok:{status}", status)


def allowed_identities() -> set[str]:
    raw = os.environ.get(ALLOWLIST_ENV, "")
    return {item.strip().casefold() for item in raw.split(",") if item.strip()}


def is_authorized(actor: str) -> bool:
    allowed = allowed_identities()
    return bool(allowed) and actor.strip().casefold() in allowed


async def _record_audit(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    reason: str,
    outcome: AdminOutcome,
    job: AccountPurgeJob | None,
    user_id: str,
) -> None:
    """Persist the attempt. Runs for denied attempts too, never for secrets."""

    db.add(
        AdminAuditEvent(
            actor=actor.strip().casefold()[:ACTOR_MAX_LENGTH],
            action=action,
            target_user_id=user_id[:64],
            target_workspace_id=job.workspace_id if job is not None else None,
            reason=reason,
            result=outcome.result,
        )
    )
    await db.commit()


async def _apply_action(
    db: AsyncSession, *, action: str, job: AccountPurgeJob
) -> AdminOutcome:
    if action == "status":
        return _ok(job.status)

    if action == "retry":
        # Completed jobs short-circuit, so a repeated retry is a safe no-op.
        return _ok((await run_account_purge(db, job)).status)

    if job.status not in RESETTABLE:
        return AdminOutcome(
            DENIED_INVALID_STATE,
            f"no se puede reiniciar una purga en estado {job.status}",
        )
    # Only the job row changes: the account remains blocked for deletion.
    job.status = "pending"
    job.started_at = None
    job.last_error = None
    job.next_attempt_at = datetime.now(UTC)
    await db.commit()
    return _ok(job.status)


async def execute(
    db: AsyncSession, *, action: str, user_id: str, actor: str, reason: str, confirm: str
) -> AdminOutcome:
    """Authorize, run and audit a single administrative action."""

    if not is_authorized(actor):
        # The actor is identified even when it is not allowed: audit the denial.
        outcome = AdminOutcome(DENIED_NOT_AUTHORIZED, "actor no autorizado")
        await _record_audit(
            db, actor=actor, action=action, reason=reason, outcome=outcome, job=None, user_id=user_id
        )
        return outcome

    expected = CONFIRMATIONS.get(action)
    if expected is not None and confirm != expected:
        outcome = AdminOutcome(DENIED_CONFIRMATION, f"confirma con --confirm {expected}")
        await _record_audit(
            db, actor=actor, action=action, reason=reason, outcome=outcome, job=None, user_id=user_id
        )
        return outcome

    job = await db.scalar(select(AccountPurgeJob).where(AccountPurgeJob.user_id == user_id))
    if job is None:
        outcome = AdminOutcome(DENIED_NOT_FOUND, "solicitud de eliminación no encontrada")
        await _record_audit(
            db, actor=actor, action=action, reason=reason, outcome=outcome, job=None, user_id=user_id
        )
        return outcome

    outcome = await _apply_action(db, action=action, job=job)
    await _record_audit(
        db, actor=actor, action=action, reason=reason, outcome=outcome, job=job, user_id=user_id
    )
    return outcome


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="admin_cli", description="Administración auditada de purgas HiTrendy"
    )
    parser.add_argument("action", choices=list(ACTIONS))
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--actor", required=True, help="Identidad del operador (sin secretos)")
    parser.add_argument("--reason", required=True, help="Motivo obligatorio para la auditoría")
    parser.add_argument("--confirm", default="")
    return parser


def _normalized_reason(raw: str) -> str | None:
    reason = raw.strip()
    if not reason or len(reason) > REASON_MAX_LENGTH:
        return None
    return reason


async def _run(args: argparse.Namespace) -> int:
    reason = _normalized_reason(args.reason)
    actor = args.actor.strip()
    if not actor or not reason:
        # Nothing is audited here: without an actor and a motive there is no
        # attributable attempt to record.
        print("actor y motivo son obligatorios", file=sys.stderr)
        return EXIT_DENIED

    session_factory = get_session_factory()
    async with session_factory() as db:
        outcome = await execute(
            db,
            action=args.action,
            user_id=args.user_id,
            actor=actor,
            reason=reason,
            confirm=args.confirm,
        )
    if outcome.ok:
        print(outcome.message)
    else:
        print(outcome.message, file=sys.stderr)
    return outcome.exit_code


def run(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
