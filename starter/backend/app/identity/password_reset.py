from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.identity.models import AuthSession, User
from app.identity.passwords import hash_password
from app.operations.email import EmailSender, get_email_sender
from app.operations.models import PasswordResetToken

logger = logging.getLogger("hitrendy.identity.password_reset")

PASSWORD_RESET_MESSAGE = (
    "Si existe una cuenta con ese correo, recibirás instrucciones para recuperar el acceso."
)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(value: datetime) -> bool:
    expires_at = value if value.tzinfo else value.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


async def request_password_reset(
    db: AsyncSession,
    *,
    email: str,
    requested_ip: str | None,
    sender: EmailSender | None = None,
) -> None:
    """Create a one-time link while keeping the response enumeration-safe."""

    normalized = email.casefold().strip()
    user = await db.scalar(
        select(User).where(User.email == normalized, User.status == "active").with_for_update()
    )
    if user is None:
        await db.commit()
        return

    now = datetime.now(UTC)
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    raw_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=settings.password_reset_ttl_seconds)
    ip_hash = hashlib.sha256(requested_ip.encode("utf-8")).hexdigest() if requested_ip else None
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=expires_at,
            requested_ip_hash=ip_hash,
        )
    )
    await db.commit()

    email_sender = sender or get_email_sender()
    reset_url = f"{settings.password_reset_url}?{urlencode({'token': raw_token})}"
    try:
        await email_sender.send_password_reset(
            recipient=normalized,
            reset_url=reset_url,
            expires_at=expires_at,
        )
    except Exception:
        # Do not expose provider state or recipient existence. The operations
        # log receives only a stable event, never the URL or token.
        logger.warning("password_reset_delivery_failed provider=%s", email_sender.provider_name)


async def confirm_password_reset(
    db: AsyncSession,
    *,
    token: str,
    password: str,
) -> None:
    reset = await db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash(token))
        .with_for_update()
    )
    if reset is None or reset.used_at is not None:
        raise AppError(
            "PASSWORD_RESET_INVALID",
            "El enlace de recuperación no es válido.",
            status_code=400,
        )
    if _is_expired(reset.expires_at):
        reset.used_at = datetime.now(UTC)
        await db.commit()
        raise AppError(
            "PASSWORD_RESET_EXPIRED",
            "El enlace de recuperación expiró.",
            status_code=410,
        )

    user = await db.get(User, reset.user_id, with_for_update=True)
    if user is None or user.status != "active":
        raise AppError(
            "PASSWORD_RESET_INVALID",
            "El enlace de recuperación no es válido.",
            status_code=400,
        )

    user.password_hash = hash_password(password)
    reset.used_at = datetime.now(UTC)
    # A successful recovery revokes every existing browser session. The user
    # must authenticate again with the new credential.
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await db.commit()

