"""Application service for image generation.

The flow is deliberately linear and every paid call sits behind the same eight
gates: the capability is enabled, a provider is configured, the model is on the
operator allow-list, the workspace still has budget, a preflight was approved,
the user confirmed explicitly, an idempotency key is present, and a durable job
row was reserved before anything left the process.

Execution happens in an external worker, never in the request that created the
job, so a browser closing or a web process restarting cannot lose or duplicate
work.

Money and the state machine
---------------------------

The one thing this module must never do is pay twice for the same request.
``FOR UPDATE ... SKIP LOCKED`` is not what guarantees that: the row lock ends
the moment the claim commits, and a worker can die at any point afterwards.
What guarantees it is the durable boundary around the provider call:

``queued`` -> ``running`` -> ``provider_started`` -> ``succeeded``/``failed``

Only ``queued`` and stale ``running`` rows are reclaimable, because in those
states the call provably never left. ``provider_started`` is written *and
committed* immediately before the call, so a worker that dies mid-flight leaves
a row that no worker will re-issue; the sweep closes it as ``IMAGE_EXECUTION_
UNKNOWN`` and keeps the unit consumed, since nobody can know whether the
provider charged for it. Inventing a refund there would hand out free credit
on every upstream hiccup.

Every terminal write is fenced by ``claim_token``: a worker that was declared
dead and then wakes up cannot overwrite the outcome another worker (or the
sweep) already recorded.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.assets.validation import enforce_expected_frame, validate_image_bytes
from app.core.capabilities import (
    Capability,
    CapabilityOutcome,
    CapabilityStatus,
    get_runtime_capability_registry,
)
from app.core.config import settings
from app.core.errors import AppError, NotFoundError, ValidationError_
from app.images import budget as budget_ledger
from app.images.brief import (
    VisualBrief,
    compose_negative_prompt,
    compose_prompt,
    normalize_aspect_ratio,
    normalize_brief,
)
from app.images.models import TERMINAL_JOB_STATUSES, ImageGenerationJob
from app.images.signing import (
    PreflightApproval,
    SignedImageUrl,
    request_fingerprint,
    sign_image_url,
    sign_preflight,
    verify_preflight,
)
from app.projects.models import Project
from app.providers.factory import get_image_generation_provider
from app.providers.images import ASPECT_RATIOS, ImageGenerationRequest
from app.providers.storage import get_object_storage_provider
from app.services.ai_usage import outcome_for_error, record_usage

logger = logging.getLogger("hitrendy.images")

#: The only failure text ever persisted or returned for an unmapped error.
GENERIC_FAILURE = "No pudimos generar la imagen. Inténtalo nuevamente."

#: Shown when a worker died after the call left and nobody can say whether it
#: was billed. It is deliberately not an invitation to retry automatically.
UNKNOWN_EXECUTION = (
    "No pudimos confirmar el resultado de esta generación. Revísala antes de reintentar."
)

STORAGE_FAILURE = "No pudimos guardar la imagen generada. Inténtalo nuevamente."

#: Statuses that still allow a generation to be confirmed. ``DEGRADED`` is
#: included on purpose: it reports reduced capacity, not an outage, and a single
#: upstream timeout must not take the whole feature down until the outcome
#: window expires. This matches how trend analysis reads the same registry.
_USABLE_STATUSES = frozenset({CapabilityStatus.AVAILABLE, CapabilityStatus.DEGRADED})


class _ClaimLost(Exception):
    """Another worker or the sweep already decided this job's outcome."""


def _stuck_after() -> timedelta:
    """How long a claim survives without progress before it is taken over.

    Configuration guarantees this is comfortably longer than the provider
    timeout (see ``validate_runtime_configuration``), so a legitimate call in
    flight is never mistaken for a dead worker.
    """

    return timedelta(seconds=settings.image_generation_stuck_after_seconds)


@dataclass(frozen=True)
class PreflightResult:
    """What the user must see before spending anything."""

    allowed: bool
    aspect_ratio: str
    brief: VisualBrief
    prompt_preview: str
    negative_prompt_preview: str | None
    reference_asset_id: str | None
    budget_remaining: int
    budget_total: int
    next_reset_at: datetime
    reason_code: str | None
    message: str | None
    approval: PreflightApproval | None


