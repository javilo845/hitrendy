"""Application service for the account deletion request.

Access is revoked synchronously; the destructive purge is asynchronous and owned
by :mod:`app.identity.purge_worker`. This module only decides *what* may be
purged and records the request idempotently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.identity.models import (
    AccountPurgeJob,
    AuthSession,
    User,
    UserPreference,
    WorkspaceMember,
)

#: Confirmation phrase per interface locale. The UI must show exactly this text.
CONFIRMATION_PHRASES: dict[str, str] = {"es": "ELIMINAR", "en": "DELETE", "pt": "EXCLUIR"}
DEFAULT_LOCALE = "es"

STATUS_TOKEN_TTL = timedelta(hours=24)
#: 43 base64url characters carry 256 bits; the client must not send anything weaker.
STATUS_TOKEN_MIN_LENGTH = 43
STATUS_TOKEN_MAX_LENGTH = 128
STATUS_TOKEN_PATTERN = r"^[A-Za-z0-9_-]+$"

DELETION_PENDING = "deletion_pending"

#: Why a workspace was or was not included in the purge. Never sent to clients.
WORKSPACE_INCLUDED = "owned_exclusive"
WORKSPACE_NONE = "no_workspace"
WORKSPACE_MULTIPLE = "multiple_workspaces"
WORKSPACE_NOT_OWNER = "not_owner"
WORKSPACE_SHARED = "shared_with_others"


def confirmation_phrase(locale: str | None) -> str:
    return CONFIRMATION_PHRASES.get(locale or DEFAULT_LOCALE, CONFIRMATION_PHRASES[DEFAULT_LOCALE])


def status_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkspacePurgeDecision:
    """Which workspace, if any, this deletion is allowed to destroy."""

    workspace_id: str | None
    reason: str

    @property
    def includes_workspace(self) -> bool:
        return self.workspace_id is not None


async def decide_purgeable_workspace(db: AsyncSession, user_id: str) -> WorkspacePurgeDecision:
    """Beta policy: destroy a workspace only when it is provably personal.

    A workspace is purged only if the user belongs to exactly one workspace, owns
    it, and is its only member. Anything else keeps the workspace — and every
    other member's data — untouched, and the purge stays limited to this user's
    personal rows.
    """

    memberships = (
        (await db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user_id)))
        .scalars()
        .all()
    )
    if not memberships:
        return WorkspacePurgeDecision(None, WORKSPACE_NONE)
    if len(memberships) > 1:
        return WorkspacePurgeDecision(None, WORKSPACE_MULTIPLE)
    membership = memberships[0]
    if membership.role != "owner":
        return WorkspacePurgeDecision(None, WORKSPACE_NOT_OWNER)
    others = await db.scalar(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == membership.workspace_id,
            WorkspaceMember.user_id != user_id,
        )
    )
    if others:
        return WorkspacePurgeDecision(None, WORKSPACE_SHARED)
    return WorkspacePurgeDecision(membership.workspace_id, WORKSPACE_INCLUDED)


async def resolve_interface_locale(db: AsyncSession, user: User) -> str:
    preference = await db.get(UserPreference, user.id)
    locale = (preference.interface_locale if preference else user.interface_locale) or DEFAULT_LOCALE
    return locale if locale in CONFIRMATION_PHRASES else DEFAULT_LOCALE


async def request_account_deletion(
    db: AsyncSession, *, user_id: str, confirmation: str, status_token: str
) -> AccountPurgeJob:
    """Block access and record exactly one purge job for the account.

    Safe to call repeatedly: a retry carrying the same client token recovers the
    same job instead of creating a second one or surfacing a database error.
    """

    user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ForbiddenError()
    locale = await resolve_interface_locale(db, user)
    if confirmation.strip().casefold() != confirmation_phrase(locale).casefold():
        raise AppError(
            "DELETE_CONFIRMATION_REQUIRED",
            f"Escribe {confirmation_phrase(locale)} para confirmar.",
            status_code=422,
        )

    decision = await decide_purgeable_workspace(db, user.id)
    now = datetime.now(UTC)
    if user.status != DELETION_PENDING:
        user.status = DELETION_PENDING
        user.deletion_requested_at = now
    # Access is revoked immediately, on every device.
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    token_hash = status_token_hash(status_token)
    job = await db.scalar(select(AccountPurgeJob).where(AccountPurgeJob.user_id == user.id))
    if job is None:
        job = AccountPurgeJob(
            user_id=user.id,
            workspace_id=decision.workspace_id,
            status="pending",
            status_token_hash=token_hash,
            status_token_expires_at=now + STATUS_TOKEN_TTL,
        )
        db.add(job)
        try:
            await db.commit()
        except IntegrityError:
            # A concurrent request won the race; adopt its job instead of failing.
            await db.rollback()
            return await _rebind_existing_job(db, user_id=user.id, token_hash=token_hash, now=now)
        return job

    if job.status_token_hash != token_hash:
        job.status_token_hash = token_hash
        job.status_token_expires_at = now + STATUS_TOKEN_TTL
    await db.commit()
    return job


async def _rebind_existing_job(
    db: AsyncSession, *, user_id: str, token_hash: str, now: datetime
) -> AccountPurgeJob:
    job = await db.scalar(
        select(AccountPurgeJob).where(AccountPurgeJob.user_id == user_id).with_for_update()
    )
    if job is None:  # pragma: no cover - the unique violation guarantees a row exists
        raise ForbiddenError()
    if job.status_token_hash != token_hash:
        job.status_token_hash = token_hash
        job.status_token_expires_at = now + STATUS_TOKEN_TTL
    await db.commit()
    return job


async def read_public_deletion_status(db: AsyncSession, status_token: str) -> str:
    """Resolve a status token to a coarse status. Reveals nothing else."""

    job = await db.scalar(
        select(AccountPurgeJob).where(
            AccountPurgeJob.status_token_hash == status_token_hash(status_token)
        )
    )
    expires_at = job.status_token_expires_at if job is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if job is None or expires_at is None or expires_at <= datetime.now(UTC):
        raise ForbiddenError("El token de estado no es válido.")
    return job.status
