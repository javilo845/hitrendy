"""WAVE-010C: external daily jobs, cooldown and the aggregated Home contract."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.business.models import Business
from app.conversations.models import IdempotencyRecord
from app.core.capabilities import Capability, get_runtime_capability_registry
from app.core.config import Settings, settings
from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult
from app.trends.jobs import run_due
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendRun,
    TrendRunEvidence,
    WorkspaceTrendRelevance,
)
from app.trends.service import (
    ABANDONED_PROCESSING_AFTER,
    EMPTY_RUN_MESSAGE,
    TrendService,
)
from tests.conftest import _TestingSessionFactory


@pytest_asyncio.fixture(autouse=True)
async def clean_trend_jobs_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    get_runtime_capability_registry()._outcome_store.clear(Capability.TREND_ANALYSIS)
    async with _TestingSessionFactory() as db:
        for model in (
            TrendRunEvidence,
            TrendItemEvidence,
            TrendEvidence,
            WorkspaceTrendRelevance,
            TrendItem,
            TrendRun,
            Business,
        ):
            await db.execute(delete(model))
        await db.commit()


class CountingSource:
    identifier = "demo-job-counting"
    public_name = "Fuente diaria"
    source_type = "demo"
    supported_regions = ("HN", "GLOBAL")
    supported_categories: tuple[str, ...] = ()
    available = True

    def __init__(
        self,
        *,
        status: str = "success",
        observed_at: datetime | None = None,
        identifier: str | None = None,
    ) -> None:
        if identifier is not None:
            self.identifier = identifier
            self.public_name = f"Fuente {identifier}"
        self.status = status
        self.observed_at = observed_at or datetime.now(UTC)
        self.calls = 0
        self.quota_reservations = 0

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        self.calls += 1
        self.quota_reservations += 1
        if self.status != "success":
            return SourceFetchResult(self.status)
        return SourceFetchResult(
            "success",
            (
                SourceCandidate(
                    "Café frío local",
                    "Interés observado en contenido de café frío.",
                    region,
                    category,
                    self.observed_at,
                    (
                        SourceEvidence(
                            "https://example.test/trends/cafe-frio",
                            self.observed_at,
                            region,
                            0.8,
                        ),
                    ),
                ),
            ),
        )


async def _business(workspace_id: str, *, category: str = "gastronomy") -> None:
    async with _TestingSessionFactory() as db:
        db.add(
            Business(
                id=f"biz_{workspace_id}",
                workspace_id=workspace_id,
                name=f"Negocio {workspace_id}",
                category=category,
                country="HN",
                city="Tegucigalpa",
                primary_product="Café",
                target_audience="Clientes locales",
                preferred_platforms='["instagram"]',
                primary_objective="sales",
            )
        )
        await db.commit()


def _business_payload() -> dict[str, object]:
    return {
        "name": "Café",
        "category": "gastronomy",
        "country": "HN",
        "city": "Tegucigalpa",
        "primary_product": "Café",
        "target_audience": "Clientes locales",
        "preferred_platforms": ["instagram"],
        "primary_objective": "sales",
    }


@pytest.mark.asyncio
async def test_run_due_is_daily_global_and_reuses_collection_for_all_workspaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = CountingSource()
    await _business("ws_test_001")
    await _business("ws_other", category="retail")
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (source,))
    scopes = ({"region": "HN", "category": None},)

    first = await run_due(session_factory=_TestingSessionFactory, scopes=scopes)
    second = await run_due(session_factory=_TestingSessionFactory, scopes=scopes)

    assert source.calls == 1
    assert first.scopes[0].run_id == second.scopes[0].run_id
    assert first.workspaces_scored == second.workspaces_scored == 2
    async with _TestingSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(TrendRun)) == 1
        scores = (
            await db.scalars(
                select(WorkspaceTrendRelevance).order_by(
                    WorkspaceTrendRelevance.workspace_id
                )
            )
        ).all()
        assert {score.workspace_id for score in scores} == {"ws_other", "ws_test_001"}


@pytest.mark.asyncio
async def test_private_relevance_never_fetches_again() -> None:
    source = CountingSource()
    await _business("ws_test_001")
    async with _TestingSessionFactory() as db:
        service = TrendService(db, (source,))
        await service.collect(region="HN", category=None)
        assert source.calls == 1
        await service.compute_workspace_relevance("ws_test_001")
        await service.compute_workspace_relevance("ws_test_001")
        await db.commit()
        assert source.calls == 1
        assert (
            await db.scalar(
                select(func.count()).select_from(WorkspaceTrendRelevance)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_failed_and_abandoned_daily_runs_are_retryable() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    source = CountingSource(status="error", observed_at=now)
    async with _TestingSessionFactory() as db:
        first = await TrendService(db, (source,), now=now).collect(
            region="HN", category=None
        )
        assert first.status == "failed"
        source.status = "success"
        retried = await TrendService(db, (source,), now=now).collect(
            region="HN", category=None
        )
        assert retried.id == first.id and retried.status == "completed"
        assert source.calls == 2

        retried.status = "processing"
        retried.started_at = now - ABANDONED_PROCESSING_AFTER - timedelta(seconds=1)
        retried.finished_at = None
        await db.commit()
        recovered = await TrendService(db, (source,), now=now).collect(
            region="HN", category=None
        )
        assert recovered.id == first.id and recovered.status == "completed"
        assert source.calls == 3


@pytest.mark.asyncio
async def test_manual_cooldown_blocks_fetch_and_is_shared_between_sessions(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = CountingSource()
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (source,))
    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201
    first = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    async with _TestingSessionFactory() as second_session:
        allowed, next_refresh_at, same_run = await TrendService(
            second_session, (source,)
        ).manual_refresh_availability(region="HN", category="gastronomy")
    cooldown_headers = {"Idempotency-Key": "cooldown-replay"}
    second = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
        headers=cooldown_headers,
    )
    replay = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
        headers=cooldown_headers,
    )
    conflict = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "GLOBAL", "category": "gastronomy"},
        headers=cooldown_headers,
    )
    concurrent = await asyncio.gather(
        *(
            client.post(
                "/api/v1/trends/refresh",
                json={"region": "HN", "category": "gastronomy"},
                headers={"Idempotency-Key": "cooldown-concurrent"},
            )
            for _ in range(2)
        )
    )

    assert first.status_code == second.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == second.json()
    assert conflict.status_code == 409
    assert 202 in {response.status_code for response in concurrent}
    assert all(response.status_code in {202, 409} for response in concurrent)
    assert source.calls == 1
    assert source.quota_reservations == 1
    assert allowed is False and next_refresh_at is not None
    assert same_run is not None and same_run.id == first.json()["id"]
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["refresh_allowed"] is False
    assert second.json()["retry_after_seconds"] > 0
    async with _TestingSessionFactory() as db:
        records = (
            await db.scalars(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.endpoint == "POST:/trends/refresh",
                    IdempotencyRecord.key.in_(
                        ("cooldown-replay", "cooldown-concurrent")
                    ),
                )
            )
        ).all()
        assert len(records) == 2
        assert all(record.status == "completed" for record in records)
        assert json.loads(
            next(
                record.response_json
                for record in records
                if record.key == "cooldown-replay"
            )
        ) == second.json()


@pytest.mark.asyncio
async def test_source_quota_failure_is_retryable_and_is_not_a_cooldown(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = CountingSource(status="quota_exhausted")
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (source,))
    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201

    failed = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    assert failed.status_code == 202
    assert failed.json()["status"] == "failed"
    assert failed.json()["refresh_allowed"] is True
    assert failed.json()["next_refresh_at"] is None

    source.status = "success"
    retried = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
        headers={"Idempotency-Key": "quota-is-not-cooldown"},
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "completed"
    assert source.calls == source.quota_reservations == 2


def test_scheduled_scopes_and_cooldown_are_bounded_server_configuration() -> None:
    configured = Settings(
        {
            "TRENDS_SCHEDULED_SCOPES": (
                '[{"region":"hn","category":"gastronomy"},'
                '{"region":"GLOBAL","category":null}]'
            ),
            "TRENDS_MANUAL_COOLDOWN_SECONDS": "600",
            "TRENDS_STALE_AFTER_SECONDS": "172800",
        }
    )
    assert configured.trends_scheduled_scopes == (
        {"region": "HN", "category": "gastronomy"},
        {"region": "GLOBAL", "category": None},
    )
    assert configured.trends_manual_cooldown_seconds == 600
    with pytest.raises(RuntimeError):
        Settings(
            {
                "TRENDS_SCHEDULED_SCOPES": (
                    '[{"region":"HN","category":null},'
                    '{"region":"HN","category":null}]'
                )
            }
        )


@pytest.mark.asyncio
async def test_home_contract_is_fresh_verifiable_and_workspace_scoped(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = CountingSource()
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (source,))
    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201
    refreshed = await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    assert refreshed.status_code == 202, refreshed.text
    assert refreshed.json()["status"] == "completed"
    response = await client.get("/api/v1/trends/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "fresh"
    assert payload["updated_at"] is not None
    assert payload["refresh_allowed"] is False
    assert len(payload["items"]) == 1
    card = payload["items"][0]
    assert card["freshness"] == "fresh"
    assert card["workspace_relevance"]["score"] >= 0
    assert card["evidence"] == [
        {
            "source": source.identifier,
            "source_name": source.public_name,
            "source_url": "https://example.test/trends/cafe-frio",
            "observed_at": source.observed_at.isoformat(),
        }
    ]
    async with _TestingSessionFactory() as db:
        assert (
            await TrendService(db, sources=()).detail(
                workspace_id="ws_not_visible",
                trend_id=card["id"],
            )
            is None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "app_env", "expected"),
    [
        (False, "test", "disabled"),
        (True, "production", "unconfigured"),
    ],
)
async def test_home_reports_disabled_and_unconfigured_without_fake_trends(
    client,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    app_env: str,
    expected: str,
) -> None:
    monkeypatch.setattr(settings, "trend_analysis_enabled", enabled)
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "youtube_trends_enabled", False)
    monkeypatch.setattr(settings, "serpapi_trends_enabled", False)
    monkeypatch.setattr(settings, "rss_trends_enabled", False)
    response = await client.get("/api/v1/trends/home")
    assert response.status_code == 200
    assert response.json()["status"] == expected
    assert response.json()["items"] == []
    assert response.json()["refresh_allowed"] is False


@pytest.mark.asyncio
async def test_home_reports_stale_empty_and_partial_degradation(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201
    empty = CountingSource(status="empty")
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (empty,))
    await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    assert (await client.get("/api/v1/trends/home")).json()["status"] == "empty"

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendRun))
        await db.commit()
    stale = CountingSource(observed_at=datetime.now(UTC) - timedelta(days=3))
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (stale,))
    await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    stale_home = (await client.get("/api/v1/trends/home")).json()
    assert stale_home["status"] == "stale"
    assert stale_home["items"][0]["freshness"] == "stale"

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendRun))
        await db.commit()
    failing = CountingSource(status="timeout", identifier="demo-job-timeout")
    monkeypatch.setattr(
        "app.trends.service.default_fake_sources",
        lambda: (CountingSource(identifier="demo-job-good"), failing),
    )
    await client.post(
        "/api/v1/trends/refresh",
        json={"region": "HN", "category": "gastronomy"},
    )
    degraded = (await client.get("/api/v1/trends/home")).json()
    assert degraded["status"] == "degraded"


@pytest.mark.asyncio
async def test_home_ranking_is_private_before_global_score() -> None:
    now = datetime.now(UTC)
    await _business("ws_test_001", category="gastronomy")
    await _business("ws_other", category="retail")
    items = (
        ("gast-low", "gastronomy", 0.20),
        ("gast-lower", "gastronomy", 0.10),
        ("retail-high", "retail", 0.90),
        ("retail-higher", "retail", 0.95),
    )
    async with _TestingSessionFactory() as db:
        for item_id, category, total in items:
            db.add(
                TrendItem(
                    id=item_id,
                    group_key=f"group-{item_id}",
                    observation_window="utc-week-v1:2026-W31",
                    fingerprint=f"fingerprint-{item_id}",
                    title=item_id,
                    summary="Señal persistida.",
                    region="HN",
                    category=category,
                    observed_at=now,
                    freshness_score=1,
                    scoring_version="trend-v1",
                    component_scores="{}",
                    total_score=total,
                    calculated_at=now,
                )
            )
        await db.commit()

        source = CountingSource()
        service = TrendService(db, (source,), now=now)
        await service.compute_workspace_relevance("ws_test_001")
        await service.compute_workspace_relevance("ws_other")
        gastronomy = await service.list(
            workspace_id="ws_test_001",
            region=None,
            category=None,
            limit=2,
            private_ranked=True,
        )
        retail = await service.list(
            workspace_id="ws_other",
            region=None,
            category=None,
            limit=2,
            private_ranked=True,
        )

    assert [item.category for item in gastronomy] == ["gastronomy", "gastronomy"]
    assert [item.category for item in retail] == ["retail", "retail"]
    assert [item.id for item in gastronomy] != [item.id for item in retail]
    assert source.calls == 0


@pytest.mark.asyncio
async def test_home_aggregates_every_scope_and_declares_only_the_refresh_scope(
    client,
) -> None:
    """Home is aggregated; `refresh_scope` only describes the refresh button."""

    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201
    business_observation = datetime(2026, 7, 30, 10, tzinfo=UTC)
    other_observation = datetime(2026, 7, 31, 9, tzinfo=UTC)
    recent_failure = datetime.now(UTC)
    scopes = (
        ("business-scope-item", "HN", "gastronomy", business_observation),
        ("other-scope-item", "GLOBAL", "retail", other_observation),
    )
    async with _TestingSessionFactory() as db:
        for item_id, region, category, observed_at in scopes:
            db.add(
                TrendItem(
                    id=item_id,
                    group_key=f"group-{item_id}",
                    observation_window="utc-week-v1:2026-W31",
                    fingerprint=f"fingerprint-{item_id}",
                    title=f"Señal {item_id}",
                    summary="Señal visible.",
                    region=region,
                    category=category,
                    observed_at=observed_at,
                    freshness_score=1,
                    scoring_version="trend-v1",
                    component_scores="{}",
                    total_score=0.5,
                    calculated_at=observed_at,
                )
            )
        # A recent failure of the refresh scope must not replace the valid
        # evidence date of the aggregated data.
        db.add(
            TrendRun(
                id="recent-failed-business-scope",
                fingerprint="recent-failed-business-fingerprint",
                window_start=recent_failure.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ),
                region="HN",
                category="gastronomy",
                status="failed",
                sources_attempted='["provider"]',
                sources_succeeded="[]",
                sources_failed='["provider"]',
                public_error="No se pudo obtener evidencia de tendencias.",
                started_at=recent_failure,
                finished_at=recent_failure,
            )
        )
        await db.commit()
        await TrendService(db, sources=()).compute_workspace_relevance("ws_test_001")
        await db.commit()

    response = await client.get("/api/v1/trends/home")
    assert response.status_code == 200
    payload = response.json()

    # The ambiguous top-level scope is gone: only `refresh_scope` remains, and
    # it describes the business, not the cards.
    assert "region" not in payload
    assert "category" not in payload
    assert payload["refresh_scope"] == {"region": "HN", "category": "gastronomy"}

    # Cards from every visible scope are returned, each declaring its own one.
    cards = {card["id"]: card for card in payload["items"]}
    assert set(cards) == {"business-scope-item", "other-scope-item"}
    assert (cards["business-scope-item"]["region"], cards["business-scope-item"]["category"]) == (
        "HN",
        "gastronomy",
    )
    assert (cards["other-scope-item"]["region"], cards["other-scope-item"]["category"]) == (
        "GLOBAL",
        "retail",
    )
    assert any(
        (card["region"], card["category"])
        != (payload["refresh_scope"]["region"], payload["refresh_scope"]["category"])
        for card in payload["items"]
    )

    # `updated_at` is the aggregated maximum of valid data, so the newer
    # out-of-scope observation wins and the recent failure changes nothing.
    assert payload["updated_at"] == other_observation.isoformat()
    assert set(payload) == {
        "status",
        "refresh_scope",
        "updated_at",
        "refresh_allowed",
        "next_refresh_at",
        "sources",
        "items",
    }


@pytest.mark.asyncio
async def test_home_updated_at_uses_visible_or_confirmed_data_only(
    client,
) -> None:
    assert (await client.post("/api/v1/businesses", json=_business_payload())).status_code == 201
    old_observation = datetime(2026, 1, 15, 12, tzinfo=UTC)
    recent_attempt = datetime.now(UTC)
    async with _TestingSessionFactory() as db:
        item = TrendItem(
            id="old-visible-item",
            group_key="old-visible-group",
            observation_window="utc-week-v1:2026-W03",
            fingerprint="old-visible-fingerprint",
            title="Señal antigua",
            summary="Evidencia antigua.",
            region="HN",
            category="gastronomy",
            observed_at=old_observation,
            freshness_score=0,
            scoring_version="trend-v1",
            component_scores="{}",
            total_score=0.2,
            calculated_at=old_observation,
        )
        failed_run = TrendRun(
            id="recent-failed-run",
            fingerprint="recent-failed-fingerprint",
            window_start=recent_attempt.replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
            region="HN",
            category="gastronomy",
            status="failed",
            sources_attempted='["provider"]',
            sources_succeeded="[]",
            sources_failed='["provider"]',
            public_error="No se pudo obtener evidencia de tendencias.",
            started_at=recent_attempt,
            finished_at=recent_attempt,
        )
        db.add_all((item, failed_run))
        await db.commit()
        await TrendService(db, sources=()).compute_workspace_relevance("ws_test_001")
        await db.commit()

    failed_with_old_data = (await client.get("/api/v1/trends/home")).json()
    assert failed_with_old_data["updated_at"] == old_observation.isoformat()
    assert failed_with_old_data["items"][0]["freshness"] == "stale"

    async with _TestingSessionFactory() as db:
        run = await db.get(TrendRun, "recent-failed-run")
        run.status = "completed"
        run.public_error = None
        await db.commit()
    successful = (await client.get("/api/v1/trends/home")).json()
    assert successful["updated_at"] == recent_attempt.isoformat()
    assert successful["items"][0]["freshness"] == "stale"

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendItem).where(TrendItem.id == "old-visible-item"))
        run = await db.get(TrendRun, "recent-failed-run")
        run.status = "failed"
        run.public_error = EMPTY_RUN_MESSAGE
        await db.commit()
    healthy_empty = (await client.get("/api/v1/trends/home")).json()
    assert healthy_empty["status"] == "empty"
    assert healthy_empty["updated_at"] == recent_attempt.isoformat()

    async with _TestingSessionFactory() as db:
        run = await db.get(TrendRun, "recent-failed-run")
        run.public_error = "No se pudo obtener evidencia de tendencias."
        await db.commit()
    failed_without_data = (await client.get("/api/v1/trends/home")).json()
    assert failed_without_data["updated_at"] is None
