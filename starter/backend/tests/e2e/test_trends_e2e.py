"""WAVE-010A — global evidence with private workspace relevance on PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.business.models import Business
from app.core.config import settings
from app.db.session import get_session_factory
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember
from app.main import app
from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendRun,
    WorkspaceTrendRelevance,
)
from app.trends.service import TrendService


async def _workspace_client(*, suffix: str, category: str, country: str) -> tuple[AsyncClient, str]:
    workspace_id, user_id, token = f"ws_trend_{suffix}", f"usr_trend_{suffix}", f"token-{suffix}"
    async with get_session_factory()() as db:
        db.add_all((
            User(id=user_id, email=f"trend-{suffix}@example.com", name=suffix, password_hash="x"),
            Workspace(id=workspace_id, name=f"Workspace {suffix}"),
        ))
        await db.flush()
        db.add_all((
            WorkspaceMember(id=f"wsm_trend_{suffix}", workspace_id=workspace_id, user_id=user_id),
            AuthSession(
                id=f"ses_trend_{suffix}", token_hash=sha256(token.encode()).hexdigest(), user_id=user_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
            Business(
                id=f"biz_trend_{suffix}", workspace_id=workspace_id, name=f"Business {suffix}",
                category=category, country=country, city="Tegucigalpa", primary_product="Producto",
                target_audience="Audiencia", preferred_platforms='["instagram"]', primary_objective="sales",
            ),
        ))
        await db.commit()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set("hitrendy_session", token)
    return client, workspace_id


@pytest.mark.asyncio
async def test_global_refresh_reuse_relevance_and_concurrency_postgres(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    client_a, workspace_a = await _workspace_client(suffix="a", category="gastronomy", country="HN")
    client_b, workspace_b = await _workspace_client(suffix="b", category="retail", country="BR")
    try:
        first = await client_a.post(
            "/api/v1/trends/refresh", json={"region": "HN", "category": "gastronomy"},
            headers={"X-Workspace-Id": workspace_a, "Idempotency-Key": "e2e-trend-a"},
        )
        assert first.status_code == 202, first.text

        # Different workspaces share the global collection but receive their
        # own persisted relevance values.
        second = await client_b.post(
            "/api/v1/trends/refresh", json={"region": "HN", "category": "gastronomy"},
            headers={"X-Workspace-Id": workspace_b, "Idempotency-Key": "e2e-trend-b"},
        )
        assert second.status_code == 202 and second.json()["id"] == first.json()["id"]
        listed_a = await client_a.get("/api/v1/trends", headers={"X-Workspace-Id": workspace_a})
        listed_b = await client_b.get("/api/v1/trends", headers={"X-Workspace-Id": workspace_b})
        assert listed_a.status_code == listed_b.status_code == 200
        trend_id = listed_a.json()["items"][0]["id"]
        assert listed_b.json()["items"][0]["id"] == trend_id
        assert listed_a.json()["items"][0]["workspace_relevance"]["score"] != listed_b.json()["items"][0]["workspace_relevance"]["score"]
        detail = await client_a.get(f"/api/v1/trends/{trend_id}", headers={"X-Workspace-Id": workspace_a})
        assert detail.status_code == 200 and len(detail.json()["evidence"]) == 2

        async def refresh(workspace_id: str):
            async with get_session_factory()() as db:
                return await TrendService(db).refresh(workspace_id=workspace_id, region="GLOBAL", category=None)

        concurrent_a, concurrent_b = await asyncio.gather(refresh(workspace_a), refresh(workspace_b))
        assert concurrent_a.id == concurrent_b.id
        async with get_session_factory()() as db:
            assert await db.scalar(select(func.count()).select_from(TrendRun)) == 2
            assert await db.scalar(select(func.count()).select_from(TrendEvidence)) == 4
            assert await db.scalar(select(func.count()).select_from(WorkspaceTrendRelevance)) >= 4
    finally:
        await client_a.aclose()
        await client_b.aclose()


@pytest.mark.asyncio
async def test_temporal_observations_and_abandoned_run_locking_postgres(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    client, workspace_id = await _workspace_client(suffix="temporal", category="gastronomy", country="HN")

    class TemporalSource:
        source_type, supported_regions, available = "demo", ("HN",), True

        def __init__(self) -> None:
            self.identifier, self.public_name = "demo-temporal", "Demo temporal"
            self.observed = datetime(2026, 1, 2, 12, tzinfo=UTC)
            self.calls = 0

        async def fetch(self, *, region, category):
            self.calls += 1
            return SourceFetchResult("success", (SourceCandidate(
                "Tema reobservado", "", region, category, self.observed,
                (SourceEvidence("https://demo.invalid/reobserved", self.observed, region, 0.8),),
            ),))

    source = TemporalSource()
    try:
        async with get_session_factory()() as db:
            first = await TrendService(db, (source,), now=datetime(2026, 1, 3, 12, tzinfo=UTC)).refresh(
                workspace_id=workspace_id, region="HN", category=None
            )
        source.observed = datetime(2026, 1, 4, 12, tzinfo=UTC)
        async with get_session_factory()() as db:
            same_window = await TrendService(db, (source,), now=datetime(2026, 1, 4, 12, tzinfo=UTC)).refresh(
                workspace_id=workspace_id, region="HN", category=None
            )
        source.observed = datetime(2026, 1, 10, 12, tzinfo=UTC)
        async with get_session_factory()() as db:
            later_window = await TrendService(db, (source,), now=datetime(2026, 1, 10, 12, tzinfo=UTC)).refresh(
                workspace_id=workspace_id, region="HN", category=None
            )
            items = (await db.scalars(select(TrendItem).where(TrendItem.title == "Tema reobservado"))).all()
            observations = (await db.scalars(
                select(TrendEvidence).where(TrendEvidence.canonical_url == "https://demo.invalid/reobserved")
            )).all()
        assert first.id != same_window.id != later_window.id
        assert len(items) == 2
        assert len(observations) == 2

        class SharedEvidenceSource(TemporalSource):
            def __init__(self) -> None:
                super().__init__()
                self.identifier, self.public_name = "demo-shared-e2e", "Demo shared"
                self.observed = datetime(2026, 3, 1, 12, tzinfo=UTC)

            async def fetch(self, *, region, category):
                evidence = SourceEvidence("https://demo.invalid/shared-e2e", self.observed, region, 0.8)
                return SourceFetchResult("success", (
                    SourceCandidate("Título A", "", region, category, self.observed, (evidence,)),
                    SourceCandidate("Título B", "", region, category, self.observed, (evidence,)),
                ))

        async with get_session_factory()() as db:
            await TrendService(
                db, (SharedEvidenceSource(),), now=datetime(2026, 3, 1, 12, tzinfo=UTC)
            ).refresh(workspace_id=workspace_id, region="HN", category="shared")
            shared = await db.scalar(
                select(TrendEvidence).where(TrendEvidence.canonical_url == "https://demo.invalid/shared-e2e")
            )
            assert shared is not None
            links = (await db.scalars(
                select(TrendItemEvidence).where(TrendItemEvidence.trend_evidence_id == shared.id)
            )).all()
            assert len(links) == 2

        lock_now = datetime(2026, 2, 1, 12, tzinfo=UTC)
        source.observed = lock_now
        async with get_session_factory()() as db:
            abandoned = await TrendService(db, (source,), now=lock_now).refresh(
                workspace_id=workspace_id, region="HN", category="lock"
            )
            abandoned.status = "processing"
            abandoned.started_at = lock_now - timedelta(minutes=20)
            abandoned.finished_at = None
            await db.commit()
        source.calls = 0

        async def retry() -> TrendRun:
            async with get_session_factory()() as db:
                return await TrendService(db, (source,), now=lock_now).refresh(
                    workspace_id=workspace_id, region="HN", category="lock"
                )

        retried_a, retried_b = await asyncio.gather(retry(), retry())
        assert retried_a.id == retried_b.id == abandoned.id
        assert source.calls == 1
    finally:
        await client.aclose()
