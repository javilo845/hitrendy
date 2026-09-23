from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult, valid_result
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendRun,
    TrendRunEvidence,
    WorkspaceTrendRelevance,
)
from app.trends.scoring import score
from app.trends.service import TrendService, canonical_url


@pytest_asyncio.fixture(autouse=True)
async def clean_global_trend_state() -> None:
    """Daily scope identity makes cross-test global runs intentionally reusable."""

    from tests.conftest import _TestingSessionFactory

    async with _TestingSessionFactory() as db:
        for model in (
            TrendRunEvidence,
            TrendItemEvidence,
            TrendEvidence,
            WorkspaceTrendRelevance,
            TrendItem,
            TrendRun,
        ):
            await db.execute(delete(model))
        await db.commit()


@pytest.mark.asyncio
async def test_trend_refresh_publishes_verified_evidence_and_is_idempotent(client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    await client.post(
        "/api/v1/businesses",
        json={
            "name": "Café",
            "category": "gastronomy",
            "country": "HN",
            "city": "Tegucigalpa",
            "primary_product": "café",
            "target_audience": "personas",
            "preferred_platforms": ["instagram"],
            "primary_objective": "sales",
        },
    )
    first = await client.post(
        "/api/v1/trends/refresh", json={"region": "HN", "category": "gastronomy"}
    )
    second = await client.post(
        "/api/v1/trends/refresh", json={"region": "HN", "category": "gastronomy"}
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    listed = await client.get("/api/v1/trends")
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    detail = await client.get(f"/api/v1/trends/{listed.json()['items'][0]['id']}")
    assert detail.status_code == 200 and len(detail.json()["evidence"]) == 2
    assert set(detail.json()) == {
        "id",
        "title",
        "summary",
        "region",
        "category",
        "observed_at",
        "freshness_score",
        "scoring_version",
        "component_scores",
        "total_score",
        "calculated_at",
        "workspace_relevance",
        "evidence",
    }
    assert set(detail.json()["workspace_relevance"]) == {
        "score",
        "component_scores",
        "calculated_at",
    }
    assert all(
        set(evidence)
        == {"source", "source_url", "observed_at", "region", "confidence"}
        for evidence in detail.json()["evidence"]
    )


@pytest.mark.asyncio
async def test_list_filters_are_normalized_like_refresh(client, monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
    await client.post(
        "/api/v1/businesses",
        json={"name": "Café", "category": "gastronomy", "country": "HN", "city": "Tegucigalpa"},
    )
    created = await client.post(
        "/api/v1/trends/refresh", json={"region": "HN", "category": "gastronomy"}
    )
    assert created.status_code == 202
    stored = await client.get("/api/v1/trends")
    assert stored.status_code == 200 and len(stored.json()["items"]) == 1
    identity = stored.json()["items"][0]
    assert identity["region"] == "HN" and identity["category"] == "gastronomy"

    # Every spelling the query contract accepts resolves to one stored identity.
    for query in (
        "region=HN&category=gastronomy",
        "region=hn&category=gastronomy",
        "region=hn&category=GASTRONOMY",
        "region=%20hn%20&category=%20Gastronomy%20",
    ):
        listed = await client.get(f"/api/v1/trends?{query}")
        assert listed.status_code == 200, query
        assert [item["id"] for item in listed.json()["items"]] == [identity["id"]], query

    # Normalization must not widen a filter into an unrelated match.
    for query in ("region=gt&category=gastronomy", "region=hn&category=retail"):
        empty = await client.get(f"/api/v1/trends?{query}")
        assert empty.status_code == 200 and empty.json()["items"] == [], query


@pytest.mark.asyncio
async def test_no_evidence_and_unsafe_urls_never_publish(client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    class Unsafe:
        identifier, public_name, source_type, supported_regions, available = (
            "demo-unsafe",
            "Demo unsafe",
            "demo",
            ("HN",),
            True,
        )

        async def fetch(self, *, region, category):
            candidate = SourceCandidate(
                "No publicar",
                "",
                region,
                category,
                datetime(2026, 1, 1, tzinfo=UTC),
                (SourceEvidence("javascript:alert(1)", datetime(2026, 1, 1, tzinfo=UTC), region),),
            )
            from app.trends.contracts import SourceFetchResult

            return SourceFetchResult("success", (candidate,))

    from tests.conftest import _TestingSessionFactory

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        service = TrendService(db, (Unsafe(),))
        run = await service.refresh(workspace_id="ws_test_001", region="HN", category="gastronomy")
        assert run.status == "failed"
        assert run.sources_succeeded == "[]" and run.sources_failed == '["demo-unsafe"]'
        assert not (
            await db.scalars(select(TrendItem).where(TrendItem.title == "No publicar"))
        ).all()
    assert canonical_url("file:///tmp/x") is None and canonical_url("data:text/plain,x") is None
    assert canonical_url("https://user:pass@example.invalid/evidence") is None


@pytest.mark.asyncio
async def test_refresh_idempotency_replays_and_rejects_payload_conflict(client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    await client.post(
        "/api/v1/businesses",
        json={"name": "Café", "category": "gastronomy", "country": "HN", "city": "Tegucigalpa"},
    )
    headers = {"Idempotency-Key": "trend-replay-key"}
    first = await client.post("/api/v1/trends/refresh", json={"region": "HN"}, headers=headers)
    replay = await client.post("/api/v1/trends/refresh", json={"region": "HN"}, headers=headers)
    conflict = await client.post(
        "/api/v1/trends/refresh", json={"region": "GLOBAL"}, headers=headers
    )
    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_http_failed_refresh_key_is_retryable_until_a_run_completes(client, monkeypatch) -> None:
    from app.conversations.models import IdempotencyRecord
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    await client.post(
        "/api/v1/businesses",
        json={"name": "Café", "category": "gastronomy", "country": "HN", "city": "Tegucigalpa"},
    )

    class Failing:
        identifier, public_name, source_type, supported_regions, available = (
            "demo-idempotency-retry", "Demo", "demo", ("HN",), True
        )

        async def fetch(self, **kwargs):
            return SourceFetchResult("error")

    class Working(Failing):
        async def fetch(self, *, region, category):
            observed = datetime.now(UTC)
            return SourceFetchResult("success", (SourceCandidate(
                "Recuperación idempotente", "", region, category, observed,
                (SourceEvidence("https://demo.invalid/idempotency-retry", observed, region, 0.8),),
            ),))

    headers = {"Idempotency-Key": "trend-failed-retry-key"}
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (Failing(),))
    failed = await client.post("/api/v1/trends/refresh", json={"region": "HN"}, headers=headers)
    assert failed.status_code == 202 and failed.json()["status"] == "failed"
    async with _TestingSessionFactory() as db:
        record = await db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == headers["Idempotency-Key"]))
        assert record is not None and record.status == "failed" and record.response_json is None

    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (Working(),))
    recovered = await client.post("/api/v1/trends/refresh", json={"region": "HN"}, headers=headers)
    assert recovered.status_code == 202 and recovered.json()["status"] == "completed"
    async with _TestingSessionFactory() as db:
        record = await db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == headers["Idempotency-Key"]))
        assert record is not None and record.status == "completed" and record.response_json is not None


