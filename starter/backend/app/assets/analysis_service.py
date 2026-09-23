from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetAnalysis
from app.assets.schemas import AssetAnalysisResult
from app.core.errors import AppError, NotFoundError
from app.providers.factory import get_vision_provider
from app.providers.storage import get_object_storage_provider
from app.providers.vision import VisionReviewProvider, VisionReviewRequest


async def analyze_authorized_asset(
    db: AsyncSession,
    *,
    workspace_id: str,
    asset_id: str,
    question: str | None = None,
    provider_factory: Callable[[], VisionReviewProvider] | None = None,
) -> tuple[AssetAnalysis, AssetAnalysisResult, str]:
    """Review one authorized image, answering ``question`` when there is one."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.workspace_id == workspace_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Activo")

    provider = (provider_factory or get_vision_provider)()
    image_bytes = None
    if provider.requires_image_content:
        image_bytes = await get_object_storage_provider().read(key=asset.storage_path)

    biz_context = None
    try:
        from app.conversations.repository import SqlBusinessContextRepository
        biz_repo = SqlBusinessContextRepository(db)
        biz_context = await biz_repo.get_for_generation(workspace_id=workspace_id)
    except Exception:
        pass

    try:
        analysis = AssetAnalysisResult.model_validate(
            await provider.analyze(
                request=VisionReviewRequest(
                    mime_type=asset.mime_type,
                    width=asset.width,
                    height=asset.height,
                    image_bytes=image_bytes,
                    business_name=biz_context.name if biz_context else None,
                    business_category=biz_context.category if biz_context else None,
                    primary_product=biz_context.primary_product if biz_context else None,
                    target_audience=biz_context.target_audience if biz_context else None,
                    city=biz_context.city if biz_context else None,
                    question=question,
                )
            )
        )
    except PydanticValidationError as exc:
        raise AppError(
            "ANALYSIS_INVALID_RESPONSE",
            "No pudimos validar el resultado del análisis visual. Inténtalo nuevamente.",
            status_code=502,
            retryable=True,
        ) from exc

    analysis_record = AssetAnalysis(
        asset_id=asset.id,
        provider=provider.provider_name,
        summary=analysis.summary,
        strengths_json=json.dumps(analysis.strengths),
        improvements_json=json.dumps([item.model_dump() for item in analysis.improvements]),
        revised_copy=analysis.revised_copy,
        accessibility_notes_json=json.dumps(analysis.accessibility_notes),
    )
    db.add(analysis_record)
    await db.flush()
    return analysis_record, analysis, "technical" if provider.provider_name == "demo" else "visual"


def analysis_to_dict(
    record: AssetAnalysis, analysis: AssetAnalysisResult, review_mode: str
) -> dict:
    return {
        "id": record.id,
        "asset_id": record.asset_id,
        "summary": analysis.summary,
        "strengths": analysis.strengths,
        "improvements": [item.model_dump() for item in analysis.improvements],
        "revised_copy": analysis.revised_copy,
        "accessibility_notes": analysis.accessibility_notes,
        "ai_hallmarks": getattr(analysis, "ai_hallmarks", []),
        "canva_templates": [t.model_dump() if hasattr(t, "model_dump") else t for t in getattr(analysis, "canva_templates", [])],
        "canva_slots_guide": getattr(analysis, "canva_slots_guide", {}),
        "canva_query": getattr(analysis, "canva_query", ""),
        "canva_query_suggestions": getattr(analysis, "canva_query_suggestions", []),
        "review_mode": review_mode,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
