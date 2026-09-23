"""WAVE-010C PostgreSQL concurrency and workspace isolation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.business.models import Business
from app.core.config import settings
from app.db.session import get_session_factory
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember
from app.main import app
from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult
from app.trends.models import TrendEvidence, TrendItem, TrendRun
from app.trends.service import TrendService


class ConcurrentSource:
    identifier = "demo-wave010c-concurrent"
    public_name = "Fuente concurrente"
    source_type = "demo"
    supported_regions = ("HN", "GLOBAL")
    supported_categories: tuple[str, ...] = ()
    available = True

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        self.calls += 1
        await asyncio.sleep(0.05)
        observed = datetime.now(UTC)
        return SourceFetchResult(
            "success",
            (
                SourceCandidate(
                    "Señal concurrente",
                    "Una única recopilación global.",
                    region,
                    category,
                    observed,
                    (
                        SourceEvidence(
                            "https://example.test/e2e/wave010c",
                            observed,
                            region,
                            0.9,
                        ),
                    ),
                ),
            ),
        )


async def _workspace_client(*, with_business: bool) -> tuple[AsyncClient, str]:
    suffix = uuid4().hex
    workspace_id = f"ws_wave010c_{suffix}"
    user_id = f"usr_wave010c_{suffix}"
    token = f"wave010c-{suffix}"
    async with get_session_factory()() as db:
        db.add_all(
            (
                User(
                    id=user_id,
                    email=f"wave010c-{suffix}@example.com",
                    name="Trend E2E",
                    password_hash="x",
                ),
                Workspace(id=workspace_id, name=f"Trend {suffix[:8]}"),
            )
        )
        await db.flush()
        db.add_all(
            (
                WorkspaceMember(
                    id=f"wsm_wave010c_{suffix}",
                    workspace_id=workspace_id,
                    user_id=user_id,
                ),
                AuthSession(
                    id=f"ses_wave010c_{suffix}",
                    token_hash=sha256(token.encode()).hexdigest(),
                    user_id=user_id,
                    expires_at=datetime.now(UTC) + timedelta(days=365),
                ),
            )
        )
        if with_business:
            db.add(
                Business(
                    id=f"biz_wave010c_{suffix}",
                    workspace_id=workspace_id,
                    name=f"Café {suffix[:8]}",
                    category="gastronomy",
                    country="HN",
                    city="Tegucigalpa",
                    primary_product="Café",
                    target_audience="Clientes locales",
                    preferred_platforms='["instagram"]',
                    primary_objective="sales",
                )
            )
        await db.commit()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set("hitrendy_session", token)
    return client, workspace_id


@pytest.mark.asyncio
async def test_two_workers_collect_once_and_relevance_stays_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    client_a, workspace_a = await _workspace_client(with_business=True)
    client_b, workspace_b = await _workspace_client(with_business=True)
    client_c, workspace_c = await _workspace_client(with_business=False)
    source = ConcurrentSource()

    try:
        async def collect():
            async with get_session_factory()() as db:
                return await TrendService(db, (source,)).collect(
                    region="HN",
                    category="wave010c",
                )

        first, second = await asyncio.gather(collect(), collect())
        assert first.id == second.id
        assert source.calls == 1

        async with get_session_factory()() as db:
            service = TrendService(db, sources=())
            await service.compute_workspace_relevance(workspace_a)
            await service.compute_workspace_relevance(workspace_b)
            await db.commit()
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(TrendRun)
                    .where(
                        TrendRun.region == "HN",
                        TrendRun.category == "wave010c",
                    )
                )
                == 1
            )
        assert source.calls == 1

        listed_a = await client_a.get(
            "/api/v1/trends",
            headers={"X-Workspace-Id": workspace_a},
        )
        listed_b = await client_b.get(
            "/api/v1/trends",
            headers={"X-Workspace-Id": workspace_b},
        )
        trend_id = listed_a.json()["items"][0]["id"]
        assert listed_b.json()["items"][0]["id"] == trend_id
        assert (
            await client_a.get(
                f"/api/v1/trends/{trend_id}",
                headers={"X-Workspace-Id": workspace_a},
            )
        ).status_code == 200
        assert (
            await client_c.get(
                f"/api/v1/trends/{trend_id}",
                headers={"X-Workspace-Id": workspace_c},
            )
        ).status_code == 404

        next_day = first.window_start + timedelta(days=1, hours=12)
        async with get_session_factory()() as db:
            tomorrow = await TrendService(
                db,
                (source,),
                now=next_day,
            ).collect(region="HN", category="wave010c")
        async with get_session_factory()() as db:
            other_region = await TrendService(
                db,
                (source,),
                now=first.window_start + timedelta(hours=12),
            ).collect(region="GLOBAL", category="wave010c")
        async with get_session_factory()() as db:
            other_category = await TrendService(
                db,
                (source,),
                now=first.window_start + timedelta(hours=12),
            ).collect(region="HN", category="wave010c-other")

        assert len({first.id, tomorrow.id, other_region.id, other_category.id}) == 4
        assert source.calls == 4
    finally:
        await client_a.aclose()
        await client_b.aclose()
        await client_c.aclose()
        async with get_session_factory()() as db:
            await db.execute(
                delete(TrendItem).where(TrendItem.category.like("wave010c%"))
            )
            await db.execute(
                delete(TrendEvidence).where(
                    TrendEvidence.source == ConcurrentSource.identifier
                )
            )
            await db.execute(
                delete(TrendRun).where(TrendRun.category.like("wave010c%"))
            )
            await db.execute(
                delete(Workspace).where(
                    Workspace.id.in_((workspace_a, workspace_b, workspace_c))
                )
            )
            await db.commit()