@pytest.mark.asyncio
async def test_capability_blocks_demo_in_production_and_when_disabled(client, monkeypatch) -> None:
    from app.core.capabilities import Capability, CapabilityRegistry, CapabilityStatus
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", False)
    assert CapabilityRegistry().get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.DISABLED
    assert (await client.post("/api/v1/trends/refresh", json={"region": "HN"})).status_code == 503
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "app_env", "production")
    assert CapabilityRegistry().get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.UNCONFIGURED
    assert (await client.post("/api/v1/trends/refresh", json={"region": "HN"})).status_code == 503


@pytest.mark.asyncio
async def test_demo_sources_are_never_executed_in_staging(monkeypatch) -> None:
    from app.core.config import settings
    from app.core.errors import AppError
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "app_env", "staging")
    async with _TestingSessionFactory() as db:
        with pytest.raises(AppError) as failure:
            await TrendService(db).refresh(workspace_id="ws_test_001", region="HN", category=None)
    assert failure.value.status_code == 503


def test_global_scoring_is_exact_and_independent_of_workspace_request() -> None:
    now = datetime(2026, 1, 15, 13, tzinfo=UTC)
    first = score(
        observed_at=datetime(2026, 1, 15, 12, tzinfo=UTC), evidence_count=2, source_count=2, now=now
    )
    second = score(
        observed_at=datetime(2026, 1, 15, 12, tzinfo=UTC), evidence_count=2, source_count=2, now=now
    )
    assert first == second
    assert set(first[0]) == {"freshness", "evidence", "source_diversity"}