async def _authorized_reference(
    db: AsyncSession, *, workspace_id: str, reference_asset_id: str | None
) -> Asset | None:
    """Resolve a reference to an asset this workspace already owns.

    External URLs, local paths and inline data are rejected upstream by the
    schema: the only accepted shape is an identifier, and it must resolve
    inside the caller's workspace.
    """

    if not reference_asset_id:
        return None
    asset = await db.scalar(
        select(Asset).where(
            Asset.id == reference_asset_id,
            Asset.workspace_id == workspace_id,
            Asset.asset_type == "image",
        )
    )
    if asset is None:
        raise NotFoundError("Imagen de referencia")
    return asset


async def _authorized_project(
    db: AsyncSession, *, workspace_id: str, project_id: str | None
) -> None:
    """Refuse to attach a generation to a project of another workspace."""

    if not project_id:
        return
    owner = await db.scalar(select(Project.workspace_id).where(Project.id == project_id))
    if owner != workspace_id:
        raise NotFoundError("Publicación")


async def preflight(
    db: AsyncSession,
    *,
    workspace_id: str,
    brief_payload: dict | None,
    aspect_ratio: str | None,
    reference_asset_id: str | None = None,
    now: datetime | None = None,
) -> PreflightResult:
    """Estimate and authorize one generation without calling any provider."""

    moment = now or datetime.now(UTC)
    brief = normalize_brief(brief_payload)
    ratio = normalize_aspect_ratio(aspect_ratio)
    await _authorized_reference(db, workspace_id=workspace_id, reference_asset_id=reference_asset_id)
    prompt = compose_prompt(brief, aspect_ratio=ratio)
    # What the user asked to avoid is shown back explicitly. It reaches the
    # provider, so it has to be part of what is reviewed and of the signature.
    negative_prompt = compose_negative_prompt(brief)
    state = await budget_ledger.read_budget(db, workspace_id=workspace_id, now=moment)

    capability = get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION)
    if capability.status not in _USABLE_STATUSES:
        return PreflightResult(
            allowed=False,
            aspect_ratio=ratio,
            brief=brief,
            prompt_preview=prompt,
            negative_prompt_preview=negative_prompt,
            reference_asset_id=reference_asset_id,
            budget_remaining=state.remaining,
            budget_total=state.budget,
            next_reset_at=state.next_reset_at,
            reason_code=capability.status.value,
            message=capability.message,
            approval=None,
        )
    if state.exhausted:
        return PreflightResult(
            allowed=False,
            aspect_ratio=ratio,
            brief=brief,
            prompt_preview=prompt,
            negative_prompt_preview=negative_prompt,
            reference_asset_id=reference_asset_id,
            budget_remaining=0,
            budget_total=state.budget,
            next_reset_at=state.next_reset_at,
            reason_code=CapabilityStatus.QUOTA_EXHAUSTED.value,
            message="Alcanzaste el límite de imágenes de hoy.",
            approval=None,
        )

    approval = sign_preflight(
        workspace_id=workspace_id,
        request_hash=request_fingerprint(
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=ratio,
            reference_asset_id=reference_asset_id,
        ),
        now=moment,
    )
    return PreflightResult(
        allowed=True,
        aspect_ratio=ratio,
        brief=brief,
        prompt_preview=prompt,
        negative_prompt_preview=negative_prompt,
        reference_asset_id=reference_asset_id,
        budget_remaining=state.remaining,
        budget_total=state.budget,
        next_reset_at=state.next_reset_at,
        reason_code=None,
        message=None,
        approval=approval,
    )


