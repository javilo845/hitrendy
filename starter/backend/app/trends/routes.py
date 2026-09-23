from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.models import Business
from app.conversations.idempotency import (
    complete,
    mark_failed,
    payload_fingerprint,
    recover_failed,
    reserve,
)
from app.core.capabilities import Capability, CapabilityStatus, get_runtime_capability_registry
from app.core.config import settings
from app.core.errors import AppError
from app.dependencies import get_db, require_workspace
from app.trends.factory import source_availability
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendRun,
    WorkspaceTrendRelevance,
)
from app.trends.service import EMPTY_RUN_MESSAGE, NO_APPLICABLE_SOURCES_MESSAGE, TrendService

router = APIRouter(prefix="/trends", tags=["trends"])
_capability_registry = get_runtime_capability_registry()


class RefreshRequest(BaseModel):
    region: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-zÀ-ÿ _-]+$")
    category: str | None = Field(None, max_length=40, pattern=r"^[a-z_]+$")


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat()


def _item(item: TrendItem, relevance: WorkspaceTrendRelevance | None = None) -> dict:
    result = {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "region": item.region,
        "category": item.category,
        "observed_at": _utc_iso(item.observed_at),
        "freshness_score": item.freshness_score,
        "scoring_version": item.scoring_version,
        "component_scores": json.loads(item.component_scores),
        "total_score": item.total_score,
        "calculated_at": _utc_iso(item.calculated_at),
    }
    if relevance:
        result["workspace_relevance"] = {
            "score": relevance.score,
            "component_scores": json.loads(relevance.component_scores),
            "calculated_at": _utc_iso(relevance.calculated_at),
        }
    return result


def _run_response(
    run: TrendRun,
    *,
    refresh_allowed: bool,
    next_refresh_at: datetime | None,
) -> dict:
    now = datetime.now(UTC)
    retry_after_seconds = (
        max(0, ceil((next_refresh_at - now).total_seconds()))
        if next_refresh_at is not None and not refresh_allowed
        else None
    )
    return {
        "id": run.id,
        "status": run.status,
        "region": run.region,
        "category": run.category,
        "sources_attempted": json.loads(run.sources_attempted),
        "sources_succeeded": json.loads(run.sources_succeeded),
        "sources_failed": json.loads(run.sources_failed),
        "started_at": _utc_iso(run.started_at),
        "finished_at": _utc_iso(run.finished_at),
        "error": run.public_error,
        "refresh_allowed": refresh_allowed,
        "next_refresh_at": _utc_iso(next_refresh_at),
        "retry_after_seconds": retry_after_seconds,
    }


@router.post("/refresh", status_code=202)
async def refresh_trends(
    body: RefreshRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = {
        "region": body.region.strip().upper(),
        "category": body.category.strip().casefold() if body.category is not None else None,
    }
    payload_hash = payload_fingerprint(payload)
    request = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint="POST:/trends/refresh",
        key=idempotency_key,
        payload_hash=payload_hash,
    )
    if request and request.status == "completed" and request.response_json:
        return json.loads(request.response_json)
    try:
        if _capability_registry.get_base_capability(Capability.TREND_ANALYSIS).status not in {
            CapabilityStatus.AVAILABLE,
            CapabilityStatus.DEGRADED,
        }:
            raise AppError(
                "CAPABILITY_UNAVAILABLE",
                "El análisis de tendencias no está disponible.",
                status_code=503,
            )
        service = TrendService(db, capability_registry=_capability_registry)
        refresh_allowed, next_refresh_at, existing_run = (
            await service.manual_refresh_availability(**payload)
        )
        if not refresh_allowed and existing_run is not None:
            await service.compute_workspace_relevance(workspace_id)
            await db.commit()
            response = _run_response(
                existing_run,
                refresh_allowed=False,
                next_refresh_at=next_refresh_at,
            )
            return await complete(db, request, response)
        run = await service.refresh(workspace_id=workspace_id, **payload)
    except Exception:
        await recover_failed(
            db,
            workspace_id=workspace_id,
            endpoint="POST:/trends/refresh",
            key=idempotency_key,
            payload_hash=payload_hash,
        )
        raise
    _, next_refresh_at, _ = await service.manual_refresh_availability(**payload)
    response = _run_response(
        run,
        refresh_allowed=run.status == "failed",
        next_refresh_at=next_refresh_at,
    )
    if run.status == "failed":
        # A failed collection is deliberately retryable with the same key.
        # Do not persist an unsuccessful response as an idempotent completion.
        await mark_failed(
            db,
            workspace_id=workspace_id,
            endpoint="POST:/trends/refresh",
            key=idempotency_key,
        )
        return response
    return await complete(db, request, response)