@pytest.mark.asyncio
async def test_normalized_titles_group_only_exact_normalizations(monkeypatch) -> None:
    from app.core.config import settings
    from app.trends.contracts import SourceFetchResult
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    now = datetime.now(UTC)

    class Source:
        source_type, supported_regions, available = "demo", ("HN",), True

        def __init__(self, identifier: str, title: str, url: str) -> None:
            self.identifier, self.public_name, self.title, self.url = identifier, identifier, title, url

        async def fetch(self, *, region, category):
            return SourceFetchResult("success", (SourceCandidate(
                self.title, "", region, category, now, (SourceEvidence(self.url, now, region, 0.8),)
            ),))

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        sources = (
            Source("demo-one", "Tema local", "https://demo.invalid/one"),
            Source("demo-two", "tema local!", "https://demo.invalid/two"),
            Source("demo-three", "Tema local nuevo", "https://demo.invalid/three"),
        )
        await TrendService(db, tuple(reversed(sources))).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        items = (await db.scalars(select(TrendItem).order_by(TrendItem.title))).all()
        assert [item.title for item in items] == ["Tema local", "Tema local nuevo"]
        merged = next(item for item in items if item.title == "Tema local")
        assert len((await db.scalars(
            select(TrendEvidence)
            .join(TrendItemEvidence)
            .where(TrendItemEvidence.trend_item_id == merged.id)
        )).all()) == 2


@pytest.mark.asyncio
async def test_group_key_uses_normalized_region_and_category(monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    observed = datetime(2026, 1, 5, 12, tzinfo=UTC)

    class Source:
        source_type, supported_regions, available = "demo", ("HN",), True

        def __init__(self, identifier: str, region: str, category: str, url: str) -> None:
            self.identifier, self.public_name = identifier, identifier
            self.region, self.category, self.url = region, category, url

        async def fetch(self, **kwargs):
            return SourceFetchResult("success", (SourceCandidate(
                "Tema normalizado", "", self.region, self.category, observed,
                (SourceEvidence(self.url, observed, self.region, 0.8),),
            ),))

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        await TrendService(db, (Source("demo-normal-one", " HN ", " Gastronomy ", "https://demo.invalid/normal-one"),), now=observed).refresh(
            workspace_id="ws_test_001", region=" HN ", category="Gastronomy"
        )
        await TrendService(db, (Source("demo-normal-two", "hn", "gastronomy", "https://demo.invalid/normal-two"),), now=observed + timedelta(days=1)).refresh(
            workspace_id="ws_test_001", region="hn", category="gastronomy"
        )
        items = (await db.scalars(select(TrendItem).where(TrendItem.title == "Tema normalizado"))).all()
        assert len(items) == 1
        assert items[0].region == "HN" and items[0].category == "gastronomy"
        mismatched = await TrendService(
            db,
            (Source("demo-normal-mismatch", "HN", "retail", "https://demo.invalid/normal-mismatch"),),
            now=observed + timedelta(days=2),
        ).refresh(workspace_id="ws_test_001", region="HN", category="gastronomy")
        assert mismatched.status == "failed"
        assert len((await db.scalars(select(TrendItem).where(TrendItem.title == "Tema normalizado"))).all()) == 1


@pytest.mark.asyncio
async def test_adapter_failures_are_isolated_and_run_evidence_is_traceable(monkeypatch) -> None:
    from app.core.config import settings
    from app.trends.contracts import SourceFetchResult
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)

    class Broken:
        identifier, public_name, source_type, supported_regions, available = "demo-broken", "Demo", "demo", ("HN",), True

        async def fetch(self, **kwargs):
            raise TimeoutError()

    class Invalid:
        identifier, public_name, source_type, supported_regions, available = "demo-invalid", "Demo", "demo", ("HN",), True

        async def fetch(self, **kwargs):
            return object()

    class Good:
        identifier, public_name, source_type, supported_regions, available = "demo-good", "Demo", "demo", ("HN",), True

        async def fetch(self, *, region, category):
            now = datetime.now(UTC)
            return SourceFetchResult("success", (SourceCandidate("Tema", "", region, category, now, (SourceEvidence("https://demo.invalid/a", now, region, .8),)),))

    async with _TestingSessionFactory() as db:
        run = await TrendService(db, (Broken(), Invalid(), Good())).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert run.status == "partial"
        succeeded, failed = set(json.loads(run.sources_succeeded)), set(json.loads(run.sources_failed))
        assert succeeded == {"demo-good"}
        assert {"demo-broken", "demo-invalid"}.issubset(failed)
        assert not (succeeded & failed)
        assert len((await db.scalars(
            select(TrendRunEvidence).where(TrendRunEvidence.trend_run_id == run.id)
        )).all()) == 1


