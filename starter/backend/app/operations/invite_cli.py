"""Audited closed-beta invite administration.

Create prints a code once so an operator can deliver it out of band. The
database stores only its hash. Revoke takes the durable invite id and never
accepts a bearer code as a command argument.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence

from sqlalchemy import select

from app.db.session import get_session_factory
from app.identity.models import AdminAuditEvent
from app.operations.invites import (
    create_invite_code,
    invite_code_hash,
    invite_expiry,
    normalize_email,
)
from app.operations.models import BetaInvite

ALLOWLIST_ENV = "HITRENDY_ADMIN_IDENTITIES"
REASON_MAX_LENGTH = 240


def _audit(db, *, actor: str, action: str, reason: str, result: str) -> None:
    db.add(
        AdminAuditEvent(
            actor=actor.casefold()[:255],
            action=f"beta_invite_{action}",
            reason=reason,
            result=result,
        )
    )


def _allowed(actor: str) -> bool:
    identities = {
        item.strip().casefold()
        for item in os.environ.get(ALLOWLIST_ENV, "").split(",")
        if item.strip()
    }
    return bool(identities) and actor.strip().casefold() in identities


def _reason(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned if cleaned and len(cleaned) <= REASON_MAX_LENGTH else None


async def _run(args: argparse.Namespace) -> int:
    reason = _reason(args.reason)
    actor = args.actor.strip()
    if not actor or reason is None or not _allowed(actor):
        print("actor, motivo y autorización son obligatorios", file=sys.stderr)
        return 2

    factory = get_session_factory()
    async with factory() as db:
        if args.action == "create":
            raw_code = create_invite_code()
            invite = BetaInvite(
                code_hash=invite_code_hash(raw_code),
                email_normalized=normalize_email(args.email) if args.email else None,
                expires_at=invite_expiry(),
                created_by=actor.casefold()[:255],
                note=args.note.strip()[:240] if args.note else None,
            )
            db.add(invite)
            await db.flush()
            _audit(db, actor=actor, action=args.action, reason=reason, result="ok:created")
            await db.commit()
            await db.refresh(invite)
            print(f"invite_id={invite.id}")
            print(f"invite_code={raw_code}")
            return 0

        invite = await db.scalar(select(BetaInvite).where(BetaInvite.id == args.invite_id))
        if invite is None:
            _audit(db, actor=actor, action=args.action, reason=reason, result="denied:not_found")
            await db.commit()
            print("invitación no encontrada", file=sys.stderr)
            return 2
        if args.action == "revoke":
            if args.confirm != "REVOKE_INVITE":
                _audit(db, actor=actor, action=args.action, reason=reason, result="denied:confirmation")
                await db.commit()
                print("confirma con --confirm REVOKE_INVITE", file=sys.stderr)
                return 2
            invite.status = "revoked"
            _audit(db, actor=actor, action=args.action, reason=reason, result="ok:revoked")
            await db.commit()
            print("revoked")
            return 0
        _audit(db, actor=actor, action=args.action, reason=reason, result="ok:status")
        await db.commit()
        print(f"{invite.status}:{invite.expires_at.isoformat() if invite.expires_at else 'sin-expiración'}")
        return 0


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administración de invitaciones de beta HiTrendy")
    parser.add_argument("action", choices=("create", "revoke", "status"))
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--email")
    parser.add_argument("--note")
    parser.add_argument("--invite-id")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if args.action != "create" and not args.invite_id:
        parser.error("--invite-id es obligatorio para esta acción")
    return asyncio.run(_run(args))


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
