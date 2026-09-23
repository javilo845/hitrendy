from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.operations.models import AbuseReport, ProductFeedback

router = APIRouter(tags=["beta operations"])


class ProductFeedbackRequest(BaseModel):
    category: Literal["bug", "idea", "support", "other"] = "other"
    message: str = Field(min_length=1, max_length=2000)
    rating: int | None = Field(None, ge=1, le=5)


class AbuseReportRequest(BaseModel):
    category: Literal["unsafe_content", "spam", "harassment", "other"]
    message: str = Field(min_length=1, max_length=2000)
    resource_id: str | None = Field(None, min_length=1, max_length=128)


@router.get("/policies")
async def public_policies() -> dict[str, object]:
    """Expose the policy versions used by the public and account screens."""

    return {
        "privacy": {
            "version": settings.privacy_policy_version,
            "path": "/privacy",
            "retention_days": settings.data_retention_days,
        },
        "terms": {"version": settings.terms_version, "path": "/terms"},
        "support": {"email": settings.support_email, "path": "/feedback"},
        "email_verification": settings.email_verification_mode,
        "closed_beta": settings.beta_invites_enabled,
    }


@router.post("/feedback", status_code=201)
async def create_product_feedback(
    body: ProductFeedbackRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    principal: CurrentPrincipal = Depends(get_current_principal),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Create a support signal without accepting arbitrary HTML or files."""

    if idempotency_key:
        existing = await db.scalar(
            select(ProductFeedback).where(
                ProductFeedback.workspace_id == workspace_id,
                ProductFeedback.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return _feedback_response(existing)

    feedback = ProductFeedback(
        workspace_id=workspace_id,
        user_id=principal.user["id"],
        category=body.category,
        rating=body.rating,
        message=body.message.strip(),
        idempotency_key=idempotency_key,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return _feedback_response(feedback)


@router.post("/abuse/reports", status_code=201)
async def create_abuse_report(
    body: AbuseReportRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Record an abuse report; moderation decisions stay outside the client."""

    report = AbuseReport(
        workspace_id=workspace_id,
        reporter_user_id=principal.user["id"],
        category=body.category,
        message=body.message.strip(),
        resource_id=body.resource_id.strip() if body.resource_id else None,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return {"id": report.id, "status": report.status}


def _feedback_response(feedback: ProductFeedback) -> dict[str, object]:
    return {
        "id": feedback.id,
        "category": feedback.category,
        "rating": feedback.rating,
        "status": feedback.status,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }

