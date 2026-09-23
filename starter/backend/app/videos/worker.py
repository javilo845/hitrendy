"""Standalone worker for the fenced asynchronous video state machine."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import re
import secrets
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.assets.validation import validate_image_bytes
from app.core.capabilities import Capability, CapabilityOutcome, get_runtime_capability_registry
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_session_factory
from app.providers.factory import get_video_generation_provider
from app.providers.storage import get_object_storage_provider
from app.providers.video import VideoGenerationProvider, VideoGenerationRequest
from app.services.ai_usage import record_usage
from app.videos import budget as budget_ledger
from app.videos.models import TERMINAL_VIDEO_JOB_STATUSES, VideoGenerationJob
from app.videos.validation import VideoValidationError, validate_video_bytes

logger = logging.getLogger("hitrendy.videos.worker")

DEFAULT_INTERVAL_SECONDS = 5
DEFAULT_BATCH = 5

GENERIC_FAILURE = "No pudimos generar el video. Inténtalo nuevamente."
UNKNOWN_EXECUTION = (
    "No pudimos confirmar el resultado de esta generación. Revísala antes de reintentar."
)
STORAGE_FAILURE = "No pudimos guardar el video generado. Inténtalo nuevamente."
PREPARATION_FAILURE = "No pudimos preparar el video. Inténtalo nuevamente."
PROVIDER_FAILURE = "El proveedor no pudo completar el video."
DOWNLOAD_FAILURE = "No pudimos descargar el video generado. Inténtalo nuevamente."

_SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class _ClaimLost(Exception):
    """The row was fenced by another worker or by the orphan sweep."""


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _safe_code(value: object, fallback: str) -> str:
    if isinstance(value, str) and _SAFE_CODE.fullmatch(value):
        return value[:64]
    return fallback


def _safe_provider_status(value: object, fallback: str) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned and len(cleaned) <= 48 and _SAFE_CODE.fullmatch(cleaned):
            return cleaned
    return fallback


def _provider_prefix(value: object) -> str:
    if isinstance(value, str):
        return value[:12]
    return "unknown"


def _claimable(now: datetime):
    stuck_before = now - timedelta(seconds=settings.video_generation_stuck_after_seconds)
    poll_before = now - timedelta(seconds=settings.video_generation_poll_interval_seconds)
    lease_available = or_(
        VideoGenerationJob.claim_token.is_(None),
        and_(
            VideoGenerationJob.claim_token.is_not(None),
            VideoGenerationJob.claimed_at.is_not(None),
            VideoGenerationJob.claimed_at < stuck_before,
        ),
    )
    return or_(
        VideoGenerationJob.status == "queued",
        and_(
            VideoGenerationJob.status == "preparing",
            VideoGenerationJob.claimed_at.is_not(None),
            VideoGenerationJob.claimed_at < stuck_before,
        ),
        and_(
            VideoGenerationJob.status == "provider_pending",
            or_(
                VideoGenerationJob.last_polled_at.is_(None),
                VideoGenerationJob.last_polled_at < poll_before,
            ),
            lease_available,
        ),
        and_(
            VideoGenerationJob.status == "downloading",
            VideoGenerationJob.claimed_at.is_not(None),
            VideoGenerationJob.claimed_at < stuck_before,
        ),
    )


def _claim_priority():
    now = _now()
    stuck_before = now - timedelta(seconds=settings.video_generation_stuck_after_seconds)
    poll_before = now - timedelta(seconds=settings.video_generation_poll_interval_seconds)
    lease_available = or_(
        VideoGenerationJob.claim_token.is_(None),
        and_(
            VideoGenerationJob.claim_token.is_not(None),
            VideoGenerationJob.claimed_at.is_not(None),
            VideoGenerationJob.claimed_at < stuck_before,
        ),
    )
    return case(
        (VideoGenerationJob.status == "queued", 1),
        (
            and_(
                VideoGenerationJob.status == "preparing",
                VideoGenerationJob.claimed_at.is_not(None),
                VideoGenerationJob.claimed_at < stuck_before,
            ),
            2,
        ),
        (
            and_(
                VideoGenerationJob.status == "provider_pending",
                or_(
                    VideoGenerationJob.last_polled_at.is_(None),
                    VideoGenerationJob.last_polled_at < poll_before,
                ),
                lease_available,
            ),
            3,
        ),
        (
            and_(
                VideoGenerationJob.status == "downloading",
                VideoGenerationJob.claimed_at.is_not(None),
                VideoGenerationJob.claimed_at < stuck_before,
            ),
            4,
        ),
        else_=99,
    )


async def sweep_submitting(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Fence stale submit calls as unknown; never refund or re-submit them."""

    moment = now or _now()
    stale_before = moment - timedelta(seconds=settings.video_generation_stuck_after_seconds)
    rows = await session.scalars(
        select(VideoGenerationJob)
        .where(
            VideoGenerationJob.status == "submitting",
            VideoGenerationJob.claimed_at.is_not(None),
            VideoGenerationJob.claimed_at < stale_before,
        )
        .with_for_update(skip_locked=True)
    )
    swept = 0
    for job in rows:
        token = job.claim_token
        if not token:
            continue
        result = await session.execute(
            update(VideoGenerationJob)
            .where(
                VideoGenerationJob.id == job.id,
                VideoGenerationJob.claim_token == token,
                VideoGenerationJob.status == "submitting",
                VideoGenerationJob.claimed_at < stale_before,
            )
            .values(
                status="execution_unknown",
                completed_at=moment,
                last_error_code="execution_unknown",
                last_error=UNKNOWN_EXECUTION,
                claim_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        swept += int(result.rowcount or 0)
    await session.commit()
    if swept:
        logger.warning("video_submit_orphans_swept count=%s", swept)
    return swept


async def _terminal(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    status: str,
    code: str,
    message: str,
    refund: bool,
    user_id: str | None = None,
    cost_units: int | None = None,
    record_usage_event: bool = False,
) -> bool:
    """Write one terminal verdict behind the current fencing token."""

    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status.not_in(TERMINAL_VIDEO_JOB_STATUSES),
        )
        .values(
            status=status,
            completed_at=_now(),
            last_error_code=_safe_code(code, "video_generation_failed"),
            last_error=message[:500],
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    if won and refund and job.budget_id:
        await budget_ledger.refund(session, job.budget_id)
    if won and record_usage_event:
        await _record_usage(
            session,
            job=job,
            user_id=user_id,
            cost_units=cost_units,
            outcome=code,
        )
    await session.commit()
    if not won:
        logger.warning("video_claim_lost job_id=%s stage=terminal", job.id[:12])
    return won


async def _record_usage(
    session: AsyncSession,
    *,
    job: VideoGenerationJob,
    user_id: str | None,
    cost_units: object,
    outcome: str,
) -> None:
    actor_id = user_id or job.requested_by_user_id
    if not actor_id:
        return
    normalized = (
        cost_units if isinstance(cost_units, int) and not isinstance(cost_units, bool) else None
    )
    if normalized is not None and normalized < 0:
        normalized = None
    # ``reported_cost=None`` is intentional: unknown provider cost stays
    # unknown in AIUsageEvent instead of being converted to zero.
    await record_usage(
        session,
        workspace_id=job.workspace_id,
        user_id=actor_id,
        capability=Capability.VIDEO_GENERATION.value,
        quality_level="standard",
        provider=job.provider,
        requested_model=job.model or "",
        metadata={"reported_cost": normalized},
        outcome=outcome[:32],
    )


async def _release_claim(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    status: str,
    values: dict[str, object] | None = None,
) -> bool:
    updates = {"claim_token": None, "claimed_at": None}
    if values:
        updates.update(values)
    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status == status,
        )
        .values(**updates)
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    await session.commit()
    return won


async def claim_next_job(session: AsyncSession) -> VideoGenerationJob | None:
    """Claim one row in priority order and commit the lease before work."""

    now = _now()
    await sweep_submitting(session, now=now)
    while True:
        job = await session.scalar(
            select(VideoGenerationJob)
            .where(_claimable(now))
            .order_by(_claim_priority(), VideoGenerationJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await session.rollback()
            return None

        token = secrets.token_urlsafe(32)
        claimed_status = job.status
        job.claim_token = token
        job.claimed_at = now
        if claimed_status in {"queued", "preparing"}:
            # This is the number of preparation/submit attempts. It must not
            # move while the remote provider is merely being polled.
            job.attempt_count += 1
            job.status = "preparing"
        elif claimed_status == "provider_pending":
            # Reserve this poll while the row lock is held. The lease remains
            # active after commit until execute_job releases it.
            job.poll_count += 1
            job.last_polled_at = now
        elif claimed_status == "downloading":
            # Provider downloads are idempotent by provider_job_id and the
            # object key is fenced by this claim token, so retrying a dead
            # download is safe and observable separately.
            job.download_attempt_count += 1
        job.last_error = None
        job.last_error_code = None
        await session.commit()
        await session.refresh(job)

        if claimed_status in {"queued", "preparing"} and (
            job.attempt_count > settings.video_generation_max_attempts
        ):
            paid_boundary_crossed = bool(
                job.submitted_at or job.provider_started_at or job.provider_job_id
            )
            if paid_boundary_crossed:
                await _terminal(
                    session,
                    job,
                    token=token,
                    status="execution_unknown",
                    code="execution_unknown",
                    message=UNKNOWN_EXECUTION,
                    refund=False,
                    record_usage_event=True,
                )
            else:
                await _terminal(
                    session,
                    job,
                    token=token,
                    status="failed",
                    code="max_attempts",
                    message=GENERIC_FAILURE,
                    refund=True,
                )
            continue
        return job


async def _provider_for_job(job: VideoGenerationJob) -> VideoGenerationProvider:
    """Re-authorize the persisted route without silently switching it."""

    current_model = settings.video_generation_model or None
    if job.provider != settings.video_provider or job.model != current_model:
        raise AppError(
            "provider_route_unavailable",
            "La ruta de generación aprobada ya no está disponible.",
            status_code=409,
        )
    provider = get_video_generation_provider()
    if provider.name != job.provider:
        raise AppError(
            "provider_route_unavailable",
            "La ruta de generación aprobada ya no está disponible.",
            status_code=409,
        )
    return provider


async def _source_image(session: AsyncSession, job: VideoGenerationJob) -> tuple[bytes, str] | None:
    if not job.source_asset_id:
        return None
    asset = await session.scalar(
        select(Asset).where(
            Asset.id == job.source_asset_id,
            Asset.workspace_id == job.workspace_id,
            Asset.asset_type == "image",
        )
    )
    if asset is None:
        raise AppError(
            "source_asset_missing",
            "La imagen de origen ya no está disponible.",
            status_code=409,
        )
    try:
        content = await get_object_storage_provider().read(key=asset.storage_path)
        metadata = validate_image_bytes(content, asset.mime_type)
    except Exception as exc:
        raise AppError(
            "source_asset_missing",
            "La imagen de origen ya no está disponible.",
            status_code=409,
        ) from exc
    return content, metadata.mime_type


def _request_from_job(
    job: VideoGenerationJob, source: tuple[bytes, str] | None
) -> VideoGenerationRequest:
    try:
        storyboard = json.loads(job.storyboard_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            "invalid_storyboard",
            "El storyboard guardado no es válido.",
            status_code=409,
        ) from exc
    if not isinstance(storyboard, dict):
        raise AppError(
            "invalid_storyboard",
            "El storyboard guardado no es válido.",
            status_code=409,
        )
    return VideoGenerationRequest(
        prompt=job.prompt,
        negative_prompt=job.negative_prompt,
        storyboard=storyboard,
        aspect_ratio=job.aspect_ratio,
        duration_seconds=job.duration_seconds,
        model=job.model or "",
        source_image=source[0] if source else None,
        source_image_mime=source[1] if source else None,
    )


async def _mark_submitting(session: AsyncSession, job: VideoGenerationJob, *, token: str) -> bool:
    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status == "preparing",
        )
        .values(status="submitting", submitted_at=_now())
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    await session.commit()
    if won:
        await session.refresh(job)
    return won


async def _mark_preparing(session: AsyncSession, job: VideoGenerationJob, *, token: str) -> bool:
    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status == "preparing",
        )
        .values(status="preparing")
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    await session.commit()
    if won:
        await session.refresh(job)
    return won


async def _persist_submission(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    provider_job_id: str,
    provider_status: str,
) -> bool:
    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status == "submitting",
        )
        .values(
            provider_job_id=provider_job_id,
            provider_status=provider_status,
            provider_started_at=_now(),
            status="provider_pending",
            claim_token=None,
            claimed_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("video_submission_persist_failed job_id=%s", job.id[:12])
        return False
    if won:
        await session.refresh(job)
        logger.info(
            "video_submitted job_id=%s provider_job_prefix=%s",
            job.id[:12],
            _provider_prefix(provider_job_id),
        )
    return won


def _explicit_provider_rejection(error: BaseException) -> bool:
    """Classify a provider's explicit client rejection after the paid boundary."""

    return isinstance(error, AppError) and 400 <= error.status_code < 500


async def _execute_preparing(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    user_id: str | None,
) -> VideoGenerationJob:
    if not settings.video_generation_enabled:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code="capability_unavailable",
            message="La generación de video no está disponible.",
            refund=True,
        )
        await session.refresh(job)
        return job
    if not await _mark_preparing(session, job, token=token):
        await session.refresh(job)
        return job
    try:
        provider = await _provider_for_job(job)
        source = await _source_image(session, job)
        request = _request_from_job(job, source)
    except AppError as error:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code=error.code,
            message=error.message,
            refund=True,
        )
        await session.refresh(job)
        return job
    except Exception:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code="preparation_failed",
            message=PREPARATION_FAILURE,
            refund=True,
        )
        await session.refresh(job)
        return job

    if not await _mark_submitting(session, job, token=token):
        await session.refresh(job)
        return job

    try:
        submission = await asyncio.wait_for(
            provider.submit(request),
            timeout=settings.video_generation_timeout_seconds,
        )
    except Exception as error:
        if _explicit_provider_rejection(error):
            await _terminal(
                session,
                job,
                token=token,
                status="failed",
                code="provider_rejected",
                message=PROVIDER_FAILURE,
                refund=False,
                user_id=user_id,
                cost_units=None,
                record_usage_event=True,
            )
        else:
            await _terminal(
                session,
                job,
                token=token,
                status="execution_unknown",
                code="execution_unknown",
                message=UNKNOWN_EXECUTION,
                refund=False,
                user_id=user_id,
                record_usage_event=True,
            )
        await session.refresh(job)
        return job

    provider_job_id = getattr(submission, "provider_job_id", None)
    if not isinstance(provider_job_id, str) or not 1 <= len(provider_job_id) <= 191:
        await _terminal(
            session,
            job,
            token=token,
            status="execution_unknown",
            code="execution_unknown",
            message=UNKNOWN_EXECUTION,
            refund=False,
            user_id=user_id,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job
    provider_status = _safe_provider_status(
        getattr(submission, "provider_status", None), "submitted"
    )
    if not await _persist_submission(
        session,
        job,
        token=token,
        provider_job_id=provider_job_id,
        provider_status=provider_status,
    ):
        await session.refresh(job)
    return job


async def _mark_downloading(session: AsyncSession, job: VideoGenerationJob, *, token: str) -> bool:
    result = await session.execute(
        update(VideoGenerationJob)
        .where(
            VideoGenerationJob.id == job.id,
            VideoGenerationJob.claim_token == token,
            VideoGenerationJob.status == "downloading",
        )
        .values(download_started_at=_now())
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    await session.commit()
    if won:
        await session.refresh(job)
    return won


async def _delete_quietly(storage, key: str, *, job_id: str) -> None:
    try:
        await storage.delete(key=key)
    except Exception:
        logger.warning("video_orphan_object job_id=%s", job_id[:12])


def _detached_storage_failed_job(
    *,
    job_id: str,
    workspace_id: str,
    budget_id: str | None,
    requested_by_user_id: str | None,
    provider: str,
    model: str | None,
    provider_job_id: str | None,
    prompt: str,
    negative_prompt: str | None,
    storyboard_json: str,
    aspect_ratio: str,
    duration_seconds: int,
) -> VideoGenerationJob:
    """Return a safe result if ORM recovery itself is unavailable."""

    fallback = VideoGenerationJob(
        id=job_id,
        workspace_id=workspace_id,
        status="failed",
        provider=provider,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        storyboard_json=storyboard_json,
        aspect_ratio=aspect_ratio,
        duration_seconds=duration_seconds,
        provider_job_id=provider_job_id,
        budget_id=budget_id,
        requested_by_user_id=requested_by_user_id,
    )
    fallback.status = "failed"
    fallback.completed_at = _now()
    fallback.last_error_code = "storage_failed"
    fallback.last_error = STORAGE_FAILURE
    fallback.claim_token = None
    return fallback


async def _recover_after_storage_failure(
    session: AsyncSession,
    *,
    storage,
    object_key: str,
    token: str,
    job_id: str,
    workspace_id: str,
    budget_id: str | None,
    requested_by_user_id: str | None,
    provider: str,
    model: str | None,
    provider_job_id: str | None,
    usage_user_id: str | None,
    cost_units: int | None,
    prompt: str,
    negative_prompt: str | None,
    storyboard_json: str,
    aspect_ratio: str,
    duration_seconds: int,
) -> VideoGenerationJob:
    """Compensate a post-upload failure without touching an expired ORM job."""

    try:
        await session.rollback()
    except Exception:
        logger.warning("video_storage_rollback_failed job_id=%s", job_id[:12], exc_info=True)
    await _delete_quietly(storage, object_key, job_id=job_id)

    try:
        recovered = await session.scalar(
            select(VideoGenerationJob).where(
                VideoGenerationJob.id == job_id,
                VideoGenerationJob.workspace_id == workspace_id,
            )
        )
        if recovered is None:
            raise RuntimeError("video job disappeared during storage compensation")

        won = await _terminal(
            session,
            recovered,
            token=token,
            status="failed",
            code="storage_failed",
            message=STORAGE_FAILURE,
            refund=False,
            record_usage_event=False,
        )
        if won:
            try:
                await session.refresh(recovered)
            except Exception:
                # The durable UPDATE already committed; keep the returned
                # object safe even if a refresh fails on a damaged connection.
                recovered.status = "failed"
                recovered.completed_at = _now()
                recovered.last_error_code = "storage_failed"
                recovered.last_error = STORAGE_FAILURE
                recovered.claim_token = None
            if usage_user_id:
                try:
                    await _record_usage(
                        session,
                        job=recovered,
                        user_id=usage_user_id,
                        cost_units=cost_units,
                        outcome="storage_failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.warning(
                        "video_storage_usage_record_failed job_id=%s",
                        job_id[:12],
                        exc_info=True,
                    )
        return recovered
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.warning("video_storage_recovery_rollback_failed job_id=%s", job_id[:12])
        logger.exception(
            "video_storage_compensation_failed job_id=%s workspace_id=%s "
            "budget_id=%s provider=%s model=%s",
            job_id[:12],
            workspace_id[:12],
            budget_id,
            provider,
            model,
        )
        return _detached_storage_failed_job(
            job_id=job_id,
            workspace_id=workspace_id,
            budget_id=budget_id,
            requested_by_user_id=requested_by_user_id,
            provider=provider,
            model=model,
            provider_job_id=provider_job_id,
            prompt=prompt,
            negative_prompt=negative_prompt,
            storyboard_json=storyboard_json,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
        )


async def _execute_downloading(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    user_id: str | None,
    cost_units: int | None = None,
) -> VideoGenerationJob:
    if not job.provider_job_id:
        await _terminal(
            session,
            job,
            token=token,
            status="execution_unknown",
            code="execution_unknown",
            message=UNKNOWN_EXECUTION,
            refund=False,
            user_id=user_id,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job
    if not await _mark_downloading(session, job, token=token):
        await session.refresh(job)
        return job

    # Capture every value needed for compensation before any later ORM error
    # can trigger rollback and expire ``job``.
    job_id = job.id
    workspace_id = job.workspace_id
    budget_id = job.budget_id
    requested_by_user_id = job.requested_by_user_id
    usage_user_id = user_id or requested_by_user_id
    provider_name = job.provider
    model = job.model
    provider_job_id = job.provider_job_id
    prompt = job.prompt
    negative_prompt = job.negative_prompt
    storyboard_json = job.storyboard_json
    aspect_ratio = job.aspect_ratio
    duration_seconds = job.duration_seconds

    try:
        provider = await _provider_for_job(job)
        artifact = await asyncio.wait_for(
            provider.download(
                job.provider_job_id,
                duration_seconds=job.duration_seconds,
            ),
            timeout=settings.video_generation_timeout_seconds,
        )
    except Exception:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code="download_failed",
            message=DOWNLOAD_FAILURE,
            refund=False,
            user_id=user_id,
            cost_units=cost_units,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job

    try:
        metadata = validate_video_bytes(
            artifact.content,
            declared_mime=artifact.mime_type,
            expected_duration=job.duration_seconds,
            expected_ratio=9 / 16,
            max_bytes=settings.video_generation_max_bytes,
        )
    except VideoValidationError as error:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code=error.code,
            message=str(error),
            refund=False,
            user_id=user_id,
            cost_units=cost_units,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job
    except Exception:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code="invalid_response",
            message="El video generado no pasó la validación.",
            refund=False,
            user_id=user_id,
            cost_units=cost_units,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job

    # Include the current claim in the private key so a late worker that lost
    # its fence can delete only its own object, never a winner's object.
    object_key = f"workspaces/{job.workspace_id}/videos/{job.id}/{token}.mp4"
    storage = get_object_storage_provider()
    try:
        await storage.put(
            key=object_key,
            content=artifact.content,
            content_type=metadata.mime_type,
        )
    except Exception:
        await _delete_quietly(storage, object_key, job_id=job.id)
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code="storage_failed",
            message=STORAGE_FAILURE,
            refund=False,
            user_id=user_id,
            cost_units=cost_units,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job

    try:
        asset = Asset(
            workspace_id=job.workspace_id,
            original_name=f"video-{job.id[:8]}.mp4",
            storage_path=object_key,
            mime_type=metadata.mime_type,
            file_size_bytes=metadata.size_bytes,
            asset_type="video",
            width=metadata.width,
            height=metadata.height,
            duration_seconds=int(round(metadata.duration_seconds)),
        )
        session.add(asset)
        await session.flush()
        completed = await session.execute(
            update(VideoGenerationJob)
            .where(
                VideoGenerationJob.id == job.id,
                VideoGenerationJob.claim_token == token,
                VideoGenerationJob.status == "downloading",
                VideoGenerationJob.asset_id.is_(None),
            )
            .values(
                status="succeeded",
                asset_id=asset.id,
                completed_at=_now(),
                last_error=None,
                last_error_code=None,
                claim_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        if not completed.rowcount:
            raise _ClaimLost()
        await _record_usage(
            session,
            job=job,
            user_id=user_id,
            cost_units=cost_units,
            outcome="success",
        )
        await session.commit()
    except _ClaimLost:
        await session.rollback()
        await _delete_quietly(storage, object_key, job_id=job_id)
        logger.warning("video_claim_lost job_id=%s stage=complete", job_id[:12])
        try:
            current = await session.scalar(
                select(VideoGenerationJob).where(
                    VideoGenerationJob.id == job_id,
                    VideoGenerationJob.workspace_id == workspace_id,
                )
            )
            if current is not None:
                return current
        except Exception:
            await session.rollback()
            logger.warning("video_claim_reload_failed job_id=%s", job_id[:12], exc_info=True)
        return _detached_storage_failed_job(
            job_id=job_id,
            workspace_id=workspace_id,
            budget_id=budget_id,
            requested_by_user_id=requested_by_user_id,
            provider=provider_name,
            model=model,
            provider_job_id=provider_job_id,
            prompt=prompt,
            negative_prompt=negative_prompt,
            storyboard_json=storyboard_json,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
        )
    except Exception:
        return await _recover_after_storage_failure(
            session,
            storage=storage,
            object_key=object_key,
            token=token,
            job_id=job_id,
            workspace_id=workspace_id,
            budget_id=budget_id,
            requested_by_user_id=requested_by_user_id,
            provider=provider_name,
            model=model,
            provider_job_id=provider_job_id,
            usage_user_id=usage_user_id,
            cost_units=cost_units,
            prompt=prompt,
            negative_prompt=negative_prompt,
            storyboard_json=storyboard_json,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
        )

    await _record_capability_outcome("success")
    await session.refresh(job)
    return job


async def _execute_provider_pending(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    token: str,
    user_id: str | None,
) -> VideoGenerationJob:
    now = _now()
    started = _aware(job.provider_started_at)
    if started is None or now - started > timedelta(
        seconds=settings.video_generation_max_poll_seconds
    ):
        await _terminal(
            session,
            job,
            token=token,
            status="execution_unknown",
            code="execution_unknown",
            message=UNKNOWN_EXECUTION,
            refund=False,
            user_id=user_id,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job
    try:
        provider = await _provider_for_job(job)
        state = await asyncio.wait_for(
            provider.check(job.provider_job_id or ""),
            timeout=settings.video_generation_timeout_seconds,
        )
    except Exception:
        await _release_claim(
            session,
            job,
            token=token,
            status="provider_pending",
            values={
                "last_polled_at": now,
                "provider_status": "check_error",
            },
        )
        await session.refresh(job)
        return job

    provider_status = _safe_provider_status(getattr(state, "provider_status", None), "pending")
    state_failed = bool(getattr(state, "failed", False))
    state_ready = bool(getattr(state, "ready", False))
    state_cost = getattr(state, "cost_units", None)
    if state_failed:
        await _terminal(
            session,
            job,
            token=token,
            status="failed",
            code=_safe_code(getattr(state, "error_code", None), "provider_failed"),
            message=PROVIDER_FAILURE,
            refund=False,
            user_id=user_id,
            cost_units=state_cost,
            record_usage_event=True,
        )
        await session.refresh(job)
        return job
    if state_ready:
        result = await session.execute(
            update(VideoGenerationJob)
            .where(
                VideoGenerationJob.id == job.id,
                VideoGenerationJob.claim_token == token,
                VideoGenerationJob.status == "provider_pending",
            )
            .values(
                status="downloading",
                last_polled_at=now,
                provider_status=provider_status,
            )
            .execution_options(synchronize_session=False)
        )
        if not result.rowcount:
            await session.rollback()
            await session.refresh(job)
            return job
        await session.commit()
        await session.refresh(job)
        return await _execute_downloading(
            session,
            job,
            token=token,
            user_id=user_id,
            cost_units=state_cost if isinstance(state_cost, int) else None,
        )

    await _release_claim(
        session,
        job,
        token=token,
        status="provider_pending",
        values={"last_polled_at": now, "provider_status": provider_status},
    )
    await session.refresh(job)
    return job


async def execute_job(
    session: AsyncSession,
    job: VideoGenerationJob,
    *,
    user_id: str | None = None,
) -> VideoGenerationJob:
    """Advance one claimed job without ever re-submitting a paid request."""

    token = job.claim_token
    if not token:
        logger.warning("video_unclaimed job_id=%s", job.id[:12])
        return job
    if job.status == "preparing":
        return await _execute_preparing(session, job, token=token, user_id=user_id)
    if job.status == "provider_pending":
        return await _execute_provider_pending(session, job, token=token, user_id=user_id)
    if job.status == "downloading":
        return await _execute_downloading(session, job, token=token, user_id=user_id)
    return job


async def _record_capability_outcome(outcome: str) -> None:
    try:
        value = CapabilityOutcome(outcome)
    except ValueError:
        value = CapabilityOutcome.PROVIDER_ERROR
    await get_runtime_capability_registry().record_outcome_for(
        Capability.VIDEO_GENERATION,
        value,
    )


async def run_once(*, batch: int = DEFAULT_BATCH) -> int:
    """Claim and execute up to ``batch`` jobs with one session per job."""

    session_factory = get_session_factory()
    processed = 0
    for _ in range(max(batch, 0)):
        async with session_factory() as session:
            job = await claim_next_job(session)
            if job is None:
                break
            job_id = job.id
            try:
                await execute_job(session, job)
            except Exception:
                await session.rollback()
                logger.warning("video_worker_job_failed job_id=%s", job_id[:12])
        processed += 1
    if processed:
        logger.info("video_worker_processed count=%s", processed)
    return processed


async def run_forever(*, interval: float, batch: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await run_once(batch=batch)
        except Exception:
            logger.warning("video_worker_cycle_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=max(interval, 0))


async def _main(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        await run_once(batch=args.batch)
        return 0
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(getattr(signal, signal_name), stop.set)
    logger.info("video_worker_started interval=%s batch=%s", args.interval, args.batch)
    await run_forever(interval=args.interval, batch=args.batch, stop=stop)
    logger.info("video_worker_stopped")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker durable de generación de video HiTrendy")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--once", action="store_true", help="Procesa un ciclo y termina")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
