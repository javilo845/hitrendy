"""HTTP surface for image generation.

Four steps, in this order and no other: draft the brief, preflight it, confirm
it, then poll the durable job. A fifth endpoint serves the finished file to a
signature, not to a session, so an ``<img src>`` works without leaking the
session cookie into the storage layer.

What the client may choose is deliberately small: the brief text, one of three
formats, and optionally one asset it already owns. The model, the provider and
the spending limits belong to the server.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.conversations.idempotency import (
    complete,
    payload_fingerprint,
    recover_failed,
    reserve,
)
from app.business.models import Business
from app.conversations.repository import SqlBusinessContextRepository
from app.core.capabilities import Capability, get_runtime_capability_registry
from app.core.errors import AppError, NotFoundError
from app.dependencies import get_db, require_workspace
from app.images import budget as budget_ledger
from app.images import service as image_service
from app.images.brief import FIELD_LIMITS, draft_brief
from app.images.models import ImageGenerationJob
from app.images.signing import invalid_image_link, verify_image_url
from app.providers.images import ASPECT_RATIOS
from app.providers.storage import get_object_storage_provider

router = APIRouter(prefix="/images", tags=["images"])

_CREATE_ENDPOINT = "POST:/images/jobs"

#: Identifiers are opaque server-generated tokens. The pattern is what keeps a
#: URL, a local path, a ``file://`` scheme or a data URL out of every field
#: that could name a reference image.
_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class BriefModel(BaseModel):
    subject: str | None = Field(None, max_length=FIELD_LIMITS["subject"])
    setting: str | None = Field(None, max_length=FIELD_LIMITS["setting"])
    style: str | None = Field(None, max_length=FIELD_LIMITS["style"])
    palette: str | None = Field(None, max_length=FIELD_LIMITS["palette"])
    mood: str | None = Field(None, max_length=FIELD_LIMITS["mood"])
    avoid: str | None = Field(None, max_length=FIELD_LIMITS["avoid"])


class DraftBriefRequest(BaseModel):
    business_id: str = Field(pattern=_ID_PATTERN)
    publication_text: str | None = Field(None, max_length=4000)
    trend_title: str | None = Field(None, max_length=300)


class PreflightRequest(BaseModel):
    brief: BriefModel
    aspect_ratio: str = Field(max_length=8)
    reference_asset_id: str | None = Field(None, pattern=_ID_PATTERN)


class CreateJobRequest(BaseModel):
    brief: BriefModel
    aspect_ratio: str = Field(max_length=8)
    reference_asset_id: str | None = Field(None, pattern=_ID_PATTERN)
    approval_token: str = Field(max_length=200)
    confirmed: bool = False
    project_id: str | None = Field(None, pattern=_ID_PATTERN)


def _capability_dict() -> dict:
    info = get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION)
    return {
        "status": info.status.value,
        "tier": info.tier.value,
        "message": info.message,
        "fallback": info.fallback,
    }


def _budget_dict(state: budget_ledger.ImageBudgetState) -> dict:
    return {
        "remaining": state.remaining,
        "total": state.budget,
        "next_reset_at": state.next_reset_at.isoformat(),
    }


def _job_response(job: ImageGenerationJob, *, include_url: bool) -> dict:
    """Serialize a job.

    ``include_url`` is off wherever the payload may be persisted: a signed URL
    is derived on every read and must never be stored, not even inside an
    idempotency replay. The provider, the model and the composed prompt are not
    part of this contract either.
    """

    payload = {
        "id": job.id,
        "status": job.status,
        "aspect_ratio": job.aspect_ratio,
        "asset_id": job.asset_id,
        "reference_asset_id": job.reference_asset_id,
        "error": job.last_error,
        "error_code": job.last_error_code,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if include_url:
        signed = image_service.signed_url_for(job)
        payload["image_url"] = signed.url if signed else None
        payload["image_expires_at"] = signed.expires_at.isoformat() if signed else None
    return payload


@router.post("/brief")
async def draft_image_brief(
    body: DraftBriefRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Propose an editable visual brief. Never calls a provider, never spends.

    This endpoint answers even when the capability is unavailable: the brief is
    itself the documented fallback, so the user always leaves with something
    they can hand to a designer.
    """

    if body.business_id:
        biz_exists = await db.scalar(
            select(Business.id).where(
                Business.id == body.business_id,
                Business.workspace_id == workspace_id,
            )
        )
        if not biz_exists:
            raise NotFoundError("Negocio")

    context = await SqlBusinessContextRepository(db).get_for_generation(
        workspace_id=workspace_id, business_id=body.business_id
    )
    brief = draft_brief(
        context=context,
        publication_text=body.publication_text,
        trend_title=body.trend_title,
    )
    state = await budget_ledger.read_budget(db, workspace_id=workspace_id)
    await db.commit()
    return {
        "brief": brief.to_dict(),
        "aspect_ratios": list(ASPECT_RATIOS),
        "capability": _capability_dict(),
        "budget": _budget_dict(state),
    }