@pytest.mark.asyncio
async def test_one_observation_can_link_to_distinct_items(monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    observed = datetime(2026, 1, 5, 12, tzinfo=UTC)

    class SharedEvidence:
        identifier, public_name, source_type, supported_regions, available = "demo-shared", "Demo", "demo", ("HN",), True

        async def fetch(self, *, region, category):
            evidence = SourceEvidence("https://demo.invalid/shared", observed, region, 0.8)
            return SourceFetchResult("success", (
                SourceCandidate("Tema A", "", region, category, observed, (evidence,)),
                SourceCandidate("Tema B", "", region, category, observed, (evidence,)),
            ))

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        await TrendService(db, (SharedEvidence(),), now=observed).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert len((await db.scalars(select(TrendItem))).all()) == 2
        assert len((await db.scalars(select(TrendEvidence))).all()) == 1
        assert len((await db.scalars(select(TrendItemEvidence))).all()) == 2


@pytest.mark.asyncio
async def test_incoherent_evidence_is_discarded_without_losing_valid_evidence(monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    observed = datetime(2026, 1, 5, 12, tzinfo=UTC)

    class Mixed:
        identifier, public_name, source_type, supported_regions, available = "demo-mixed", "Demo", "demo", ("HN",), True

        async def fetch(self, *, region, category):
            return SourceFetchResult("success", (SourceCandidate(
                "Tema coherente", "", region, category, observed,
                (
                    SourceEvidence("https://demo.invalid/valid", observed, "HN", 0.8),
                    SourceEvidence("https://demo.invalid/region", observed, "BR", 0.8),
                    SourceEvidence("https://demo.invalid/window", observed + timedelta(days=7), "HN", 0.8),
                ),
            ),))

    async with _TestingSessionFactory() as db:
        run = await TrendService(db, (Mixed(),), now=observed).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert run.status == "partial"
        assert len((await db.scalars(
            select(TrendEvidence).where(TrendEvidence.canonical_url == "https://demo.invalid/valid")
        )).all()) == 1


@pytest.mark.asyncio
async def test_http_refresh_recovers_after_runtime_provider_error(client, monkeypatch) -> None:
    from app.core.capabilities import Capability, CapabilityStatus, get_runtime_capability_registry
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    registry = get_runtime_capability_registry()
    registry._outcome_store.clear(Capability.TREND_ANALYSIS)
    await client.post(
        "/api/v1/businesses",
        json={"name": "Café", "category": "gastronomy", "country": "HN", "city": "Tegucigalpa"},
    )

    class Failing:
        identifier, public_name, source_type, supported_regions, available = "demo-recovery", "Demo", "demo", ("HN",), True

        async def fetch(self, **kwargs):
            return SourceFetchResult("error")

    class Working(Failing):
        async def fetch(self, *, region, category):
            now = datetime.now(UTC)
            return SourceFetchResult("success", (SourceCandidate(
                "Recuperado", "", region, category, now,
                (SourceEvidence("https://demo.invalid/recovered", now, region, 0.8),),
            ),))

    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (Failing(),))
    failed = await client.post("/api/v1/trends/refresh", json={"region": "HN"})
    assert failed.status_code == 202 and failed.json()["status"] == "failed"
    assert registry.get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.ERROR
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (Working(),))
    recovered = await client.post("/api/v1/trends/refresh", json={"region": "HN"})
    assert recovered.status_code == 202 and recovered.json()["status"] == "completed"
    assert registry.get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.AVAILABLE


