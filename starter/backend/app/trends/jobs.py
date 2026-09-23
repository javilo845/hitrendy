"""Externally scheduled daily trend collection.

The scheduler owns only invocation. PostgreSQL ``TrendRun`` rows own global
scope idempotency and locking, while workspace relevance is derived afterward
from persisted evidence without contacting providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.business.models import Business
from app.core.config import settings
from app.db.session import get_session_factory
from app.trends.service import TrendService

logger = logging.getLogger("hitrendy.trends.jobs")


@dataclass(frozen=True)
class TrendJobScopeResult:
    region: str
    category: str | None
    run_id: str | None
    status: str


@dataclass(frozen=True)
class TrendRunDueResult:
    scopes: tuple[TrendJobScopeResult, ...]
    workspaces_scored: int

    @property
    def failed(self) -> int:
        return sum(scope.status in {"failed", "error"} for scope in self.scopes)


async def _score_workspaces(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as db:
        workspace_ids = tuple(
            (
                await db.scalars(
                    select(Business.workspace_id)
                    .distinct()
                    .order_by(Business.workspace_id)
                )
            ).all()
        )
        service = TrendService(db, sources=())
        for workspace_id in workspace_ids:
            await service.compute_workspace_relevance(workspace_id)
        await db.commit()
        return len(workspace_ids)


async def run_due(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    scopes: tuple[dict[str, str | None], ...] | None = None,
) -> TrendRunDueResult:
    """Collect each configured scope once and refresh all private scores."""

    factory = session_factory or get_session_factory()
    configured_scopes = scopes if scopes is not None else settings.trends_scheduled_scopes
    results: list[TrendJobScopeResult] = []
    for scope in configured_scopes:
        region, category = str(scope["region"]), scope["category"]
        try:
            async with factory() as db:
                run = await TrendService(db).collect(region=region, category=category)
            results.append(TrendJobScopeResult(region, category, run.id, run.status))
        except Exception:
            # Provider exception payloads may contain secrets. Scope values are
            # validated server-side and are the only safe diagnostic context.
            logger.warning(
                "trend_scope_failed",
                extra={"region": region, "category": category},
            )
            results.append(TrendJobScopeResult(region, category, None, "error"))
    workspaces_scored = await _score_workspaces(factory)
    return TrendRunDueResult(tuple(results), workspaces_scored)