async def create_job(
    db: AsyncSession,
    *,
    workspace_id: str,
    brief_payload: dict | None,
    aspect_ratio: str | None,
    approval_token: str | None,
    confirmed: bool,
    reference_asset_id: str | None = None,
    project_id: str | None = None,
    now: datetime | None = None,
) -> ImageGenerationJob:
    """Reserve budget and enqueue exactly one durable job.

    Nothing is called upstream here. The caller commits, and a worker picks the
    job up: the money is only spent once the row exists.
    """

    moment = now or datetime.now(UTC)
    if not confirmed:
        raise ValidationError_("Confirma la generación antes de continuar.")

    brief = normalize_brief(brief_payload)
    ratio = normalize_aspect_ratio(aspect_ratio)
    await _authorized_reference(db, workspace_id=workspace_id, reference_asset_id=reference_asset_id)
    await _authorized_project(db, workspace_id=workspace_id, project_id=project_id)
    prompt = compose_prompt(brief, aspect_ratio=ratio)
    negative_prompt = compose_negative_prompt(brief)

    verify_preflight(
        workspace_id=workspace_id,
        request_hash=request_fingerprint(
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=ratio,
            reference_asset_id=reference_asset_id,
        ),
        token=approval_token,
        now=moment,
    )

    capability = get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION)
    if capability.status not in _USABLE_STATUSES:
        raise AppError(
            "CAPABILITY_UNAVAILABLE",
            capability.message or "La generación de imágenes no está disponible.",
            status_code=503,
        )

    # The provider is built before the reservation so a misconfiguration fails
    # without touching the ledger. Its identity is what the job stores: the
    # worker will rebuild exactly this route, not whatever is configured later.
    provider = get_image_generation_provider()

    reservation = await budget_ledger.reserve(db, workspace_id=workspace_id, now=moment)
    if reservation is None:
        raise AppError(
            "IMAGE_QUOTA_EXHAUSTED",
            "Alcanzaste el límite de imágenes de hoy.",
            status_code=429,
        )

    job = ImageGenerationJob(
        workspace_id=workspace_id,
        project_id=project_id,
        status="queued",
        aspect_ratio=ratio,
        prompt=prompt,
        negative_prompt=negative_prompt,
        reference_asset_id=reference_asset_id,
        provider=provider.provider_name,
        model=provider.model_name,
        # Which ledger row paid, so a refund on a later UTC day still lands on
        # the period that was actually charged.
        budget_id=reservation.budget_id,
    )
    db.add(job)
    await db.flush()
    return job


def _claimable(now: datetime):
    """Rows whose provider call provably never left this process.

    ``provider_started`` is absent by construction: past that point the money
    may already be gone, and a second call is exactly what must not happen.
    """

    return or_(
        ImageGenerationJob.status == "queued",
        and_(
            ImageGenerationJob.status == "running",
            ImageGenerationJob.started_at.is_not(None),
            ImageGenerationJob.started_at <= now - _stuck_after(),
        ),
    )