@pytest.mark.asyncio
async def test_http_processing_run_never_completes_idempotency_early(client, monkeypatch) -> None:
    from app.conversations.models import IdempotencyRecord
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    await client.post(
        "/api/v1/businesses",
        json={"name": "Café", "category": "gastronomy", "country": "HN", "city": "Tegucigalpa"},
    )
    calls = 0

    class Counting:
        identifier, public_name, source_type, supported_regions, available = "demo-processing", "Demo", "demo", ("HN",), True

        async def fetch(self, *, region, category):
            nonlocal calls
            calls += 1
            now = datetime.now(UTC)
            return SourceFetchResult("success", (SourceCandidate(
                "Procesando", "", region, category, now,
                (SourceEvidence("https://demo.invalid/processing", now, region, 0.8),),
            ),))

    source = Counting()
    monkeypatch.setattr("app.trends.service.default_fake_sources", lambda: (source,))
    first = await client.post("/api/v1/trends/refresh", json={"region": "HN", "category": "processing"})
    assert first.status_code == 202
    async with _TestingSessionFactory() as db:
        run = await db.get(TrendRun, first.json()["id"])
        assert run is not None
        run.status, run.started_at, run.finished_at = "processing", datetime.now(UTC), None
        await db.commit()
    calls = 0
    headers = {"Idempotency-Key": "processing-run-key"}
    blocked = await client.post(
        "/api/v1/trends/refresh", json={"region": "HN", "category": "processing"}, headers=headers
    )
    assert blocked.status_code == 202
    assert blocked.json()["status"] == "processing"
    assert blocked.json()["refresh_allowed"] is False
    assert blocked.json()["next_refresh_at"] is not None
    assert calls == 0
    async with _TestingSessionFactory() as db:
        record = await db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == "processing-run-key"))
        assert record is not None
        assert record.status == "completed"
        assert json.loads(record.response_json) == blocked.json()
        run = await db.get(TrendRun, first.json()["id"])
        assert run is not None
        run.status, run.finished_at = "completed", datetime.now(UTC)
        await db.commit()
    retry = await client.post(
        "/api/v1/trends/refresh", json={"region": "HN", "category": "processing"}, headers=headers
    )
    assert retry.status_code == 202 and retry.json()["id"] == first.json()["id"]


def test_adapter_contract_discards_invalid_nested_candidates() -> None:
    observed = datetime(2026, 1, 5, tzinfo=UTC)
    valid = SourceCandidate("Válido", "", "HN", None, observed, (
        SourceEvidence("https://demo.invalid/ok", observed, "HN", 0.8),
    ))
    invalid_evidence = SourceCandidate("Malo", "", "HN", None, observed, (object(),))
    invalid_confidence = SourceCandidate("Malo", "", "HN", None, observed, (
        SourceEvidence("https://demo.invalid/bad", observed, "HN", "0.8"),
    ))
    naive = SourceCandidate("Malo", "", "HN", None, datetime(2026, 1, 5), ())
    invalid_title = SourceCandidate(123, "", "HN", None, observed, ())
    result = valid_result(SourceFetchResult("success", (valid, invalid_evidence, invalid_confidence, naive, invalid_title)))
    assert result is not None and result.invalid_candidates
    assert result.result.candidates == (valid,)
    assert valid_result(SourceFetchResult("success", object())) is None


@pytest.mark.asyncio
async def test_temporal_grouping_reobservation_and_freshness(monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)

    class Source:
        source_type, supported_regions, available = "demo", ("HN",), True

        def __init__(self, identifier: str, observed: datetime, url: str) -> None:
            self.identifier, self.public_name, self.observed, self.url = identifier, identifier, observed, url

        async def fetch(self, *, region, category):
            return SourceFetchResult("success", (SourceCandidate(
                "Tema temporal", "", region, category, self.observed,
                (SourceEvidence(self.url, self.observed, region, 0.8),),
            ),))

    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        old = datetime(2026, 1, 2, 12, tzinfo=UTC)
        first_now = datetime(2026, 1, 3, 12, tzinfo=UTC)
        recent = datetime(2026, 1, 4, 12, tzinfo=UTC)
        first = await TrendService(db, (Source("demo-old", old, "https://demo.invalid/time-old"),), now=first_now).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        item = await db.scalar(select(TrendItem).where(TrendItem.id.is_not(None)))
        assert item is not None and item.observed_at.replace(tzinfo=UTC) == old
        old_freshness = item.freshness_score
        await TrendService(
            db,
            (
                Source("demo-old", old, "https://demo.invalid/time-old"),
                Source("demo-new", recent, "https://demo.invalid/time-new"),
            ),
            now=recent,
        ).refresh(workspace_id="ws_test_001", region="HN", category=None)
        await db.refresh(item)
        assert item.observed_at.replace(tzinfo=UTC) == recent and item.freshness_score > old_freshness
        later = datetime(2026, 1, 10, 12, tzinfo=UTC)
        second = await TrendService(db, (Source("demo-old", later, "https://demo.invalid/time-old"),), now=later).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert first.id != second.id
        assert len((await db.scalars(select(TrendItem).where(TrendItem.title == "Tema temporal"))).all()) == 2
        assert len((await db.scalars(select(TrendEvidence).where(TrendEvidence.canonical_url == "https://demo.invalid/time-old"))).all()) == 2


