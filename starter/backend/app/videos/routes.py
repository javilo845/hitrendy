"""HTTP endpoints for private, asynchronous video generation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.conversations.idempotency import complete, recover_failed
from app.conversations.models import IdempotencyRecord
from app.core.errors import AppError, NotFoundError
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.providers.storage import get_object_storage_provider
from app.videos import service as video_service
from app.videos.schemas import (
    VideoJobCreate,
    VideoJobPublic,
    VideoLatestJobResponse,
    VideoPreflightRequest,
    VideoPreflightResponse,
    VideoStoryboardDraft,
    VideoStoryboardRequest,
)
from app.videos.signing import verify_video_url

router = APIRouter(prefix="/videos", tags=["videos"])

_CREATE_ENDPOINT = "POST:/videos/jobs"
_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@router.post("/storyboard", response_model=VideoStoryboardDraft)
async def create_video_storyboard(
    body: VideoStoryboardRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> VideoStoryboardDraft:
    draft = await video_service.draft_storyboard(
        db,
        workspace_id=workspace_id,
        business_id=body.business_id,
        publication_text=body.publication_text,
        trend_title=body.trend_title,
        duration_seconds=body.duration_seconds,
    )
    await db.commit()
    return draft


@router.post("/preflight", response_model=VideoPreflightResponse)
async def preflight_video(
    body: VideoPreflightRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> VideoPreflightResponse:
    response = await video_service.preflight(db, workspace_id=workspace_id, payload=body)
    await db.commit()
    return response


@router.post("/jobs", response_model=VideoJobPublic, status_code=202)
async def create_video_job(
    body: VideoJobCreate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> VideoJobPublic:
    if not idempotency_key:
        raise AppError(
            "idempotency_key_required",
            "Falta la clave de idempotencia de la solicitud.",
            status_code=400,
        )

    try:
        job = await video_service.create_job(
            db,
            workspace_id=workspace_id,
            payload=body,
            idempotency_key=idempotency_key,
            requested_by_user_id=principal.user["id"],
        )
        public = video_service.to_public(job, include_url=False)
        record = await db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.workspace_id == workspace_id,
                IdempotencyRecord.endpoint == _CREATE_ENDPOINT,
                IdempotencyRecord.key == idempotency_key,
            )
        )
        await complete(db, record, public.model_dump(mode="json"), commit=False)
        await db.commit()
        return public
    except Exception as exc:
        # A request already owned by another worker must stay processing; all
        # other failures leave this key retryable without touching a provider.
        if getattr(exc, "code", None) == "idempotency_conflict":
            await db.rollback()
        else:
            await recover_failed(
                db,
                workspace_id=workspace_id,
                endpoint=_CREATE_ENDPOINT,
                key=idempotency_key,
            )
        raise


@router.get("/jobs/{job_id}", response_model=VideoJobPublic)
async def read_video_job(
    job_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> VideoJobPublic:
    job = await video_service.get_job(db, workspace_id=workspace_id, job_id=job_id)
    return video_service.to_public(job, include_url=True)


@router.get("/jobs", response_model=VideoLatestJobResponse)
async def read_latest_video_job(
    project_id: str | None = Query(None, pattern=_ID_PATTERN, max_length=64),
    latest: bool = Query(False),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> VideoLatestJobResponse:
    if not project_id or not latest:
        raise AppError(
            "latest_query_required",
            "Indica un proyecto y latest=true para consultar la generación más reciente.",
            status_code=400,
        )
    job = await video_service.latest_job(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    return VideoLatestJobResponse(
        job=video_service.to_public(job, include_url=True) if job else None
    )


@router.get("/files/{asset_id}")
async def read_video_file(
    asset_id: str,
    workspace: str | None = Query(None, max_length=64),
    expires: str | None = Query(None, max_length=20),
    signature: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve a complete private object only through a valid signed URL."""

    try:
        # Verify before querying either the database or object storage so an
        # invalid link cannot become an asset-existence oracle.
        verify_video_url(
            asset_id=asset_id,
            workspace_id=workspace or "",
            expires_at=expires,
            signature=signature,
        )
    except AppError as exc:
        raise NotFoundError("Video") from exc

    asset = await db.scalar(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.workspace_id == workspace,
            Asset.asset_type == "video",
        )
    )
    if asset is None:
        raise NotFoundError("Video")
    try:
        content = await get_object_storage_provider().read(key=asset.storage_path)
    except AppError as exc:
        if exc.code == "ASSET_UNAVAILABLE":
            raise NotFoundError("Video") from exc
        raise
    # The storage adapter exposes only whole-object reads. WAVE-013 does not
    # simulate Range support; this response honestly declares it unavailable.
    return Response(
        content=content,
        media_type=asset.mime_type,
        headers={
            "Content-Length": str(len(content)),
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
            "Accept-Ranges": "none",
        },
    )


__all__ = ["router"]
