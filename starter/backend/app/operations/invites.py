from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.operations.models import BetaInvite


def invite_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.casefold().strip()


def create_invite_code() -> str:
    return f"htb_{secrets.token_urlsafe(24)}"


async def resolve_invite(
    db: AsyncSession, *, code: str, email: str, lock: bool = False
) -> BetaInvite:
    statement = select(BetaInvite).where(BetaInvite.code_hash == invite_code_hash(code))
    if lock:
        statement = statement.with_for_update()
    invite = await db.scalar(statement)
    now = datetime.now(UTC)
    if invite is None or invite.status != "active":
        raise AppError("BETA_INVITE_INVALID", "La invitación de beta no es válida.", status_code=403)
    if invite.expires_at is not None:
        expires_at = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            invite.status = "revoked"
            await db.commit()
            raise AppError("BETA_INVITE_EXPIRED", "La invitación de beta expiró.", status_code=403)
    normalized_email = normalize_email(email)
    if invite.email_normalized and invite.email_normalized != normalized_email:
        raise AppError("BETA_INVITE_INVALID", "La invitación de beta no es válida.", status_code=403)
    return invite


async def redeem_invite(db: AsyncSession, invite: BetaInvite) -> None:
    if invite.status != "active":
        raise AppError("BETA_INVITE_INVALID", "La invitación de beta no es válida.", status_code=403)
    invite.status = "redeemed"
    invite.redeemed_at = datetime.now(UTC)


def invite_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=settings.beta_invite_ttl_seconds)