async def sweep_unaccounted_calls(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Close jobs whose worker died after the call left, without re-issuing.

    The outcome is genuinely unknown: the provider may have completed and
    billed, or never received it. So the job becomes terminal with a distinct
    code, the reservation stays consumed, and no worker ever picks it up again.
    A user who wants another image confirms a new one, and pays for it.
    """

    moment = now or datetime.now(UTC)
    result = await db.execute(
        update(ImageGenerationJob)
        .where(
            ImageGenerationJob.status == "provider_started",
            ImageGenerationJob.provider_started_at.is_not(None),
            ImageGenerationJob.provider_started_at <= moment - _stuck_after(),
        )
        .values(
            status="failed",
            completed_at=moment,
            last_error_code="IMAGE_EXECUTION_UNKNOWN",
            last_error=UNKNOWN_EXECUTION,
            # Dropping the token fences the original worker out for good.
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    swept = int(result.rowcount or 0)
    await db.commit()
    if swept:
        logger.warning("image_generation_unaccounted swept=%s", swept)
    return swept


async def claim_next_job(db: AsyncSession) -> ImageGenerationJob | None:
    """Atomically take ownership of one claimable job.

    ``FOR UPDATE ... SKIP LOCKED`` keeps two workers from claiming the same row
    at the same instant, but it says nothing about the minutes that follow: the
    lock is released when this commits. Ownership from here on is carried by
    ``claim_token``, which every terminal write checks.
    """

    now = datetime.now(UTC)
    await sweep_unaccounted_calls(db, now=now)

    job = await db.scalar(
        select(ImageGenerationJob)
        .where(_claimable(now))
        .order_by(ImageGenerationJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        await db.rollback()
        return None
    if job.attempt_count >= settings.image_generation_max_attempts:
        job.status = "failed"
        job.completed_at = now
        job.last_error_code = "IMAGE_MAX_ATTEMPTS"
        job.last_error = GENERIC_FAILURE
        job.claim_token = None
        # Only refundable because this row is claimable, and a claimable row is
        # one whose call never left. Anything past the boundary is never here.
        if job.provider_started_at is None and job.budget_id:
            await budget_ledger.release(db, budget_id=job.budget_id)
        await db.commit()
        return None
    job.status = "running"
    job.started_at = now
    job.attempt_count += 1
    job.claim_token = uuid.uuid4().hex
    job.last_error = None
    job.last_error_code = None
    await db.commit()
    return job


async def execute_job(
    db: AsyncSession, job: ImageGenerationJob, *, user_id: str | None = None
) -> ImageGenerationJob:
    """Generate, validate and store the image for a job this worker claimed."""

    job_id = job.id
    workspace_id = job.workspace_id
    token = job.claim_token
    if not token:
        # Without a token no terminal write could be attributed to this worker,
        # so there is nothing safe to do here.
        logger.warning("image_generation_unclaimed job_id=%s", job_id)
        return job

    # --- Preparation. Nothing has left the process, so a failure here is fully
    # refundable: the workspace gets its unit back.
    try:
        # The route the job recorded, re-authorized: a model removed from the
        # allow-list after confirmation fails here, before any spend.
        provider = get_image_generation_provider(provider=job.provider, model=job.model)
        await _authorized_project(db, workspace_id=workspace_id, project_id=job.project_id)
        reference = await _reference_bytes(db, job)
        width, height = ASPECT_RATIOS[job.aspect_ratio]
        request = ImageGenerationRequest(
            prompt=job.prompt,
            aspect_ratio=job.aspect_ratio,
            width=width,
            height=height,
            negative_prompt=job.negative_prompt,
            reference_image=reference[0] if reference else None,
            reference_mime_type=reference[1] if reference else None,
        )
    except AppError as error:
        logger.warning("image_generation_unprepared job_id=%s code=%s", job_id, error.code)
        return await _fail(
            db, job, token=token, code=error.code, message=error.message, refund=True
        )
    except Exception:
        logger.warning("image_generation_unprepared job_id=%s code=%s", job_id, "UNEXPECTED")
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_PREPARATION_FAILED",
            message=GENERIC_FAILURE,
            refund=True,
        )

    # --- The paid boundary. Committed before the call, so a crash one line
    # later is still visible as "we may have been charged for this".
    if not await _mark_provider_started(db, job, token=token):
        logger.warning("image_generation_claim_lost job_id=%s stage=%s", job_id, "start")
        await db.refresh(job)
        return job

    try:
        generated = await provider.generate(request=request)
    except AppError as error:
        # The call was attempted, so the reservation stays consumed: a provider
        # failure after billing is not the workspace's credit to reclaim.
        logger.warning("image_generation_failed job_id=%s code=%s", job_id, error.code)
        outcome = outcome_for_error(error)
        await _record(db, job=job, user_id=user_id, metadata=None, outcome=outcome)
        await _record_capability_outcome(outcome)
        return await _fail(
            db, job, token=token, code=error.code, message=error.message, refund=False
        )
    except Exception:
        # Never log the exception payload: it can carry provider secrets.
        logger.warning("image_generation_failed job_id=%s code=%s", job_id, "UNEXPECTED")
        await _record_capability_outcome("provider_error")
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_PROVIDER_ERROR",
            message=GENERIC_FAILURE,
            refund=False,
        )

    # --- Everything below is post-provider: terminal, never refunded, never
    # retried. The unit is spent whether or not we manage to deliver it.
    try:
        metadata = validate_image_bytes(
            generated.content,
            generated.mime_type,
            max_bytes=settings.image_generation_max_bytes,
            size_message="La imagen generada supera el tamaño permitido.",
        )
        # A square answer to a 9:16 job is not the image that was approved.
        enforce_expected_frame(metadata, width=width, height=height)
    except AppError:
        logger.warning("image_generation_rejected job_id=%s", job_id)
        await _record(
            db,
            job=job,
            user_id=user_id,
            metadata=generated.usage_metadata,
            outcome="invalid_response",
        )
        await _record_capability_outcome("invalid_response")
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_PROVIDER_INVALID_RESPONSE",
            message="No recibimos una imagen válida. Inténtalo nuevamente.",
            refund=False,
        )

    if generated.provider_name != job.provider or generated.model != job.model:
        # The bytes came from somewhere other than the route the user's
        # confirmation recorded. Storing them would misattribute the spend.
        logger.warning("image_generation_route_mismatch job_id=%s", job_id)
        await _record(
            db,
            job=job,
            user_id=user_id,
            metadata=generated.usage_metadata,
            outcome="invalid_response",
        )
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_ROUTE_MISMATCH",
            message="No pudimos verificar el modelo que generó la imagen.",
            refund=False,
        )

    object_key = f"workspaces/{workspace_id}/generated/{job_id}{metadata.extension}"
    storage = get_object_storage_provider()
    try:
        await storage.put(
            key=object_key, content=generated.content, content_type=metadata.mime_type
        )
    except Exception:
        # A full disk is not a reason to buy the image again. The spend is
        # recorded, the job is closed, and no worker will reclaim it.
        logger.warning("image_generation_storage_failed job_id=%s stage=%s", job_id, "put")
        await _record(
            db, job=job, user_id=user_id, metadata=generated.usage_metadata, outcome="success"
        )
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_STORAGE_ERROR",
            message=STORAGE_FAILURE,
            refund=False,
        )

    try:
        asset = Asset(
            workspace_id=workspace_id,
            original_name=f"imagen-{job_id[:8]}{metadata.extension}",
            storage_path=object_key,
            mime_type=metadata.mime_type,
            file_size_bytes=len(generated.content),
            asset_type="image",
            width=metadata.width,
            height=metadata.height,
        )
        db.add(asset)
        await db.flush()
        completed = await db.execute(
            update(ImageGenerationJob)
            .where(
                ImageGenerationJob.id == job_id,
                ImageGenerationJob.claim_token == token,
                ImageGenerationJob.status == "provider_started",
            )
            .values(
                status="succeeded",
                asset_id=asset.id,
                completed_at=datetime.now(UTC),
                last_error=None,
                last_error_code=None,
                claim_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        if not completed.rowcount:
            raise _ClaimLost()
        await _record(
            db, job=job, user_id=user_id, metadata=generated.usage_metadata, outcome="success"
        )
        await db.commit()
    except _ClaimLost:
        # Someone already decided this job. Leave their verdict alone and take
        # the now-unreferenced object with us.
        await db.rollback()
        await _delete_quietly(storage, object_key)
        logger.warning("image_generation_claim_lost job_id=%s stage=%s", job_id, "complete")
        await db.refresh(job)
        return job
    except Exception:
        await db.rollback()
        await _delete_quietly(storage, object_key)
        logger.warning("image_generation_storage_failed job_id=%s stage=%s", job_id, "persist")
        # A rollback expires every instance; reload before reading the job.
        await db.refresh(job)
        return await _fail(
            db,
            job,
            token=token,
            code="IMAGE_STORAGE_ERROR",
            message=STORAGE_FAILURE,
            refund=False,
        )

    await _record_capability_outcome("success")
    await db.refresh(job)
    return job


async def _mark_provider_started(
    db: AsyncSession, job: ImageGenerationJob, *, token: str
) -> bool:
    """Durably record that a paid call is about to be made, and commit.

    Returning ``False`` means this worker no longer owns the job -- its claim
    expired and someone else took over -- so it must not call the provider.
    """

    result = await db.execute(
        update(ImageGenerationJob)
        .where(
            ImageGenerationJob.id == job.id,
            ImageGenerationJob.claim_token == token,
            ImageGenerationJob.status == "running",
        )
        .values(status="provider_started", provider_started_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if not result.rowcount:
        return False
    await db.refresh(job)
    return True


async def _delete_quietly(storage, key: str) -> None:
    """Best-effort compensation: an orphan object is better than a failed close."""

    try:
        await storage.delete(key=key)
    except Exception:  # pragma: no cover - the purge sweeps the prefix anyway
        logger.warning("image_generation_orphan_object key_suffix=%s", key[-16:])


async def _reference_bytes(
    db: AsyncSession, job: ImageGenerationJob
) -> tuple[bytes, str] | None:
    """Load the reference image, or refuse to generate without it.

    A job that recorded a reference was approved *with* that reference. If it
    was deleted, moved out of the workspace or is no longer a usable image,
    generating anyway would produce something the user never confirmed, on
    their budget. So this fails before the provider, and the unit goes back.
    """

    if not job.reference_asset_id:
        return None
    asset = await db.scalar(
        select(Asset).where(
            Asset.id == job.reference_asset_id,
            Asset.workspace_id == job.workspace_id,
            Asset.asset_type == "image",
        )
    )
    if asset is None:
        raise _reference_unavailable()
    try:
        content = await get_object_storage_provider().read(key=asset.storage_path)
    except Exception as exc:
        raise _reference_unavailable() from exc
    metadata = validate_image_bytes(
        content,
        asset.mime_type,
        max_bytes=settings.image_generation_max_bytes,
        size_message="La imagen de referencia supera el tamaño permitido.",
    )
    return content, metadata.mime_type


def _reference_unavailable() -> AppError:
    return AppError(
        "IMAGE_REFERENCE_UNAVAILABLE",
        "La imagen de referencia ya no está disponible. Vuelve a elegirla.",
        status_code=409,
        retryable=False,
    )


async def _record_capability_outcome(outcome: str) -> None:
    """Report the last provider result to the capability registry.

    This is a transient signal, not a verdict: it degrades the reported status
    until the next successful generation clears it, and it never touches the
    configured base state, so a single ``402`` cannot leave the capability
    permanently down. An unknown outcome degrades to ``provider_error`` rather
    than raising, because reporting must never break the job itself.
    """

    try:
        value = CapabilityOutcome(outcome)
    except ValueError:  # pragma: no cover - defensive
        value = CapabilityOutcome.PROVIDER_ERROR
    await get_runtime_capability_registry().record_outcome_for(
        Capability.IMAGE_GENERATION, value
    )


async def _record(
    db: AsyncSession,
    *,
    job: ImageGenerationJob,
    user_id: str | None,
    metadata: dict | None,
    outcome: str,
) -> None:
    if not user_id:
        return
    await record_usage(
        db,
        workspace_id=job.workspace_id,
        user_id=user_id,
        capability=Capability.IMAGE_GENERATION.value,
        quality_level="standard",
        provider=job.provider,
        requested_model=job.model,
        metadata=metadata,
        outcome=outcome,
    )


async def _fail(
    db: AsyncSession,
    job: ImageGenerationJob,
    *,
    token: str,
    code: str,
    message: str,
    refund: bool,
) -> ImageGenerationJob:
    """Close a job as failed, but only if this worker still owns it.

    The guard is what stops a worker that was declared dead, and then woke up,
    from overwriting a terminal state someone else already wrote -- and from
    refunding a unit that was never its to refund.
    """

    budget_id = job.budget_id
    result = await db.execute(
        update(ImageGenerationJob)
        .where(
            ImageGenerationJob.id == job.id,
            ImageGenerationJob.claim_token == token,
            ImageGenerationJob.status.not_in(TERMINAL_JOB_STATUSES),
        )
        .values(
            status="failed",
            completed_at=datetime.now(UTC),
            last_error_code=code[:64],
            last_error=message[:300],
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    won = bool(result.rowcount)
    if won and refund and budget_id:
        await budget_ledger.release(db, budget_id=budget_id)
    await db.commit()
    if not won:
        logger.warning("image_generation_claim_lost job_id=%s stage=%s", job.id, "fail")
    await db.refresh(job)
    return job


async def get_job(
    db: AsyncSession, *, workspace_id: str, job_id: str
) -> ImageGenerationJob:
    job = await db.scalar(
        select(ImageGenerationJob).where(
            ImageGenerationJob.id == job_id,
            ImageGenerationJob.workspace_id == workspace_id,
        )
    )
    if job is None:
        raise NotFoundError("Generación de imagen")
    return job


async def latest_job(
    db: AsyncSession, *, workspace_id: str, project_id: str
) -> ImageGenerationJob | None:
    """The most recent generation for one project of *this* workspace.

    This is what a reloaded page reads to find work already in flight, so it is
    scoped by workspace as well as project: a guessed project id must never
    surface another tenant's generation.
    """

    return await db.scalar(
        select(ImageGenerationJob)
        .where(
            ImageGenerationJob.workspace_id == workspace_id,
            ImageGenerationJob.project_id == project_id,
        )
        .order_by(ImageGenerationJob.created_at.desc())
        .limit(1)
    )


def signed_url_for(job: ImageGenerationJob) -> SignedImageUrl | None:
    """Mint a fresh temporary link each time a succeeded job is read."""

    if job.status != "succeeded" or not job.asset_id:
        return None
    return sign_image_url(asset_id=job.asset_id, workspace_id=job.workspace_id)