@router.post("/preflight")
async def preflight_image(
    body: PreflightRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Show exactly what will be generated and what it will cost, then approve.

    The approval it returns is a short-lived signature over this precise brief,
    format and reference. Editing any of them invalidates it.
    """

    result = await image_service.preflight(
        db,
        workspace_id=workspace_id,
        brief_payload=body.brief.model_dump(),
        aspect_ratio=body.aspect_ratio,
        reference_asset_id=body.reference_asset_id,
    )
    await db.commit()
    return {
        "allowed": result.allowed,
        "aspect_ratio": result.aspect_ratio,
        "brief": result.brief.to_dict(),
        "prompt_preview": result.prompt_preview,
        # Shown separately because it is phrased as an exclusion, not as part of
        # the scene. It still travels to the provider and is still signed, so
        # the user reviews everything that will shape the result.
        "negative_prompt_preview": result.negative_prompt_preview,
        "reference_asset_id": result.reference_asset_id,
        "budget": {
            "remaining": result.budget_remaining,
            "total": result.budget_total,
            "next_reset_at": result.next_reset_at.isoformat(),
        },
        "reason_code": result.reason_code,
        "message": result.message,
        "approval_token": result.approval.token if result.approval else None,
        "approval_expires_at": (
            result.approval.expires_at.isoformat() if result.approval else None
        ),
        "capability": _capability_dict(),
    }


@router.post("/jobs", status_code=202)
async def create_image_job(
    body: CreateJobRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirm the generation and enqueue one durable job.

    No provider is reached here. The request returns as soon as the row and the
    budget reservation are committed, and a separate worker does the work, so
    the spend survives a browser closing and never happens twice.
    """

    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Falta la clave de idempotencia de la solicitud.",
            status_code=400,
        )

    brief_payload = body.brief.model_dump()
    payload_hash = payload_fingerprint(
        {
            "brief": brief_payload,
            "aspect_ratio": body.aspect_ratio,
            "reference_asset_id": body.reference_asset_id,
            "project_id": body.project_id,
        }
    )
    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=_CREATE_ENDPOINT,
        key=idempotency_key,
        payload_hash=payload_hash,
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)

    try:
        job = await image_service.create_job(
            db,
            workspace_id=workspace_id,
            brief_payload=brief_payload,
            aspect_ratio=body.aspect_ratio,
            approval_token=body.approval_token,
            confirmed=body.confirmed,
            reference_asset_id=body.reference_asset_id,
            project_id=body.project_id,
        )
        await db.commit()
    except Exception:
        # Leave the key retryable: nothing was spent if we never got here.
        await recover_failed(
            db,
            workspace_id=workspace_id,
            endpoint=_CREATE_ENDPOINT,
            key=idempotency_key,
            payload_hash=payload_hash,
        )
        raise

    return await complete(db, record, _job_response(job, include_url=False))


@router.get("/jobs")
async def read_latest_image_job(
    project_id: str = Query(pattern=_ID_PATTERN, max_length=64),
    latest: bool = Query(True),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recover the generation already in flight for a project after a reload.

    A reloaded page has no job id, and starting a new generation to find out
    would spend a second unit. This answers with the project's most recent job
    -- or ``null`` -- scoped to the caller's workspace, so a guessed project id
    reveals nothing. Only the latest is ever returned; ``latest`` exists so the
    contract can grow a listing later without changing this shape.
    """

    if not latest:
        raise AppError(
            "VALIDATION_ERROR",
            "Solo puede consultarse la generación más reciente del proyecto.",
            status_code=422,
        )
    job = await image_service.latest_job(
        db, workspace_id=workspace_id, project_id=project_id
    )
    return {"job": _job_response(job, include_url=True) if job else None}


@router.get("/jobs/{job_id}")
async def read_image_job(
    job_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Poll one job. A fresh signed link is minted on every successful read."""

    job = await image_service.get_job(db, workspace_id=workspace_id, job_id=job_id)
    return _job_response(job, include_url=True)


@router.get("/files/{asset_id}")
async def read_generated_image(
    asset_id: str,
    workspace: str | None = Query(None, max_length=64),
    expires: str | None = Query(None, max_length=20),
    signature: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve the generated bytes to a valid, unexpired signature.

    The parameters are optional so a malformed link fails as an invalid link
    rather than as a schema error: both cases must be indistinguishable.
    """

    verify_image_url(
        asset_id=asset_id,
        workspace_id=workspace or "",
        expires=expires,
        signature=signature,
    )
    asset = await db.scalar(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.workspace_id == workspace,
            Asset.asset_type == "image",
        )
    )
    if asset is None:
        # A missing asset is reported like a bad signature: whether an id
        # exists is not something an unauthenticated caller may probe.
        raise invalid_image_link()
    content = await get_object_storage_provider().read(key=asset.storage_path)
    return Response(
        content=content,
        media_type=asset.mime_type,
        headers={
            # The link is already short-lived; caching it would outlive it.
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
        },
    )