@router.get("/home")
async def trends_home(
    limit: int = Query(8, ge=1, le=12),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregated Home for the workspace.

    Contract, deliberately explicit because the two halves are not the same
    scope:

    * ``items`` is an aggregated, workspace-private list. It contains every
      visible trend of the workspace regardless of scope, privately ranked, and
      each card declares its own ``region``/``category``. It is never filtered
      to the refresh scope.
    * ``refresh_scope`` is only the scope the manual refresh button will
      collect: the business region/category. It does not describe the cards.
    * ``refresh_allowed`` and ``next_refresh_at`` belong to ``refresh_scope``.
    * ``updated_at`` represents the aggregated visible data, not necessarily
      that single scope.
    """

    now = datetime.now(UTC)
    service = TrendService(db)
    await service.compute_workspace_relevance(workspace_id)
    await db.commit()
    business = await db.scalar(
        select(Business)
        .where(Business.workspace_id == workspace_id)
        .order_by(Business.created_at)
    )
    refresh_region = business.country.strip().upper() if business else "GLOBAL"
    refresh_category = business.category.strip().casefold() if business else None
    items = await service.list(
        workspace_id=workspace_id,
        region=None,
        category=None,
        limit=limit,
        private_ranked=True,
    )
    relevances = {
        row.trend_item_id: row
        for row in (
            await db.scalars(
                select(WorkspaceTrendRelevance).where(
                    WorkspaceTrendRelevance.workspace_id == workspace_id
                )
            )
        ).all()
    }
    item_ids = [item.id for item in items]
    evidence_by_item: dict[str, list[TrendEvidence]] = {item_id: [] for item_id in item_ids}
    if item_ids:
        evidence_rows = (
            await db.execute(
                select(TrendItemEvidence.trend_item_id, TrendEvidence)
                .join(
                    TrendEvidence,
                    TrendEvidence.id == TrendItemEvidence.trend_evidence_id,
                )
                .where(TrendItemEvidence.trend_item_id.in_(item_ids))
                .order_by(
                    TrendItemEvidence.trend_item_id,
                    TrendEvidence.source,
                    TrendEvidence.canonical_url,
                )
            )
        ).all()
        for trend_item_id, evidence in evidence_rows:
            evidence_by_item[trend_item_id].append(evidence)
    sources = await source_availability()
    source_names = {source.identifier: source.public_name for source in sources}
    source_names.update({source.identifier: source.public_name for source in service.sources})
    source_counts = {
        status: sum(source.status == status for source in sources)
        for status in (
            "available",
            "degraded",
            "quota_exhausted",
            "unavailable",
            "unconfigured",
            "disabled",
        )
    }
    # Run state is scoped to the refresh target only: it drives the button and
    # the degradation banner, never the visibility of the aggregated cards.
    latest_run = await service.latest_run(
        region=refresh_region,
        category=refresh_category,
    )
    latest_successful_run = await service.latest_successful_run(
        region=refresh_region,
        category=refresh_category,
    )
    refresh_allowed, next_refresh_at, _ = await service.manual_refresh_availability(
        region=refresh_region,
        category=refresh_category,
    )
    base_status = _capability_registry.get_base_capability(Capability.TREND_ANALYSIS).status
    runtime_status = _capability_registry.get_capability(Capability.TREND_ANALYSIS).status
    stale_cutoff = now - timedelta(seconds=settings.trends_stale_after_seconds)
    any_stale = any(
        (item.observed_at.replace(tzinfo=UTC) if item.observed_at.tzinfo is None else item.observed_at)
        < stale_cutoff
        for item in items
    )
    degraded = (
        runtime_status
        in {
            CapabilityStatus.DEGRADED,
            CapabilityStatus.ERROR,
            CapabilityStatus.QUOTA_EXHAUSTED,
        }
        or (latest_run is not None and latest_run.status == "partial")
        or bool(
            source_counts["degraded"]
            + source_counts["quota_exhausted"]
            + source_counts["unavailable"]
        )
    )
    if base_status == CapabilityStatus.DISABLED:
        home_status = "disabled"
    elif base_status == CapabilityStatus.UNCONFIGURED:
        home_status = "unconfigured"
    elif items and degraded:
        home_status = "degraded"
    elif items and any_stale:
        home_status = "stale"
    elif items:
        home_status = "fresh"
    elif latest_run is None:
        home_status = "empty"
    elif latest_run.status == "failed":
        attempted = json.loads(latest_run.sources_attempted)
        healthy_identifiers = {
            source.identifier for source in sources if source.status == "available"
        }
        home_status = (
            "empty"
            if latest_run.public_error
            in {EMPTY_RUN_MESSAGE, NO_APPLICABLE_SOURCES_MESSAGE}
            or not attempted
            or set(attempted).issubset(healthy_identifiers)
            else "degraded"
            if degraded
            else "failed"
        )
    else:
        home_status = "empty"
    updated_at_values = [
        item.observed_at.replace(tzinfo=UTC)
        if item.observed_at.tzinfo is None
        else item.observed_at.astimezone(UTC)
        for item in items
    ]
    if (
        latest_successful_run is not None
        and latest_successful_run.finished_at is not None
    ):
        updated_at_values.append(
            latest_successful_run.finished_at.replace(tzinfo=UTC)
            if latest_successful_run.finished_at.tzinfo is None
            else latest_successful_run.finished_at.astimezone(UTC)
        )
    # EMPTY is a healthy provider response even though the legacy TrendRun
    # status contract retains "failed" when no evidence was published.
    if (
        latest_run is not None
        and latest_run.public_error == EMPTY_RUN_MESSAGE
        and latest_run.finished_at is not None
    ):
        updated_at_values.append(
            latest_run.finished_at.replace(tzinfo=UTC)
            if latest_run.finished_at.tzinfo is None
            else latest_run.finished_at.astimezone(UTC)
        )
    cards = []
    for item in items:
        observed_at = (
            item.observed_at.replace(tzinfo=UTC)
            if item.observed_at.tzinfo is None
            else item.observed_at.astimezone(UTC)
        )
        card = _item(item, relevances.get(item.id))
        card["freshness"] = "stale" if observed_at < stale_cutoff else "fresh"
        card["evidence"] = [
            {
                "source": evidence.source,
                "source_name": source_names.get(evidence.source, evidence.source),
                "source_url": evidence.source_url,
                "observed_at": _utc_iso(evidence.observed_at),
            }
            for evidence in evidence_by_item[item.id]
        ]
        cards.append(card)
    return {
        "status": home_status,
        # Only the scope the manual refresh button collects. The cards below
        # are aggregated and each one declares its own region/category.
        "refresh_scope": {"region": refresh_region, "category": refresh_category},
        # Aggregated visible data, not necessarily `refresh_scope`.
        "updated_at": max(updated_at_values).isoformat() if updated_at_values else None,
        # Belongs to `refresh_scope`.
        "refresh_allowed": refresh_allowed
        and base_status in {CapabilityStatus.AVAILABLE, CapabilityStatus.DEGRADED},
        "next_refresh_at": next_refresh_at.isoformat() if next_refresh_at else None,
        "sources": {"total": len(sources), **source_counts},
        "items": cards,
    }


@router.get("")
async def list_trends(
    region: str | None = Query(None, min_length=2, max_length=80),
    category: str | None = Query(None, max_length=40),
    limit: int = Query(20, ge=1, le=50),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = TrendService(db)
    # Filters are normalized exactly like refresh so a stored identity is
    # reachable by any accepted spelling of the same region or category.
    items = await service.list(
        workspace_id=workspace_id,
        region=region.strip().upper() if region else None,
        category=category.strip().casefold() if category else None,
        limit=limit,
    )
    relevances = {
        row.trend_item_id: row
        for row in (
            await db.scalars(
                select(WorkspaceTrendRelevance).where(
                    WorkspaceTrendRelevance.workspace_id == workspace_id
                )
            )
        ).all()
    }
    return {"items": [_item(item, relevances.get(item.id)) for item in items]}


@router.get("/sources")
async def trend_sources(workspace_id: str = Depends(require_workspace)) -> dict:
    """Authenticated, safe source configuration/runtime summary."""

    del workspace_id
    return {
        "sources": [
            {
                "identifier": source.identifier,
                "public_name": source.public_name,
                "source_type": source.source_type,
                "configured": source.configured,
                "status": source.status,
                "next_reset_at": source.next_reset_at.isoformat()
                if source.next_reset_at is not None
                else None,
            }
            for source in await source_availability()
        ]
    }


@router.get("/{trend_id}")
async def trend_detail(
    trend_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await TrendService(db).detail(workspace_id=workspace_id, trend_id=trend_id)
    if item is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Tendencia")
    relevance = await db.scalar(
        select(WorkspaceTrendRelevance).where(
            WorkspaceTrendRelevance.workspace_id == workspace_id,
            WorkspaceTrendRelevance.trend_item_id == item.id,
        )
    )
    evidences = (
        await db.scalars(
            select(TrendEvidence)
            .join(TrendItemEvidence)
            .where(TrendItemEvidence.trend_item_id == item.id)
            .order_by(TrendEvidence.source, TrendEvidence.canonical_url)
        )
    ).all()
    result = _item(item, relevance)
    result["evidence"] = [
        {
            "source": evidence.source,
            "source_url": evidence.source_url,
            "observed_at": _utc_iso(evidence.observed_at),
            "region": evidence.region,
            "confidence": evidence.confidence,
        }
        for evidence in evidences
    ]
    return result
