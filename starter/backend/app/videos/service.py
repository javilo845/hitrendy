"""Application service for bounded asynchronous video generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.assets.validation import validate_image_bytes
from app.conversations.idempotency import payload_fingerprint, reserve
from app.conversations.models import IdempotencyRecord
from app.conversations.repository import SqlBusinessContextRepository
from app.core.capabilities import (
    Capability,
    CapabilityStatus,
    get_runtime_capability_registry,
)
from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError_
from app.projects.models import Project
from app.providers.storage import get_object_storage_provider
from app.videos import budget as budget_ledger
from app.videos import signing
from app.videos.models import VideoGenerationJob
from app.videos.schemas import (
    VideoJobCreate,
    VideoJobPublic,
    VideoPreflightRequest,
    VideoPreflightResponse,
    VideoStoryboardDraft,
)
from app.videos.storyboard import compose_prompt
from app.videos.storyboard import draft_storyboard as build_storyboard

_CREATE_ENDPOINT = "POST:/videos/jobs"
_USABLE_STATUSES = frozenset({CapabilityStatus.AVAILABLE, CapabilityStatus.DEGRADED})
_APPROVAL_SEPARATOR = "."


def _capability_payload() -> dict[str, object]:
    info = get_runtime_capability_registry().get_capability(Capability.VIDEO_GENERATION)
    payload: dict[str, object] = {
        "status": info.status.value,
        "tier": info.tier.value,
        "quality_levels": [level.value for level in info.quality_levels],
    }
    if info.message is not None:
        payload["message"] = info.message
    if info.next_reset_at is not None:
        payload["next_reset_at"] = info.next_reset_at
    if info.fallback is not None:
        payload["fallback"] = info.fallback
    return payload


def _invalid_preflight(
    message: str = "El preflight ya no es válido. Vuelve a revisarlo.",
) -> AppError:
    return AppError("preflight_invalid", message, status_code=409)


def _capability_unavailable(message: str | None = None) -> AppError:
    return AppError(
        "capability_unavailable",
        message or "La generación de video no está disponible.",
        status_code=409,
    )


def _idempotency_payload(payload: VideoPreflightRequest) -> dict[str, object]:
    return {
        "storyboard": payload.storyboard.model_dump(mode="json"),
        "prompt": payload.prompt,
        "negative_prompt": payload.negative_prompt,
        "duration_seconds": payload.duration_seconds,
        "source_asset_id": payload.source_asset_id,
        "project_id": payload.project_id,
    }


def _request_fingerprint(payload: VideoPreflightRequest) -> str:
    return signing.request_fingerprint(
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        storyboard=payload.storyboard,
        aspect_ratio=payload.storyboard.aspect_ratio,
        duration_seconds=payload.duration_seconds,
        source_asset_id=payload.source_asset_id,
        project_id=payload.project_id,
    )


def _preflight_token(*, fingerprint: str, workspace_id: str, expires_at: datetime) -> str:
    """Carry the signed expiry because the B1 signer intentionally returns a raw MAC."""

    signature = signing.sign_preflight(fingerprint, workspace_id, expires_at)
    return f"{int(expires_at.timestamp())}{_APPROVAL_SEPARATOR}{signature}"


def _verify_preflight_token(
    *, fingerprint: str, workspace_id: str, token: str, now: datetime
) -> None:
    try:
        raw_expires, signature = token.split(_APPROVAL_SEPARATOR, 1)
        expires_at = int(raw_expires)
        if not signature:
            raise ValueError("missing signature")
    except (AttributeError, TypeError, ValueError) as exc:
        raise _invalid_preflight() from exc
    try:
        signing.verify_preflight(
            fingerprint,
            workspace_id,
            expires_at,
            signature,
            now=now,
        )
    except AppError as exc:
        raise _invalid_preflight() from exc


async def _authorized_project(
    session: AsyncSession, *, workspace_id: str, project_id: str | None
) -> None:
    if not project_id:
        return
    project = await session.scalar(
        select(Project.id).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    if project is None:
        raise NotFoundError("Proyecto")


async def _authorized_source_asset(
    session: AsyncSession,
    *,
    workspace_id: str,
    source_asset_id: str | None,
    validate_bytes: bool,
) -> Asset | None:
    if not source_asset_id:
        return None
    asset = await session.scalar(
        select(Asset).where(
            Asset.id == source_asset_id,
            Asset.workspace_id == workspace_id,
            Asset.asset_type == "image",
        )
    )
    if asset is None:
        raise NotFoundError("Imagen de origen")
    if not validate_bytes:
        return asset

    try:
        content = await get_object_storage_provider().read(key=asset.storage_path)
        validate_image_bytes(content, asset.mime_type)
    except Exception as exc:
        raise AppError(
            "source_asset_invalid",
            "La imagen de origen ya no está disponible o no es válida.",
            status_code=409,
        ) from exc
    return asset


def _validate_request_shape(payload: VideoPreflightRequest) -> None:
    if payload.storyboard.aspect_ratio != "9:16":
        raise _invalid_preflight("El video debe usar el formato vertical 9:16.")
    if payload.storyboard.duration_seconds != payload.duration_seconds:
        raise _invalid_preflight("La duración del storyboard y de la solicitud no coincide.")


def _duration_reason(duration_seconds: int) -> tuple[str, str] | None:
    if duration_seconds not in settings.video_generation_allowed_durations:
        allowed = ", ".join(str(item) for item in settings.video_generation_allowed_durations)
        return (
            "duration_not_allowed",
            f"Elige una duración permitida: {allowed} segundos.",
        )
    return None


async def draft_storyboard(
    session: AsyncSession,
    *,
    workspace_id: str,
    business_id: str,
    publication_text: str | None,
    trend_title: str | None,
    duration_seconds: int | None,
) -> VideoStoryboardDraft:
    """Draft an editable storyboard without spending or contacting a provider."""

    duration = (
        duration_seconds
        if duration_seconds is not None
        else settings.video_generation_allowed_durations[0]
    )
    duration_reason = _duration_reason(duration)
    if duration_reason is not None:
        raise ValidationError_(duration_reason[1])

    context = await SqlBusinessContextRepository(session).get_for_generation(
        workspace_id=workspace_id,
        business_id=business_id,
    )
    storyboard = build_storyboard(
        context=context,
        publication_text=publication_text,
        trend_title=trend_title,
        duration_seconds=duration,
    )
    prompt, negative_prompt = compose_prompt(storyboard, context)
    budget = await budget_ledger.view(session, workspace_id)
    return VideoStoryboardDraft(
        storyboard=storyboard,
        prompt_preview=prompt,
        negative_prompt_preview=negative_prompt,
        allowed_durations=list(settings.video_generation_allowed_durations),
        aspect_ratio="9:16",
        budget=budget,
        capability=_capability_payload(),
    )


async def preflight(
    session: AsyncSession,
    *,
    workspace_id: str,
    payload: VideoPreflightRequest,
) -> VideoPreflightResponse:
    """Validate one exact request and issue a short-lived approval, never reserve."""

    _validate_request_shape(payload)
    await _authorized_project(session, workspace_id=workspace_id, project_id=payload.project_id)
    await _authorized_source_asset(
        session,
        workspace_id=workspace_id,
        source_asset_id=payload.source_asset_id,
        validate_bytes=True,
    )

    budget = await budget_ledger.view(session, workspace_id)
    capability = get_runtime_capability_registry().get_capability(Capability.VIDEO_GENERATION)
    duration_reason = _duration_reason(payload.duration_seconds)
    if duration_reason is not None:
        reason_code, message = duration_reason
        return VideoPreflightResponse(
            allowed=False,
            aspect_ratio="9:16",
            duration_seconds=payload.duration_seconds,
            storyboard=payload.storyboard,
            prompt_preview=payload.prompt,
            negative_prompt_preview=payload.negative_prompt,
            source_asset_id=payload.source_asset_id,
            estimated_units=1,
            budget=budget,
            reason_code=reason_code,
            message=message,
            capability=_capability_payload(),
        )
    if capability.status not in _USABLE_STATUSES:
        return VideoPreflightResponse(
            allowed=False,
            aspect_ratio="9:16",
            duration_seconds=payload.duration_seconds,
            storyboard=payload.storyboard,
            prompt_preview=payload.prompt,
            negative_prompt_preview=payload.negative_prompt,
            source_asset_id=payload.source_asset_id,
            estimated_units=1,
            budget=budget,
            reason_code=capability.status.value,
            message=capability.message or "La generación de video no está disponible.",
            capability=_capability_payload(),
        )
    if budget.remaining <= 0:
        return VideoPreflightResponse(
            allowed=False,
            aspect_ratio="9:16",
            duration_seconds=payload.duration_seconds,
            storyboard=payload.storyboard,
            prompt_preview=payload.prompt,
            negative_prompt_preview=payload.negative_prompt,
            source_asset_id=payload.source_asset_id,
            estimated_units=1,
            budget=budget,
            reason_code="quota_exhausted",
            message="Alcanzaste el límite de videos de hoy.",
            capability=_capability_payload(),
        )

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.video_preflight_ttl_seconds)
    fingerprint = _request_fingerprint(payload)
    approval_token = _preflight_token(
        fingerprint=fingerprint,
        workspace_id=workspace_id,
        expires_at=expires_at,
    )
    return VideoPreflightResponse(
        allowed=True,
        aspect_ratio="9:16",
        duration_seconds=payload.duration_seconds,
        storyboard=payload.storyboard,
        prompt_preview=payload.prompt,
        negative_prompt_preview=payload.negative_prompt,
        source_asset_id=payload.source_asset_id,
        estimated_units=1,
        budget=budget,
        approval_token=approval_token,
        approval_expires_at=expires_at,
        capability=_capability_payload(),
    )


async def _job_from_idempotency_record(
    session: AsyncSession,
    *,
    workspace_id: str,
    record: IdempotencyRecord,
) -> VideoGenerationJob:
    if not record.response_json:
        raise AppError(
            "idempotency_conflict",
            "La solicitud ya está en proceso. Inténtalo nuevamente en un momento.",
            status_code=409,
            retryable=True,
        )
    try:
        response = json.loads(record.response_json)
        job_id = response["id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            "idempotency_conflict",
            "No pudimos recuperar la solicitud anterior.",
            status_code=409,
        ) from exc
    job = await session.scalar(
        select(VideoGenerationJob).where(
            VideoGenerationJob.id == job_id,
            VideoGenerationJob.workspace_id == workspace_id,
        )
    )
    if job is None:
        raise AppError(
            "idempotency_conflict",
            "No pudimos recuperar la solicitud anterior.",
            status_code=409,
        )
    return job


async def create_job(
    session: AsyncSession,
    *,
    workspace_id: str,
    payload: VideoJobCreate,
    idempotency_key: str,
    requested_by_user_id: str,
) -> VideoGenerationJob:
    """Reserve one unit and enqueue one job in the caller's transaction."""

    if payload.confirmed is not True:
        raise ValidationError_("Confirma la generación antes de continuar.")
    _validate_request_shape(payload)
    if _duration_reason(payload.duration_seconds) is not None:
        raise _invalid_preflight("La duración solicitada no fue aprobada en el preflight.")

    now = datetime.now(UTC)
    fingerprint = _request_fingerprint(payload)
    _verify_preflight_token(
        fingerprint=fingerprint,
        workspace_id=workspace_id,
        token=payload.approval_token,
        now=now,
    )
    await _authorized_project(session, workspace_id=workspace_id, project_id=payload.project_id)
    await _authorized_source_asset(
        session,
        workspace_id=workspace_id,
        source_asset_id=payload.source_asset_id,
        validate_bytes=False,
    )

    capability = get_runtime_capability_registry().get_capability(Capability.VIDEO_GENERATION)
    if capability.status not in _USABLE_STATUSES:
        raise _capability_unavailable(capability.message)

    idempotency_hash = payload_fingerprint(_idempotency_payload(payload))
    try:
        record = await reserve(
            session,
            workspace_id=workspace_id,
            endpoint=_CREATE_ENDPOINT,
            key=idempotency_key,
            payload_hash=idempotency_hash,
            commit=False,
        )
    except ConflictError as exc:
        raise AppError(
            "idempotency_conflict",
            exc.message,
            status_code=409,
            retryable=exc.retryable,
        ) from exc
    if record is not None and record.status == "completed":
        return await _job_from_idempotency_record(
            session,
            workspace_id=workspace_id,
            record=record,
        )

    try:
        reservation = await budget_ledger.reserve(session, workspace_id, now=now)
    except budget_ledger.VideoQuotaExceeded as exc:
        raise AppError(
            "quota_exhausted",
            "Alcanzaste el límite de videos de hoy.",
            status_code=429,
        ) from exc

    job = VideoGenerationJob(
        workspace_id=workspace_id,
        project_id=payload.project_id,
        status="queued",
        provider=settings.video_provider,
        model=settings.video_generation_model or None,
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        storyboard_json=json.dumps(
            payload.storyboard.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        source_asset_id=payload.source_asset_id,
        aspect_ratio=payload.storyboard.aspect_ratio,
        duration_seconds=payload.duration_seconds,
        budget_id=reservation.id,
        requested_by_user_id=requested_by_user_id,
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, *, workspace_id: str, job_id: str) -> VideoGenerationJob:
    job = await session.scalar(
        select(VideoGenerationJob).where(
            VideoGenerationJob.id == job_id,
            VideoGenerationJob.workspace_id == workspace_id,
        )
    )
    if job is None:
        raise NotFoundError("Generación de video")
    return job


async def latest_job(
    session: AsyncSession, *, workspace_id: str, project_id: str
) -> VideoGenerationJob | None:
    return await session.scalar(
        select(VideoGenerationJob)
        .where(
            VideoGenerationJob.workspace_id == workspace_id,
            VideoGenerationJob.project_id == project_id,
        )
        .order_by(VideoGenerationJob.created_at.desc())
        .limit(1)
    )


def to_public(job: VideoGenerationJob, *, include_url: bool) -> VideoJobPublic:
    video_url: str | None = None
    video_expires_at: datetime | None = None
    if include_url and job.status == "succeeded" and job.asset_id:
        video_expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.video_signed_url_ttl_seconds
        )
        expires = int(video_expires_at.timestamp())
        signature = signing.sign_video_url(job.asset_id, job.workspace_id, video_expires_at)
        video_url = (
            f"{settings.api_prefix}/videos/files/{job.asset_id}"
            f"?workspace={job.workspace_id}&expires={expires}&signature={signature}"
        )
    return VideoJobPublic(
        id=job.id,
        status=job.status,
        aspect_ratio=job.aspect_ratio,
        duration_seconds=job.duration_seconds,
        source_asset_id=job.source_asset_id,
        asset_id=job.asset_id,
        video_url=video_url,
        video_expires_at=video_expires_at,
        created_at=job.created_at,
        completed_at=job.completed_at,
        safe_error=job.last_error,
        safe_error_code=job.last_error_code,
    )


__all__ = [
    "create_job",
    "draft_storyboard",
    "get_job",
    "latest_job",
    "preflight",
    "to_public",
]
