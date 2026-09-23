"""WAVE-010B: real-source adapters exercised through HTTP with mock transports."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.capabilities import Capability, CapabilityStatus, get_runtime_capability_registry
from app.core.config import settings
from app.core.ephemeral_store import MemoryEphemeralStore
from app.db.session import get_session_factory
from app.trends.cache import TrendSourceCache
from app.trends.factory import clear_source_outcomes
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendProviderBudget,
    TrendRun,
    TrendRunEvidence,
    WorkspaceTrendRelevance,
)
from app.trends.quota import BudgetPeriod, TrendQuotaBudget
from app.trends.real_sources import RssFeed, RssTrendSource, SerpApiTrendSource, YouTubeTrendSource

from .test_trends_e2e import _workspace_client


@pytest.mark.asyncio
async def test_quota_reservation_is_durable_and_concurrent_across_postgres_sessions() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    factory = get_session_factory()
    quota = TrendQuotaBudget(now=now, session_factory=factory)
    try:
        first, second = await asyncio.gather(
            quota.reserve(
                provider="test-durable-quota", operation="search", period=BudgetPeriod.DAY, budget=1
            ),
            quota.reserve(
                provider="test-durable-quota", operation="search", period=BudgetPeriod.DAY, budget=1
            ),
        )
        assert sorted((first.granted, second.granted)) == [False, True]
        async with factory() as db:
            ledger = await db.scalar(
                select(TrendProviderBudget).where(
                    TrendProviderBudget.provider == "test-durable-quota"
                )
            )
            assert ledger is not None and ledger.consumed == 1
            # A request-local transaction can roll back without refunding a
            # reservation committed before the provider request.
            await db.rollback()
        async with factory() as db:
            durable = await db.scalar(
                select(TrendProviderBudget).where(
                    TrendProviderBudget.provider == "test-durable-quota"
                )
            )
            assert durable is not None and durable.consumed == 1

        lock_was_released = False

        async def youtube_handler(request: httpx.Request) -> httpx.Response:
            nonlocal lock_was_released
            async with factory() as db:
                row = await db.scalar(
                    select(TrendProviderBudget)
                    .where(TrendProviderBudget.provider == "youtube")
                    .with_for_update(nowait=True)
                )
                lock_was_released = row is not None
                await db.rollback()
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": {"videoId": "AbCdEfGhI12"},
                            "snippet": {
                                "title": "Reserva durable",
                                "description": "",
                                "publishedAt": "2026-07-29T10:00:00Z",
                            },
                        }
                    ]
                },
            )

        source = YouTubeTrendSource(
            api_key="test-key",
            daily_budget=1,
            cache_ttl_seconds=60,
            negative_cache_ttl_seconds=10,
            cache=TrendSourceCache(MemoryEphemeralStore(prefix="durable-quota")),
            quota=TrendQuotaBudget(now=now, session_factory=factory),
            now=lambda: now,
            transport=httpx.MockTransport(youtube_handler),
        )
        assert (await source.fetch(region="HN", category=None)).status == "success"
        assert lock_was_released
        async with factory() as db:
            db.add(
                TrendRun(
                    fingerprint=uuid4().hex,
                    window_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
                    region="HN",
                    category=None,
                    status="processing",
                    sources_attempted="[]",
                    sources_succeeded="[]",
                    sources_failed="[]",
                )
            )
            await db.flush()
            await db.rollback()
        async with factory() as db:
            after_rollback = await db.scalar(
                select(TrendProviderBudget).where(TrendProviderBudget.provider == "youtube")
            )
            assert after_rollback is not None and after_rollback.consumed == 1
    finally:
        async with factory() as db:
            await db.execute(
                delete(TrendProviderBudget).where(
                    TrendProviderBudget.provider.in_(("test-durable-quota", "youtube"))
                )
            )
            await db.commit()


@pytest.mark.asyncio
async def test_budget_reduction_is_immediate_and_increase_waits_for_next_period() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    factory = get_session_factory()
    quota = TrendQuotaBudget(now=now, session_factory=factory)
    providers = ("test-budget-reduction", "test-budget-increase")
    try:
        async with factory() as db:
            db.add_all(
                (
                    TrendProviderBudget(
                        provider=providers[0],
                        operation="search",
                        period_start=now.replace(hour=0),
                        period_end=now.replace(hour=0) + timedelta(days=1),
                        budget=200,
                        consumed=150,
                    ),
                    TrendProviderBudget(
                        provider=providers[1],
                        operation="search",
                        period_start=now.replace(hour=0),
                        period_end=now.replace(hour=0) + timedelta(days=1),
                        budget=100,
                        consumed=99,
                    ),
                )
            )
            await db.commit()

        reduced = await quota.reserve(
            provider=providers[0],
            operation="search",
            period=BudgetPeriod.DAY,
            budget=100,
        )
        assert not reduced.granted

        final_original_slot = await quota.reserve(
            provider=providers[1],
            operation="search",
            period=BudgetPeriod.DAY,
            budget=200,
        )
        above_original_budget = await quota.reserve(
            provider=providers[1],
            operation="search",
            period=BudgetPeriod.DAY,
            budget=200,
        )
        assert final_original_slot.granted
        assert not above_original_budget.granted

        async with factory() as db:
            rows = {
                row.provider: row
                for row in (
                    await db.scalars(
                        select(TrendProviderBudget).where(
                            TrendProviderBudget.provider.in_(providers)
                        )
                    )
                ).all()
            }
            assert rows[providers[0]].budget == 200
            assert rows[providers[0]].consumed == 150
            assert rows[providers[1]].budget == 100
            assert rows[providers[1]].consumed == 100
    finally:
        async with factory() as db:
            await db.execute(
                delete(TrendProviderBudget).where(
                    TrendProviderBudget.provider.in_(providers)
                )
            )
            await db.commit()


@pytest.mark.asyncio
async def test_http_refresh_with_mocked_real_sources_persists_attribution_and_partial_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    await clear_source_outcomes()
    monkeypatch.setattr(settings, "youtube_trends_enabled", True)
    monkeypatch.setattr(settings, "youtube_api_key", "test-key")
    monkeypatch.setattr(settings, "serpapi_trends_enabled", True)
    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(settings, "rss_trends_enabled", True)
    monkeypatch.setattr(
        settings,
        "rss_trends_allowlist",
        ({"identifier": "e2e", "public_name": "RSS E2E", "feed_url": "https://feeds.example.com/rss", "regions": ("HN",), "categories": (), "enabled": True},),
    )
    registry = get_runtime_capability_registry()
    registry._outcome_store.clear(Capability.TREND_ANALYSIS)
    client, workspace_id = await _workspace_client(
        suffix="real-sources", category="gastronomy", country="HN"
    )
    observed = datetime.now(UTC) - timedelta(hours=1)
    await TrendQuotaBudget(now=observed, session_factory=get_session_factory()).reserve(
        provider="serpapi", operation="google_trends", period=BudgetPeriod.MONTH, budget=1
    )

    def youtube_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "AbCdEfGhI12"},
                        "snippet": {
                            "title": "Tendencia YouTube",
                            "description": "Señal verificada",
                            "publishedAt": observed.isoformat().replace("+00:00", "Z"),
                        },
                    }
                ]
            },
        )

    def serp_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "monthly credit limit"})

    rss_xml = (
        "<rss><channel><item><title>Tendencia RSS</title>"
        "<link>https://news.example.com/trend</link>"
        f"<pubDate>{format_datetime(observed)}</pubDate>"
        "<description>Fuente permitida</description></item></channel></rss>"
    ).encode()

    def sources(db, *, now=None):
        cache = TrendSourceCache(MemoryEphemeralStore(prefix="e2e-real-sources"))
        quota = TrendQuotaBudget(now=observed, session_factory=get_session_factory())
        return (
            YouTubeTrendSource(
                api_key="test-key", daily_budget=5, cache_ttl_seconds=60,
                negative_cache_ttl_seconds=10, cache=cache, quota=quota,
                now=lambda: observed, transport=httpx.MockTransport(youtube_handler),
            ),
            SerpApiTrendSource(
                api_key="test-key", monthly_budget=1, cache_ttl_seconds=60,
                negative_cache_ttl_seconds=10, cache=cache, quota=quota,
                now=lambda: observed, transport=httpx.MockTransport(serp_handler),
            ),
            RssTrendSource(
                feed=RssFeed("e2e", "RSS E2E", "https://feeds.example.com/rss", ("HN",), ()),
                cache=cache, cache_ttl_seconds=60, negative_cache_ttl_seconds=10,
                timeout_seconds=2, max_results=10, max_response_bytes=10_000,
                resolver=lambda host: ["93.184.216.34"],
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, content=rss_xml, headers={"content-type": "application/rss+xml"}
                    )
                ),
            ),
        )

    monkeypatch.setattr("app.trends.service.configured_trend_sources", sources)
    run_id: str | None = None
    item_ids: list[str] = []
    try:
        refresh = await client.post(
            "/api/v1/trends/refresh",
            json={"region": "HN", "category": "gastronomy"},
            headers={"X-Workspace-Id": workspace_id, "Idempotency-Key": "real-sources-e2e"},
        )
        assert refresh.status_code == 202, refresh.text
        run_id = refresh.json()["id"]
        assert refresh.json()["status"] == "partial"
        assert refresh.json()["sources_succeeded"] == ["rss-e2e", "youtube-search"]
        assert refresh.json()["sources_failed"] == ["serpapi-google-trends"]
        listed = await client.get("/api/v1/trends", headers={"X-Workspace-Id": workspace_id})
        assert listed.status_code == 200 and len(listed.json()["items"]) == 2
        item_ids = [item["id"] for item in listed.json()["items"]]
        detail = await client.get(
            f"/api/v1/trends/{listed.json()['items'][0]['id']}",
            headers={"X-Workspace-Id": workspace_id},
        )
        assert detail.status_code == 200
        assert detail.json()["evidence"][0]["source"] in {"rss-e2e", "youtube-search"}
        assert registry.get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.DEGRADED
        availability = await client.get(
            "/api/v1/trends/sources", headers={"X-Workspace-Id": workspace_id}
        )
        assert availability.status_code == 200
        serpapi = next(
            item for item in availability.json()["sources"] if item["identifier"] == "serpapi-google-trends"
        )
        assert serpapi["status"] == "quota_exhausted"
        assert serpapi["next_reset_at"] is not None
    finally:
        await clear_source_outcomes()
        await client.aclose()
        # E2E shares a migrated database. Remove only this fixture's global
        # observations so later WAVE-010A ordering assertions stay isolated.
        if run_id and item_ids:
            async with get_session_factory()() as db:
                evidence_ids = list(
                    await db.scalars(
                        select(TrendItemEvidence.trend_evidence_id).where(
                            TrendItemEvidence.trend_item_id.in_(item_ids)
                        )
                    )
                )
                await db.execute(delete(TrendRunEvidence).where(TrendRunEvidence.trend_run_id == run_id))
                await db.execute(
                    delete(TrendItemEvidence).where(TrendItemEvidence.trend_item_id.in_(item_ids))
                )
                await db.execute(
                    delete(WorkspaceTrendRelevance).where(
                        WorkspaceTrendRelevance.trend_item_id.in_(item_ids)
                    )
                )
                await db.execute(delete(TrendRun).where(TrendRun.id == run_id))
                if evidence_ids:
                    await db.execute(delete(TrendEvidence).where(TrendEvidence.id.in_(evidence_ids)))
                await db.execute(delete(TrendItem).where(TrendItem.id.in_(item_ids)))
                await db.execute(delete(TrendProviderBudget).where(TrendProviderBudget.provider == "serpapi"))
                await db.commit()
