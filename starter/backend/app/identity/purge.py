"""Durable account purge.

The purge is deliberately split in two phases so a retry never repeats work
that already succeeded:

1. Storage objects are removed one asset at a time and each asset row is
   committed right after its object is gone. A crash between two assets leaves
   the finished ones deleted and the pending ones intact.
2. Relational rows are removed inside a single transaction scoped to the
   account's workspace and user.

A job only becomes ``completed`` once both phases finished. Every failure keeps
the account blocked (``users.status = 'deletion_pending'``) and leaves the job
in ``failed`` so it can be retried by the worker or by an audited administrator.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetAnalysis
from app.identity.models import (
    AccountPurgeJob,
    AuthSession,
    OAuthAccount,
    PendingSignup,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)
from app.providers.storage import ObjectStorageProvider, get_object_storage_provider

logger = logging.getLogger("hitrendy.purge")

#: A ``processing`` job whose worker died is reclaimable after this delay.
STUCK_PROCESSING_AFTER = timedelta(minutes=15)
#: A ``failed`` job is retried automatically after this delay.
FAILURE_BACKOFF = timedelta(minutes=5)
#: Assets are streamed in batches so a large workspace never loads at once.
ASSET_BATCH_SIZE = 50

#: The only failure text ever persisted. Provider messages may carry secrets.
GENERIC_FAILURE = "No se pudo completar la purga de recursos."
STUCK_FAILURE = "La purga anterior no respondió; puede reintentarse de forma segura."

TERMINAL_STATUS = "completed"

#: Workspace-scoped rows, ordered so children are always removed before owners.
#: ``templates`` and ``admin_audit_events`` are global and never listed here.
_WORKSPACE_STATEMENTS: tuple[str, ...] = (
    """
    DELETE FROM artifact_events WHERE artifact_id IN (
        SELECT id FROM generated_artifacts
        WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = :workspace_id)
           OR project_id IN (SELECT id FROM projects WHERE workspace_id = :workspace_id)
    )
    """,
    """
    DELETE FROM artifact_feedback WHERE artifact_id IN (
        SELECT id FROM generated_artifacts
        WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = :workspace_id)
           OR project_id IN (SELECT id FROM projects WHERE workspace_id = :workspace_id)
    )
    """,
    """
    DELETE FROM artifact_versions WHERE artifact_id IN (
        SELECT id FROM generated_artifacts
        WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = :workspace_id)
           OR project_id IN (SELECT id FROM projects WHERE workspace_id = :workspace_id)
    )
    """,
    """
    DELETE FROM generated_artifacts
    WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = :workspace_id)
       OR project_id IN (SELECT id FROM projects WHERE workspace_id = :workspace_id)
    """,
    "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = :workspace_id)",
    "DELETE FROM conversations WHERE workspace_id = :workspace_id",
    "DELETE FROM projects WHERE workspace_id = :workspace_id",
    "DELETE FROM creation_flow_events WHERE workspace_id = :workspace_id",
    "DELETE FROM ai_usage_events WHERE workspace_id = :workspace_id",
    "DELETE FROM idempotency_records WHERE workspace_id = :workspace_id",
    "DELETE FROM workspace_trend_relevance WHERE workspace_id = :workspace_id",
    "DELETE FROM upload_sessions WHERE workspace_id = :workspace_id",
    # Image/video jobs and their budget ledgers go before ``assets``. Video
    # ``source_asset_id`` is a deliberate logical reference (not SET NULL), so
    # purge may remove the source row in phase 1; the worker will never see a
    # partially purged job because the relational phase deletes the job before
    # the workspace disappears.
    "DELETE FROM image_generation_jobs WHERE workspace_id = :workspace_id",
    "DELETE FROM image_generation_budgets WHERE workspace_id = :workspace_id",
    "DELETE FROM video_generation_jobs WHERE workspace_id = :workspace_id",
    "DELETE FROM video_generation_budgets WHERE workspace_id = :workspace_id",
    # Social connections carry encrypted provider tokens. Deleting the workspace
    # destroys the only copy of the key material's plaintext target, which is the
    # point: a purge must not leave a credential behind that still works.
    "DELETE FROM social_connections WHERE workspace_id = :workspace_id",
    "DELETE FROM asset_analyses WHERE asset_id IN (SELECT id FROM assets WHERE workspace_id = :workspace_id)",
    "DELETE FROM assets WHERE workspace_id = :workspace_id",
    "DELETE FROM brand_profiles WHERE business_id IN (SELECT id FROM businesses WHERE workspace_id = :workspace_id)",
    "DELETE FROM businesses WHERE workspace_id = :workspace_id",
)


async def _object_already_gone(storage: ObjectStorageProvider, key: str) -> bool:
    """A missing object means a previous attempt already removed it."""

    try:
        return not await storage.exists(key=key)
    except Exception:
        return False


async def _delete_object(storage: ObjectStorageProvider, key: str) -> None:
    try:
        await storage.delete(key=key)
    except Exception:
        if await _object_already_gone(storage, key):
            return
        raise


async def _purge_storage_objects(db: AsyncSession, workspace_id: str) -> None:
    storage = get_object_storage_provider()
    while True:
        assets = (
            (
                await db.execute(
                    select(Asset)
                    .where(Asset.workspace_id == workspace_id)
                    .order_by(Asset.id)
                    .limit(ASSET_BATCH_SIZE)
                )
            )
            .scalars()
            .all()
        )
        if not assets:
            return
        for asset in assets:
            await _delete_object(storage, asset.storage_path)
            # Committing per asset makes a retry skip everything already gone.
            await db.execute(delete(AssetAnalysis).where(AssetAnalysis.asset_id == asset.id))
            await db.execute(delete(Asset).where(Asset.id == asset.id))
            await db.commit()


async def _purge_relational_data(db: AsyncSession, job: AccountPurgeJob) -> None:
    user = await db.get(User, job.user_id)
    email_normalized = user.email.strip().casefold() if user is not None else None
    oauth_identities = (
        (
            await db.execute(
                select(OAuthAccount.provider, OAuthAccount.provider_subject).where(
                    OAuthAccount.user_id == job.user_id
                )
            )
        )
        .tuples()
        .all()
    )

    if job.workspace_id is not None:
        parameters = {"workspace_id": job.workspace_id}
        for statement in _WORKSPACE_STATEMENTS:
            await db.execute(text(statement), parameters)

    await db.execute(delete(UserPreference).where(UserPreference.user_id == job.user_id))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == job.user_id))
    await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == job.user_id))

    # Any signup still in flight for the same identity must not resurrect access.
    if email_normalized:
        await db.execute(
            delete(PendingSignup).where(PendingSignup.email_normalized == email_normalized)
        )
    for provider, subject in oauth_identities:
        await db.execute(
            delete(PendingSignup).where(
                and_(
                    PendingSignup.oauth_provider == provider,
                    PendingSignup.oauth_subject == subject,
                )
            )
        )

    await db.execute(delete(WorkspaceMember).where(WorkspaceMember.user_id == job.user_id))
    if job.workspace_id is not None:
        await db.execute(
            delete(WorkspaceMember).where(WorkspaceMember.workspace_id == job.workspace_id)
        )
        await db.execute(delete(Workspace).where(Workspace.id == job.workspace_id))
    await db.execute(delete(User).where(User.id == job.user_id))


def _claimable(now: datetime):
    return or_(
        and_(
            AccountPurgeJob.status == "pending",
            or_(
                AccountPurgeJob.next_attempt_at.is_(None),
                AccountPurgeJob.next_attempt_at <= now,
            ),
        ),
        and_(
            AccountPurgeJob.status == "failed",
            or_(
                AccountPurgeJob.next_attempt_at.is_(None),
                AccountPurgeJob.next_attempt_at <= now,
            ),
        ),
        and_(
            AccountPurgeJob.status == "processing",
            AccountPurgeJob.started_at.is_not(None),
            AccountPurgeJob.started_at <= now - STUCK_PROCESSING_AFTER,
        ),
    )


async def claim_next_purge_job(db: AsyncSession) -> AccountPurgeJob | None:
    """Atomically move one claimable job to ``processing``.

    ``FOR UPDATE ... SKIP LOCKED`` guarantees that two workers running against
    PostgreSQL never take the same row. The transaction is committed before any
    deletion runs so the claim is durable even if the worker dies mid-purge.
    """

    now = datetime.now(UTC)
    job = await db.scalar(
        select(AccountPurgeJob)
        .where(_claimable(now))
        .order_by(AccountPurgeJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        await db.rollback()
        return None
    return await _mark_processing(db, job, now)


async def _mark_processing(
    db: AsyncSession, job: AccountPurgeJob, now: datetime
) -> AccountPurgeJob:
    job.status = "processing"
    job.started_at = now
    job.attempt_count += 1
    job.last_error = None
    job.next_attempt_at = None
    await db.commit()
    return job


async def claim_purge_job(db: AsyncSession, job_id: str) -> AccountPurgeJob | None:
    """Claim one specific job. Returns ``None`` when it is not claimable."""

    now = datetime.now(UTC)
    job = await db.scalar(
        select(AccountPurgeJob)
        .where(and_(AccountPurgeJob.id == job_id, _claimable(now)))
        .with_for_update(skip_locked=True)
    )
    if job is None:
        await db.rollback()
        return None
    return await _mark_processing(db, job, now)


async def execute_purge(db: AsyncSession, job: AccountPurgeJob) -> AccountPurgeJob:
    """Run both purge phases for a job already claimed as ``processing``."""

    job_id = job.id
    try:
        if job.workspace_id is not None:
            await _purge_storage_objects(db, job.workspace_id)
        await _purge_relational_data(db, job)
        job.status = TERMINAL_STATUS
        job.completed_at = datetime.now(UTC)
        job.last_error = None
        job.next_attempt_at = None
        await db.commit()
    except Exception:
        # The provider message may embed credentials; only the job id is logged.
        logger.warning("account_purge_failed job_id=%s", job_id)
        await db.rollback()
        reloaded = await db.get(AccountPurgeJob, job_id)
        if reloaded is None:
            raise
        job = reloaded
        job.status = "failed"
        job.last_error = GENERIC_FAILURE
        job.next_attempt_at = datetime.now(UTC) + FAILURE_BACKOFF
        await db.commit()
    return job


async def run_account_purge(db: AsyncSession, job: AccountPurgeJob) -> AccountPurgeJob:
    """Claim (if needed) and run a purge for a known job.

    Completed jobs are returned untouched, and a job actively held by another
    worker is left alone: the caller sees ``processing`` and can retry later.
    """

    if job.status == TERMINAL_STATUS:
        return job
    claimed = await claim_purge_job(db, job.id)
    if claimed is None:
        refreshed = await db.get(AccountPurgeJob, job.id)
        return refreshed if refreshed is not None else job
    return await execute_purge(db, claimed)


async def recover_stuck_jobs(db: AsyncSession) -> int:
    """Flag abandoned ``processing`` jobs as retryable. Returns how many."""

    cutoff = datetime.now(UTC) - STUCK_PROCESSING_AFTER
    stuck = (
        (
            await db.execute(
                select(AccountPurgeJob).where(
                    and_(
                        AccountPurgeJob.status == "processing",
                        AccountPurgeJob.started_at.is_not(None),
                        AccountPurgeJob.started_at <= cutoff,
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for job in stuck:
        job.status = "failed"
        job.last_error = STUCK_FAILURE
        job.next_attempt_at = datetime.now(UTC)
    if stuck:
        await db.commit()
    return len(stuck)


async def process_available_purge_jobs(db: AsyncSession, *, limit: int = 25) -> int:
    """Claim and run up to ``limit`` jobs. Returns how many were processed."""

    processed = 0
    while processed < limit:
        job = await claim_next_purge_job(db)
        if job is None:
            return processed
        await execute_purge(db, job)
        processed += 1
    return processed
