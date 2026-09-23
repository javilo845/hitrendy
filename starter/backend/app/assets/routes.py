from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.analysis_service import analysis_to_dict, analyze_authorized_asset
from app.assets.models import Asset, UploadSession
from app.assets.validation import (
    ALLOWED_MIME,
    ImageMetadata,
    read_image_metadata,
    validate_image_bytes,
)
from app.core.config import settings
from app.core.errors import NotFoundError
from app.dependencies import get_db, require_workspace
from app.providers.factory import get_vision_provider
from app.providers.storage import get_object_storage_provider

router = APIRouter(prefix="/assets", tags=["assets"])

__all__ = ["ALLOWED_MIME", "ImageMetadata", "router"]


def _validate_upload(content: bytes, declared_mime_type: str | None) -> ImageMetadata:
    return validate_image_bytes(content, declared_mime_type)


def _read_image_metadata(content: bytes) -> ImageMetadata | None:
    return read_image_metadata(content)


class InitUploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    fields: dict = Field(default_factory=dict)


@router.post("/uploads", response_model=InitUploadResponse)
async def init_upload(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> InitUploadResponse:
    upload_id = uuid.uuid4().hex
    db.add(
        UploadSession(
            id=upload_id,
            workspace_id=workspace_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()
    return InitUploadResponse(
        upload_id=upload_id,
        upload_url=f"{settings.api_prefix}/assets/uploads/{upload_id}/complete",
        fields={},
    )


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    file: UploadFile,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    content = await file.read()
    image = _validate_upload(content, file.content_type)
    session_result = await db.execute(
        select(UploadSession).where(
            UploadSession.id == upload_id,
            UploadSession.workspace_id == workspace_id,
            UploadSession.completed_at.is_(None),
        )
    )
    upload_session = session_result.scalar_one_or_none()
    if upload_session is None:
        raise NotFoundError("Sesión de carga")
    object_key = f"workspaces/{workspace_id}/assets/{upload_id}{image.extension}"
    storage = get_object_storage_provider()
    await storage.put(key=object_key, content=content, content_type=image.mime_type)
    try:
        asset = Asset(
            workspace_id=workspace_id,
            original_name=file.filename or "upload",
            storage_path=object_key,
            mime_type=image.mime_type,
            file_size_bytes=len(content),
            asset_type="image",
            width=image.width,
            height=image.height,
        )
        db.add(asset)
        upload_session.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(asset)
    except Exception:
        await db.rollback()
        await storage.delete(key=object_key)
        raise

    return {
        "status": "ok",
        "asset_id": asset.id,
        "original_name": asset.original_name,
        "file_size_bytes": asset.file_size_bytes,
        "mime_type": asset.mime_type,
    }


@router.get("/{asset_id}/content")
async def read_asset_content_endpoint(
    asset_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.workspace_id == workspace_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Activo")
    content = await get_object_storage_provider().read(key=asset.storage_path)
    return Response(
        content=content,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("")
async def list_assets_endpoint(
    asset_type: str | None = None,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = select(Asset).where(Asset.workspace_id == workspace_id)
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    query = query.order_by(Asset.created_at.desc()).limit(50)
    result = await db.execute(query)
    return [
        {
            "id": a.id,
            "original_name": a.original_name,
            "mime_type": a.mime_type,
            "file_size_bytes": a.file_size_bytes,
            "asset_type": a.asset_type,
            "status": a.status,
            "width": a.width,
            "height": a.height,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in result.scalars().all()
    ]


@router.get("/{asset_id}")
async def get_asset_endpoint(
    asset_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.workspace_id == workspace_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Activo")
    return {
        "id": asset.id,
        "original_name": asset.original_name,
        "mime_type": asset.mime_type,
        "file_size_bytes": asset.file_size_bytes,
        "asset_type": asset.asset_type,
        "status": asset.status,
        "width": asset.width,
        "height": asset.height,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


@router.post("/{asset_id}/analyses")
async def analyze_asset_endpoint(
    asset_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    analysis_record, analysis, review_mode = await analyze_authorized_asset(
        db,
        workspace_id=workspace_id,
        asset_id=asset_id,
        provider_factory=get_vision_provider,
    )
    await db.commit()
    await db.refresh(analysis_record)
    return analysis_to_dict(analysis_record, analysis, review_mode)