@pytest.mark.asyncio
async def test_same_window_reobservation_updates_evidence_and_item_freshness(monkeypatch) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)

    class Source:
        identifier, public_name, source_type, supported_regions, available = (
            "demo-same-window", "Demo", "demo", ("HN",), True
        )

        def __init__(self, observed: datetime, confidence: float) -> None:
            self.observed, self.confidence = observed, confidence

        async def fetch(self, *, region, category):
            return SourceFetchResult("success", (SourceCandidate(
                "Tema reobservado", "", region, category, self.observed,
                (SourceEvidence("https://demo.invalid/same-window", self.observed, region, self.confidence),),
            ),))

    monday = datetime(2026, 1, 5, 12, tzinfo=UTC)
    friday = datetime(2026, 1, 9, 12, tzinfo=UTC)
    async with _TestingSessionFactory() as db:
        await db.execute(delete(TrendRunEvidence))
        await db.execute(delete(TrendItemEvidence))
        await db.execute(delete(TrendEvidence))
        await db.execute(delete(WorkspaceTrendRelevance))
        await db.execute(delete(TrendItem))
        await db.execute(delete(TrendRun))
        await db.commit()
        await TrendService(db, (Source(monday, 0.4),), now=friday + timedelta(hours=1)).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        item = await db.scalar(select(TrendItem).where(TrendItem.title == "Tema reobservado"))
        assert item is not None
        prior_freshness = item.freshness_score
        await TrendService(db, (Source(friday, 0.9),), now=friday + timedelta(days=1, hours=1)).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        await db.refresh(item)
        evidence = await db.scalar(select(TrendEvidence).where(TrendEvidence.canonical_url == "https://demo.invalid/same-window"))
        assert evidence is not None
        assert evidence.observed_at.replace(tzinfo=UTC) == friday and evidence.confidence == 0.9
        assert item.observed_at.replace(tzinfo=UTC) == friday and item.freshness_score > prior_freshness
        observations = (
            await db.scalars(
                select(TrendEvidence).where(
                    TrendEvidence.canonical_url == "https://demo.invalid/same-window"
                )
            )
        ).all()
        assert len(observations) == 1
        run_links = (
            await db.scalars(
                select(TrendRunEvidence).where(TrendRunEvidence.trend_evidence_id == evidence.id)
            )
        ).all()
        assert len(run_links) == 2


@pytest.mark.asyncio
async def test_retry_resets_abandoned_run_and_records_capability_outcomes(monkeypatch) -> None:
    from app.core.capabilities import Capability, CapabilityStatus, get_runtime_capability_registry
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    registry = get_runtime_capability_registry()
    registry._outcome_store.clear(Capability.TREND_ANALYSIS)
    now = datetime(2026, 1, 5, 12, tzinfo=UTC)

    class Good:
        identifier, public_name, source_type, supported_regions, available = "demo-good-retry", "Demo", "demo", ("HN",), True

        async def fetch(self, *, region, category):
            return SourceFetchResult("success", (SourceCandidate(
                "Retry", "", region, category, now, (SourceEvidence("https://demo.invalid/retry", now, region, 0.8),),
            ),))

    class Timeout:
        identifier, public_name, source_type, supported_regions, available = "demo-timeout-retry", "Demo", "demo", ("HN",), True

        async def fetch(self, **kwargs):
            raise TimeoutError()

    async with _TestingSessionFactory() as db:
        partial = await TrendService(db, (Good(), Timeout()), now=now, capability_registry=registry).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert partial.status == "partial"
        assert registry.get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.DEGRADED
        recovered = await TrendService(db, (Good(),), now=now + timedelta(days=1), capability_registry=registry).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert recovered.status == "completed"
        assert registry.get_capability(Capability.TREND_ANALYSIS).status == CapabilityStatus.AVAILABLE
        recovered.status = "processing"
        recovered.started_at = now - timedelta(minutes=20)
        recovered.sources_succeeded = '["stale"]'
        recovered.sources_failed = '["stale"]'
        recovered.public_error = "stale"
        recovered.finished_at = now
        await db.commit()
        retry_now = now + timedelta(days=1)
        retried = await TrendService(db, (Good(),), now=retry_now, capability_registry=registry).refresh(
            workspace_id="ws_test_001", region="HN", category=None
        )
        assert retried.id == recovered.id and retried.started_at == retry_now
        assert retried.sources_failed == "[]" and retried.public_error is None
