from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.assets.models  # noqa: F401
import app.business.models  # noqa: F401
import app.conversations.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.images.models  # noqa: F401
import app.projects.models  # noqa: F401
import app.social.models  # noqa: F401
import app.templates.models  # noqa: F401
import app.trends.models  # noqa: F401
import app.videos.models  # noqa: F401
from alembic import command
from app.core.config import settings
from app.db.base import Base
from app.trends.service import TrendService

POSTGRES_URL = os.environ.get(
    "POSTGRES_MIGRATION_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)
_database_name = urlparse(POSTGRES_URL).path.rsplit("/", 1)[-1]
_enabled = os.environ.get("RUN_POSTGRES_MIGRATION_TESTS") == "1"
_safe_database = _database_name.endswith(("_test", "_migration_test"))

pytestmark = pytest.mark.skipif(
    not _enabled or not _safe_database or not POSTGRES_URL.startswith("postgresql"),
    reason=(
        "Prueba PostgreSQL omitida: requiere RUN_POSTGRES_MIGRATION_TESTS=1 y una URL "
        "PostgreSQL cuyo nombre termine en _test o _migration_test."
    ),
)

EXPECTED_TEMPLATE_IDS = {
    "tpl_instagram_01",
    "tpl_instagram_02",
    "tpl_instagram_03",
    "tpl_instagram_04",
    "tpl_instagram_05",
}


@pytest.fixture()
def postgres_engine():
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    previous_url = settings.database_url
    settings.database_url = POSTGRES_URL
    try:
        yield engine
    finally:
        settings.database_url = previous_url
        engine.dispose()


def _alembic_config() -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", POSTGRES_URL.replace("%", "%%"))
    return config


def _upgrade(revision: str) -> None:
    command.upgrade(_alembic_config(), revision)


def _template_ids(engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.scalars(text("SELECT id FROM templates ORDER BY id")))


def _public_template_ids(engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.scalars(text("SELECT id FROM templates WHERE is_public = true ORDER BY id"))
        )


def test_upgrade_empty_postgres_to_head(postgres_engine) -> None:
    _upgrade("head")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "026"
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_jobs')"))
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_budgets')"))
        assert connection.scalar(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='assets' AND column_name='duration_seconds'"
            )
        )
    assert set(_public_template_ids(postgres_engine)) == EXPECTED_TEMPLATE_IDS


def test_trend_framework_upgrade_downgrade_and_reupgrade(postgres_engine) -> None:
    _upgrade("018")
    _upgrade("019")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.trend_items')"))
        assert connection.scalar(text("SELECT to_regclass('public.trend_evidence')"))
        assert connection.scalar(text("SELECT to_regclass('public.trend_item_evidence')"))
        assert connection.scalar(text("SELECT to_regclass('public.trend_run_evidence')"))
    command.downgrade(_alembic_config(), "018")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.trend_items')")) is None
    _upgrade("019")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "019"


def test_trend_framework_schema_matches_the_sqlalchemy_models(postgres_engine) -> None:
    """019/021 own these tables; compare their combined declarative surface."""

    _upgrade("head")
    owned_tables = {
        "trend_runs",
        "trend_items",
        "trend_evidence",
        "trend_item_evidence",
        "trend_run_evidence",
        "workspace_trend_relevance",
    }
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    divergences = [entry for entry in diffs if _diff_table(entry) in owned_tables]
    assert divergences == [], f"019/021 no coinciden con los modelos: {divergences}"


#: Deleted duplicate whose id a stored idempotent refresh response returned.
CONSOLIDATED_RUN_RESPONSE = (
    '{"id": "legacy-failed", "status": "failed", "region": "HN", '
    '"category": "gastronomy", "sources_attempted": ["legacy-rss", "legacy-api"], '
    '"sources_succeeded": [], "sources_failed": ["legacy-rss", "legacy-api"], '
    '"started_at": "2026-07-30T11:00:00+00:00", '
    '"finished_at": "2026-07-30T11:00:00+00:00", "error": null, '
    '"refresh_allowed": true, "next_refresh_at": null, "retry_after_seconds": null}'
)


def _idempotency_records(engine) -> dict[str, dict]:
    with engine.connect() as connection:
        return {
            row["id"]: dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT id, workspace_id, endpoint, key, payload_hash, status,
                           response_json
                    FROM idempotency_records
                    """
                )
            ).mappings()
        }


def test_daily_scope_upgrade_reuses_legacy_run_and_preserves_evidence(
    postgres_engine,
) -> None:
    _upgrade("020")
    observed = datetime(2026, 7, 30, 10, tzinfo=UTC)
    with postgres_engine.begin() as connection:
        # Three duplicates of the same scope/day, each with different sources
        # and its own evidence. `legacy-partial` also carries a malformed
        # legacy array that must degrade instead of aborting the migration.
        connection.execute(
            text(
                """
                INSERT INTO trend_runs (
                    id, fingerprint, region, category, status,
                    sources_attempted, sources_succeeded, sources_failed,
                    started_at, finished_at
                ) VALUES
                    (
                        'legacy-completed', 'legacy-fingerprint-completed',
                        ' hn ', ' Gastronomy ', 'completed',
                        '["legacy-rss"]', '["legacy-rss"]', '[]',
                        :observed, :observed
                    ),
                    (
                        'legacy-failed', 'legacy-fingerprint-failed',
                        'HN', 'gastronomy', 'failed',
                        '["legacy-rss", "legacy-api"]', '[]',
                        '["legacy-rss", "legacy-api"]',
                        :later, :later
                    ),
                    (
                        'legacy-partial', 'legacy-fingerprint-partial',
                        'HN', 'gastronomy', 'partial',
                        '["legacy-video"]', '["legacy-video"]', 'no-es-json',
                        :earlier, :earlier
                    )
                """
            ),
            {
                "observed": observed,
                "later": observed.replace(hour=11),
                "earlier": observed.replace(hour=9),
            },
        )
        evidence_sources = {
            "completed": "legacy-rss",
            "failed": "legacy-rss",
            "partial": "legacy-social",
        }
        for suffix, source in evidence_sources.items():
            connection.execute(
                text(
                    """
                    INSERT INTO trend_evidence (
                        id, source, source_url, canonical_url, observed_at,
                        region, observation_window, confidence,
                        evidence_fingerprint
                    ) VALUES (
                        :id, :source, :url, :url, :observed,
                        'HN', 'utc-week-v1:2026-W31', 0.8, :fingerprint
                    )
                    """
                ),
                {
                    "id": f"evidence-{suffix}",
                    "source": source,
                    "url": f"https://example.test/{suffix}",
                    "observed": observed,
                    "fingerprint": f"evidence-fingerprint-{suffix}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO trend_run_evidence (trend_run_id, trend_evidence_id)
                    VALUES (:run_id, :evidence_id)
                    """
                ),
                {
                    "run_id": f"legacy-{suffix}",
                    "evidence_id": f"evidence-{suffix}",
                },
            )
        # Durable idempotent replays: only the completed refresh response that
        # returned a deleted run may change, and only in its "id" member.
        connection.execute(
            text(
                """
                INSERT INTO idempotency_records (
                    id, workspace_id, endpoint, key, payload_hash, status,
                    response_json
                ) VALUES
                    (
                        'idem-consolidated', 'ws_legacy', 'POST:/trends/refresh',
                        'key-consolidated', 'hash-consolidated', 'completed',
                        :consolidated
                    ),
                    (
                        'idem-survivor', 'ws_legacy', 'POST:/trends/refresh',
                        'key-survivor', 'hash-survivor', 'completed',
                        '{"id": "legacy-completed", "status": "completed"}'
                    ),
                    (
                        'idem-other-endpoint', 'ws_legacy', 'POST:/conversations',
                        'key-other', 'hash-other', 'completed',
                        '{"id": "legacy-failed", "status": "completed"}'
                    ),
                    (
                        'idem-processing', 'ws_legacy', 'POST:/trends/refresh',
                        'key-processing', 'hash-processing', 'processing', NULL
                    ),
                    (
                        'idem-invalid-json', 'ws_legacy', 'POST:/trends/refresh',
                        'key-invalid', 'hash-invalid', 'completed',
                        'no es json'
                    )
                """
            ),
            {"consolidated": CONSOLIDATED_RUN_RESPONSE},
        )
    before = _idempotency_records(postgres_engine)

    _upgrade("021")
    with postgres_engine.connect() as connection:
        runs = (
            connection.execute(
                text(
                    """
                SELECT id, region, category, window_start,
                       sources_attempted, sources_succeeded, sources_failed
                FROM trend_runs
                """
                )
            )
            .mappings()
            .all()
        )
        assert len(runs) == 1
        survivor = runs[0]
        assert survivor["id"] == "legacy-completed"
        assert survivor["region"] == "HN"
        assert survivor["category"] == "gastronomy"
        assert survivor["window_start"] == datetime(2026, 7, 30, tzinfo=UTC)
        # Merged traceability: ordered unions without duplicates, failures
        # exclude whatever ultimately succeeded, and every source behind the
        # evidence linked to the survivor is attempted and succeeded.
        assert json.loads(survivor["sources_attempted"]) == [
            "legacy-api",
            "legacy-rss",
            "legacy-social",
            "legacy-video",
        ]
        assert json.loads(survivor["sources_succeeded"]) == [
            "legacy-rss",
            "legacy-social",
            "legacy-video",
        ]
        assert json.loads(survivor["sources_failed"]) == ["legacy-api"]
        linked_sources = (
            connection.execute(
                text(
                    """
                SELECT DISTINCT trend_evidence.source
                FROM trend_run_evidence
                JOIN trend_evidence
                  ON trend_evidence.id = trend_run_evidence.trend_evidence_id
                WHERE trend_run_evidence.trend_run_id = 'legacy-completed'
                """
                )
            )
            .scalars()
            .all()
        )
        assert set(linked_sources) <= set(json.loads(survivor["sources_attempted"]))
        assert set(linked_sources) <= set(json.loads(survivor["sources_succeeded"]))
        # No evidence row was deleted, renumbered or orphaned.
        assert connection.execute(
            text("SELECT id FROM trend_evidence ORDER BY id")
        ).scalars().all() == ["evidence-completed", "evidence-failed", "evidence-partial"]
        assert connection.execute(
            text(
                """
                    SELECT trend_evidence_id FROM trend_run_evidence
                    WHERE trend_run_id = 'legacy-completed'
                    ORDER BY trend_evidence_id
                    """
            )
        ).scalars().all() == ["evidence-completed", "evidence-failed", "evidence-partial"]
        assert connection.scalar(text("SELECT count(*) FROM trend_run_evidence")) == 3

    after = _idempotency_records(postgres_engine)
    assert set(after) == set(before)
    # Every column except the rewritten response stays untouched everywhere.
    for record_id, row in after.items():
        for column in ("workspace_id", "endpoint", "key", "payload_hash", "status"):
            assert row[column] == before[record_id][column], record_id
    # Foreign endpoints and non-completed or non-JSON records are never touched.
    for untouched in (
        "idem-survivor",
        "idem-other-endpoint",
        "idem-processing",
        "idem-invalid-json",
    ):
        assert after[untouched]["response_json"] == before[untouched]["response_json"]
    # The consolidated replay keeps its exact shape except for the run id.
    rewritten = after["idem-consolidated"]["response_json"]
    assert json.loads(rewritten) == {
        **json.loads(CONSOLIDATED_RUN_RESPONSE),
        "id": "legacy-completed",
    }
    assert list(json.loads(rewritten)) == list(json.loads(CONSOLIDATED_RUN_RESPONSE))
    assert rewritten != CONSOLIDATED_RUN_RESPONSE
    with postgres_engine.connect() as connection:
        # The replayed id really exists after the consolidation.
        assert (
            connection.scalar(
                text("SELECT count(*) FROM trend_runs WHERE id = :id"),
                {"id": json.loads(rewritten)["id"]},
            )
            == 1
        )
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    trend_divergences = [entry for entry in diffs if _diff_table(entry) == "trend_runs"]
    assert trend_divergences == [], f"021 no coincide con los modelos: {trend_divergences}"

    class NeverFetchSource:
        identifier = "legacy-rss"
        public_name = "Legacy RSS"
        source_type = "rss"
        supported_regions = ("HN",)
        supported_categories = ("gastronomy",)
        available = True
        calls = 0

        async def fetch(self, *, region: str, category: str | None):
            del region, category
            self.calls += 1
            raise AssertionError("El run legado debía reutilizarse.")

    async def collect_legacy() -> str:
        engine = create_async_engine(POSTGRES_URL)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = NeverFetchSource()
        try:
            async with factory() as db:
                run = await TrendService(
                    db,
                    (source,),
                    now=datetime(2026, 7, 30, 18, tzinfo=UTC),
                ).collect(region="HN", category="gastronomy")
                assert source.calls == 0
                return run.id
        finally:
            await engine.dispose()

    assert asyncio.run(collect_legacy()) == "legacy-completed"

    command.downgrade(_alembic_config(), "020")
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    """
                    SELECT count(*) FROM information_schema.columns
                    WHERE table_name = 'trend_runs' AND column_name = 'window_start'
                    """
                )
            )
            == 0
        )
    _upgrade("021")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "021"


def test_real_trend_budget_upgrade_downgrade_and_schema(postgres_engine) -> None:
    _upgrade("019")
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regclass('public.trend_provider_budgets')")) is None
        )
    _upgrade("020")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.trend_provider_budgets')"))
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    divergences = [entry for entry in diffs if _diff_table(entry) == "trend_provider_budgets"]
    assert divergences == [], f"020 no coincide con los modelos: {divergences}"
    command.downgrade(_alembic_config(), "019")
    _upgrade("020")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "020"


def test_phase1_templates_are_seeded_once_and_upgrade_is_repeatable(postgres_engine) -> None:
    _upgrade("head")
    before = _public_template_ids(postgres_engine)
    command.downgrade(_alembic_config(), "011")
    _upgrade("head")
    after = _public_template_ids(postgres_engine)
    assert before == after
    assert len(after) == len(EXPECTED_TEMPLATE_IDS)
    assert len(after) == len(set(after))


def test_upgrade_hides_unapproved_templates_without_breaking_historical_rows(
    postgres_engine,
) -> None:
    _upgrade("011")
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO templates "
                "(id, title, platforms, formats, category, objective, thumbnail_url, "
                "editable_slots, description) VALUES "
                "(:id, :title, :platforms, :formats, :category, :objective, :thumbnail_url, "
                ":editable_slots, :description)"
            ),
            {
                "id": "tpl_unapproved",
                "title": "Título personalizado",
                "platforms": "[]",
                "formats": "[]",
                "category": "custom",
                "objective": "custom",
                "thumbnail_url": "/custom.svg",
                "editable_slots": "[]",
                "description": "Contenido personalizado.",
            },
        )
    _upgrade("head")
    with postgres_engine.connect() as connection:
        ids = set(connection.scalars(text("SELECT id FROM templates")))
        columns = {
            row.column_name
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'templates'"
                )
            )
        }
    assert "tpl_unapproved" in ids
    assert set(_public_template_ids(postgres_engine)) == EXPECTED_TEMPLATE_IDS
    assert {"canva_url", "aspect_ratio", "is_public"} <= columns


def test_downgrade_restores_a_016_compatible_template_catalog(postgres_engine) -> None:
    _upgrade("head")
    command.downgrade(_alembic_config(), "011")
    assert EXPECTED_TEMPLATE_IDS.isdisjoint(set(_template_ids(postgres_engine)))


def test_upgrade_from_013_adds_pending_signup_schema(postgres_engine) -> None:
    _upgrade("013")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.pending_signups')")) is None
    _upgrade("head")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.pending_signups')"))
        assert connection.scalar(text("SELECT to_regclass('public.user_preferences')"))
        pending_columns = {
            row.column_name
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'pending_signups'"
                )
            )
        }
        columns = {
            row.column_name
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'businesses'"
                )
            )
        }
    assert {"website_url", "content_locale", "onboarding_completed_at"} <= columns
    # The deletion status token lives on account_purge_jobs, never here.
    assert {"completion_response_json"} <= pending_columns
    assert {"status_token_hash", "status_token_expires_at"} & pending_columns == set()


def test_upgrade_from_014_adds_google_oauth_schema(postgres_engine) -> None:
    _upgrade("014")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.oauth_accounts')")) is None
    _upgrade("head")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.oauth_accounts')"))
        assert connection.scalar(text("SELECT to_regclass('public.oauth_authorization_requests')"))
        constraints = {
            row.conname
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'pending_signups'::regclass"
                )
            )
        }
    assert "uq_pending_signup_oauth_identity" in constraints


def test_upgrade_from_015_adds_ai_usage_events(postgres_engine) -> None:
    _upgrade("015")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.ai_usage_events')")) is None
    _upgrade("head")
    with postgres_engine.connect() as connection:
        columns = {
            row.column_name: row.data_type
            for row in connection.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ai_usage_events'"
                )
            )
        }
        indexes = {
            row.indexname
            for row in connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'ai_usage_events'")
            )
        }
        foreign_keys = {
            row.conname
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'ai_usage_events'::regclass AND contype = 'f'"
                )
            )
        }
    assert columns["reported_cost"] == "numeric"
    assert {"workspace_id", "user_id", "created_at", "provider_request_id"} <= columns.keys()
    assert {
        "ix_ai_usage_events_workspace_id",
        "ix_ai_usage_events_user_id",
        "ix_ai_usage_events_created_at",
    } <= indexes
    assert len(foreign_keys) == 2
    command.downgrade(_alembic_config(), "015")
    _upgrade("head")


def test_upgrade_from_016_adds_instagram_flow_timing(postgres_engine) -> None:
    _upgrade("016")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.creation_flow_events')")) is None
    _upgrade("head")
    with postgres_engine.connect() as connection:
        columns = {
            row.column_name
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'creation_flow_events'"
                )
            )
        }
    assert {
        "flow_started_at",
        "first_generation_completed_at",
        "elapsed_seconds",
        "completion_status",
        "flow_key",
    } <= columns
    command.downgrade(_alembic_config(), "016")
    _upgrade("head")


def test_upgrade_from_017_adds_account_lifecycle_schema(postgres_engine) -> None:
    _upgrade("017")
    _upgrade("head")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.account_purge_jobs')"))
        assert connection.scalar(text("SELECT to_regclass('public.admin_audit_events')"))
        assert connection.scalar(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='deletion_requested_at'"
            )
        )

    # head -> 017 must leave no trace behind, so a redeploy can replay it.
    command.downgrade(_alembic_config(), "017")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.account_purge_jobs')")) is None
        assert connection.scalar(text("SELECT to_regclass('public.admin_audit_events')")) is None
        assert (
            connection.scalar(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='deletion_requested_at'"
                )
            )
            is None
        )

    _upgrade("head")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "026"
        assert connection.scalar(text("SELECT to_regclass('public.account_purge_jobs')"))


def test_account_purge_job_survives_the_rows_it_deletes(postgres_engine) -> None:
    """No cascade may take the job away before it reports its outcome."""

    _upgrade("head")
    with postgres_engine.connect() as connection:
        referenced = list(
            connection.scalars(
                text(
                    "SELECT confrelid::regclass::text FROM pg_constraint "
                    "WHERE contype = 'f' AND conrelid = 'account_purge_jobs'::regclass"
                )
            )
        )
    assert referenced == []


def _flatten_diffs(diffs: list) -> list[tuple]:
    flat: list[tuple] = []
    for entry in diffs:
        flat.extend(entry) if isinstance(entry, list) else flat.append(entry)
    return flat


def _diff_table(entry: tuple) -> str | None:
    kind = entry[0]
    if kind in {"add_table", "remove_table"}:
        return entry[1].name
    if kind in {"add_column", "remove_column"} or kind.startswith("modify_"):
        return entry[2]
    return getattr(getattr(entry[1], "table", None), "name", None)


def _diff_column(entry: tuple) -> str | None:
    kind = entry[0]
    if kind in {"add_column", "remove_column"}:
        return entry[3].name
    if kind.startswith("modify_"):
        return entry[3]
    return None


def test_account_lifecycle_schema_matches_the_sqlalchemy_models(postgres_engine) -> None:
    """The schema Alembic builds for WAVE-009 must equal the declared models.

    The comparison is scoped to what this wave owns: tables created before it
    carry drift that predates this work and is not corrected here.
    """

    _upgrade("head")
    owned_tables = {"account_purge_jobs", "admin_audit_events"}
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))

    divergences = [
        entry
        for entry in diffs
        if _diff_table(entry) in owned_tables
        or (_diff_table(entry) == "users" and _diff_column(entry) == "deletion_requested_at")
    ]
    assert divergences == [], f"019 no coincide con los modelos: {divergences}"


def test_image_generation_upgrade_from_021_downgrade_and_reupgrade(postgres_engine) -> None:
    """022 must be additive over 021 and fully reversible."""

    _upgrade("021")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_jobs')")) is None
        assert (
            connection.scalar(text("SELECT to_regclass('public.image_generation_budgets')")) is None
        )

    _upgrade("022")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "022"
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_jobs')"))
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_budgets')"))
        # The worker claims the oldest queued job; that predicate must be indexed.
        indexes = set(
            connection.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'image_generation_jobs'")
            )
        )
    assert "ix_image_generation_jobs_status_created" in indexes
    # A browser reload asks for the newest job of one project, never for a scan.
    assert "ix_image_generation_jobs_workspace_project" in indexes

    command.downgrade(_alembic_config(), "021")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_jobs')")) is None
        assert (
            connection.scalar(text("SELECT to_regclass('public.image_generation_budgets')")) is None
        )
        # 021 keeps everything it owned before the image wave existed.
        assert connection.scalar(text("SELECT to_regclass('public.trend_runs')"))

    _upgrade("022")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "022"
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_jobs')"))


def test_image_generation_schema_matches_the_sqlalchemy_models(postgres_engine) -> None:
    """What 022 builds must equal what the ORM declares for the tables it owns."""

    _upgrade("head")
    owned_tables = {"image_generation_jobs", "image_generation_budgets"}
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    divergences = [entry for entry in diffs if _diff_table(entry) in owned_tables]
    assert divergences == [], f"022 no coincide con los modelos: {divergences}"


def test_image_generation_constraints_are_enforced_by_postgres(postgres_engine) -> None:
    """The database refuses the shapes the service refuses, not only the service."""

    _upgrade("head")
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_img_mig', 'Migración imágenes')")
        )

    def _insert_job(ratio: str, status: str) -> None:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO image_generation_jobs "
                    "(id, workspace_id, status, aspect_ratio, prompt, provider, model) "
                    "VALUES (:id, 'ws_img_mig', :status, :ratio, 'prompt', 'demo', 'demo-image-v1')"
                ),
                {"id": f"job_{ratio}_{status}", "ratio": ratio, "status": status},
            )

    _insert_job("1:1", "queued")
    for ratio in ("3:2", "16:9"):
        with pytest.raises(Exception, match="ck_image_generation_job_ratio"):
            _insert_job(ratio, "queued")
    with pytest.raises(Exception, match="ck_image_generation_job_status"):
        _insert_job("4:5", "in_progress")

    def _insert_budget(suffix: str, budget: int, consumed: int) -> None:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO image_generation_budgets "
                    "(id, workspace_id, period_start, period_end, budget, consumed) "
                    "VALUES (:id, 'ws_img_mig', :start, :end, :budget, :consumed)"
                ),
                {
                    "id": f"bud_{suffix}",
                    "start": now,
                    "end": now,
                    "budget": budget,
                    "consumed": consumed,
                },
            )

    with pytest.raises(Exception, match="ck_image_generation_budget_consumed"):
        _insert_budget("over", 5, 6)
    with pytest.raises(Exception, match="ck_image_generation_budget_positive"):
        _insert_budget("zero", 0, 0)


def test_the_paid_boundary_survives_in_the_schema_itself(postgres_engine) -> None:
    """The columns that stop a second paid call are not optional bookkeeping.

    ``provider_started`` is the state that says "the money may already be gone".
    The database refuses to record it without the timestamp that proves when,
    and it never deletes a job just because the row it should refund or the
    project it belonged to disappeared -- an orphan reference is recoverable,
    a vanished job is not.
    """

    _upgrade("head")
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_img_edge', 'Frontera pagada')")
        )
        connection.execute(
            text(
                "INSERT INTO projects (id, workspace_id, business_id, name, platform, status) "
                "VALUES ('prj_img_edge', 'ws_img_edge', 'biz_img_edge', 'Post', "
                "'instagram', 'active')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO image_generation_budgets "
                "(id, workspace_id, period_start, period_end, budget, consumed) "
                "VALUES ('bud_img_edge', 'ws_img_edge', :start, :end, 10, 1)"
            ),
            {"start": now, "end": now},
        )

    def _insert_job(job_id: str, status: str, provider_started_at) -> None:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO image_generation_jobs "
                    "(id, workspace_id, project_id, budget_id, status, aspect_ratio, prompt, "
                    "provider, model, claim_token, provider_started_at) "
                    "VALUES (:id, 'ws_img_edge', 'prj_img_edge', 'bud_img_edge', :status, "
                    "'4:5', 'prompt', 'demo', 'demo-image-v1', 'tok', :started)"
                ),
                {"id": job_id, "status": status, "started": provider_started_at},
            )

    # Claiming the job is not crossing the boundary; only the call is.
    _insert_job("job_edge_running", "running", None)
    with pytest.raises(Exception, match="ck_image_generation_job_provider_started"):
        _insert_job("job_edge_blind", "provider_started", None)
    _insert_job("job_edge_started", "provider_started", now)
    # The ambiguous and cancelled outcomes are storable states, not strings the
    # service invents on its way past a stricter constraint.
    _insert_job("job_edge_cancelled", "cancelled", None)

    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM image_generation_budgets WHERE id = 'bud_img_edge'"))
        connection.execute(text("DELETE FROM projects WHERE id = 'prj_img_edge'"))

    with postgres_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, budget_id, project_id FROM image_generation_jobs "
                "WHERE workspace_id = 'ws_img_edge' ORDER BY id"
            )
        ).all()
    assert [row.id for row in rows] == [
        "job_edge_cancelled",
        "job_edge_running",
        "job_edge_started",
    ]
    assert all(row.budget_id is None and row.project_id is None for row in rows)

    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM workspaces WHERE id = 'ws_img_edge'"))


def test_deleting_a_workspace_takes_its_image_rows(postgres_engine) -> None:
    """Account cleanup must not leave orphan jobs or budgets behind."""

    _upgrade("head")
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_img_drop', 'Baja de cuenta')")
        )
        connection.execute(
            text(
                "INSERT INTO image_generation_jobs "
                "(id, workspace_id, status, aspect_ratio, prompt, provider, model) "
                "VALUES ('job_drop', 'ws_img_drop', 'queued', '1:1', 'p', 'demo', 'demo-image-v1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO image_generation_budgets "
                "(id, workspace_id, period_start, period_end, budget, consumed) "
                "VALUES ('bud_drop', 'ws_img_drop', :start, :end, 10, 1)"
            ),
            {"start": now, "end": now},
        )

    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM workspaces WHERE id = 'ws_img_drop'"))

    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM image_generation_jobs WHERE workspace_id='ws_img_drop'")
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM image_generation_budgets WHERE workspace_id='ws_img_drop'"
                )
            )
            == 0
        )


def test_social_connections_upgrade_from_022_downgrade_and_reupgrade(postgres_engine) -> None:
    """023 must be additive over 022 and fully reversible."""

    _upgrade("022")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.social_connections')")) is None

    _upgrade("023")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "023"
        assert connection.scalar(text("SELECT to_regclass('public.social_connections')"))
        indexes = set(
            connection.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'social_connections'")
            )
        )
    # The Settings screen lists one workspace's connections and nothing else.
    assert "ix_social_connections_workspace_id" in indexes
    assert "ix_social_connections_workspace_provider" in indexes
    assert "ix_social_connections_provider" in indexes
    assert "uq_social_connection_account" in indexes

    command.downgrade(_alembic_config(), "022")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.social_connections')")) is None
        # 022 keeps everything it owned before the social wave existed.
        assert connection.scalar(text("SELECT to_regclass('public.image_generation_jobs')"))

    _upgrade("023")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "023"
        assert connection.scalar(text("SELECT to_regclass('public.social_connections')"))


def test_social_connection_schema_matches_the_sqlalchemy_models(postgres_engine) -> None:
    """What 023 builds must equal what the ORM declares for the table it owns."""

    _upgrade("head")
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    divergences = [entry for entry in diffs if _diff_table(entry) == "social_connections"]
    assert divergences == [], f"023 no coincide con los modelos: {divergences}"


def test_social_connection_tokens_are_never_stored_as_readable_columns(postgres_engine) -> None:
    """The table has no column that could hold a credential in the clear.

    A column named for a code, a verifier, a state or a raw provider payload is a
    place someone will eventually write one. The absence is the control.
    """

    _upgrade("head")
    with postgres_engine.connect() as connection:
        columns = set(
            connection.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'social_connections'"
                )
            )
        )

    assert {"encrypted_access_token", "encrypted_refresh_token"} <= columns
    forbidden = {
        "access_token",
        "refresh_token",
        "authorization_code",
        "code_verifier",
        "pkce_verifier",
        "oauth_state",
        "state",
        "client_secret",
        "provider_response",
        "raw_response",
    }
    assert forbidden & columns == set(), f"Columnas prohibidas presentes: {forbidden & columns}"


def test_social_connection_constraints_are_enforced_by_postgres(postgres_engine) -> None:
    """The database refuses the shapes the service refuses, not only the service."""

    _upgrade("head")
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_soc_mig', 'Migración social')")
        )

    def _insert(
        row_id: str,
        *,
        workspace_id: str = "ws_soc_mig",
        provider: str = "demo",
        account_id: str = "acc_1",
        status: str = "connected",
        account_type: str = "business",
        access_token: str | None = "v1.nonce.cipher",
        refresh_token: str | None = None,
        disconnected_at=None,
    ) -> None:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO social_connections "
                    "(id, workspace_id, provider, provider_account_id, display_name, "
                    "account_type, status, encrypted_access_token, encrypted_refresh_token, "
                    "connected_at, disconnected_at) "
                    "VALUES (:id, :workspace_id, :provider, :account_id, 'Cuenta', "
                    ":account_type, :status, :access_token, :refresh_token, :now, :disconnected)"
                ),
                {
                    "id": row_id,
                    "workspace_id": workspace_id,
                    "provider": provider,
                    "account_id": account_id,
                    "account_type": account_type,
                    "status": status,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "now": now,
                    "disconnected": disconnected_at,
                },
            )

    _insert("soc_ok")

    with pytest.raises(Exception, match="ck_social_connection_status"):
        _insert("soc_bad_status", status="pending", account_id="acc_2")
    with pytest.raises(Exception, match="ck_social_connection_account_type"):
        _insert("soc_bad_type", account_type="influencer", account_id="acc_3")
    # "connected" is a claim that a usable credential exists. Without one it is a lie.
    with pytest.raises(Exception, match="ck_social_connection_connected_token"):
        _insert("soc_no_token", access_token=None, account_id="acc_4")
    # A disconnected row must not keep a credential, nor hide when it was cut.
    with pytest.raises(Exception, match="ck_social_connection_disconnected_tokens"):
        _insert(
            "soc_dirty_disconnect",
            status="disconnected",
            account_id="acc_5",
            disconnected_at=now,
        )
    with pytest.raises(Exception, match="ck_social_connection_disconnected_at"):
        _insert(
            "soc_undated_disconnect",
            status="disconnected",
            account_id="acc_6",
            access_token=None,
            refresh_token=None,
        )
    _insert(
        "soc_clean_disconnect",
        status="disconnected",
        account_id="acc_7",
        access_token=None,
        refresh_token=None,
        disconnected_at=now,
    )

    # One external account connects once per workspace and provider. Reconnecting
    # is an update of that row, never a second row racing the first.
    with pytest.raises(Exception, match="uq_social_connection_account"):
        _insert("soc_duplicate", account_id="acc_1")

    # The same external account may legitimately belong to two workspaces, and to
    # two providers, without either constraint standing in the way.
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_soc_other', 'Otro espacio')")
        )
    _insert("soc_other_workspace", workspace_id="ws_soc_other")
    _insert("soc_other_provider", provider="instagram")

    with postgres_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM workspaces WHERE id IN ('ws_soc_mig', 'ws_soc_other')")
        )


def test_deleting_a_workspace_takes_its_social_connections(postgres_engine) -> None:
    """A purge must not leave behind a token that still works."""

    _upgrade("head")
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_soc_drop', 'Baja de cuenta')")
        )
        connection.execute(
            text(
                "INSERT INTO social_connections "
                "(id, workspace_id, provider, provider_account_id, display_name, "
                "account_type, status, encrypted_access_token, connected_at) "
                "VALUES ('soc_drop', 'ws_soc_drop', 'demo', 'acc_drop', 'Cuenta', "
                "'business', 'connected', 'v1.nonce.cipher', :now)"
            ),
            {"now": now},
        )

    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM workspaces WHERE id = 'ws_soc_drop'"))

    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM social_connections WHERE workspace_id='ws_soc_drop'")
            )
            == 0
        )


def test_video_generation_schema_matches_the_sqlalchemy_models(postgres_engine) -> None:
    """024 must build the two video tables exactly as the ORM declares them."""

    _upgrade("head")
    owned_tables = {"video_generation_jobs", "video_generation_budgets"}
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))
    divergences = [entry for entry in diffs if _diff_table(entry) in owned_tables]
    assert divergences == [], f"024 no coincide con los modelos: {divergences}"


def test_video_generation_024_roundtrip_and_durable_constraints(postgres_engine) -> None:
    """The video migration must be reversible and preserve its hard boundaries."""

    _upgrade("023")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "023"
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_jobs')")) is None
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name='assets' AND column_name='duration_seconds'"
                )
            )
            == 0
        )

    _upgrade("024")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "024"
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_jobs')"))
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_budgets')"))
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE tablename='video_generation_jobs' "
                    "AND indexname IN ('ix_video_jobs_claim', 'ix_video_jobs_polling', "
                    "'ix_video_jobs_requested_by_user', 'ix_video_jobs_workspace_project')"
                )
            )
            == 4
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname='fk_video_jobs_source_asset_id'"
                )
            )
            == 0
        )

    command.downgrade(_alembic_config(), "023")
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "023"
        assert connection.scalar(text("SELECT to_regclass('public.video_generation_jobs')")) is None
        assert (
            connection.scalar(text("SELECT to_regclass('public.video_generation_budgets')")) is None
        )

    _upgrade("024")
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash) VALUES "
                "('usr_video_mig', 'video-mig@example.com', 'Video', 'hash')"
            )
        )
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES ('ws_video_mig', 'Video migration')")
        )
        connection.execute(
            text(
                "INSERT INTO video_generation_budgets "
                "(id, workspace_id, day, budget, consumed) "
                "VALUES ('budget_video_mig', 'ws_video_mig', '2026-08-02', 2, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO assets "
                "(id, workspace_id, original_name, storage_path, mime_type, file_size_bytes, asset_type) "
                "VALUES ('source_video_mig', 'ws_video_mig', 'source.png', 'source.png', "
                "'image/png', 4, 'image')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO video_generation_jobs "
                "(id, workspace_id, status, provider, prompt, storyboard_json, source_asset_id, "
                "aspect_ratio, duration_seconds, provider_job_id, budget_id, requested_by_user_id) "
                "VALUES ('job_video_mig', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
                "'source_video_mig', '9:16', 5, 'remote-video-mig', 'budget_video_mig', 'usr_video_mig')"
            )
        )

    # The source reference is intentionally logical: deleting the source does
    # not rewrite the approved job to NULL.
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM assets WHERE id='source_video_mig'"))
        assert (
            connection.scalar(
                text("SELECT source_asset_id FROM video_generation_jobs WHERE id='job_video_mig'")
            )
            == "source_video_mig"
        )
        connection.execute(text("DELETE FROM users WHERE id='usr_video_mig'"))
        assert (
            connection.scalar(
                text(
                    "SELECT requested_by_user_id FROM video_generation_jobs WHERE id='job_video_mig'"
                )
            )
            is None
        )

    invalid_statements = (
        (
            "uq_video_jobs_provider_job",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds, provider_job_id) VALUES "
            "('job_video_mig_dup', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'9:16', 5, 'remote-video-mig')",
        ),
        (
            "ck_video_jobs_status",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds) VALUES "
            "('job_video_mig_bad_status', 'ws_video_mig', 'not-a-status', 'demo', 'prompt', '{}', "
            "'9:16', 5)",
        ),
        (
            "ck_video_jobs_duration_seconds",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds) VALUES "
            "('job_video_mig_bad_duration', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'9:16', 0)",
        ),
        (
            "ck_video_jobs_aspect_ratio",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds) VALUES "
            "('job_video_mig_bad_ratio', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'16:9', 5)",
        ),
        (
            "ck_video_jobs_attempt_count",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds, attempt_count) VALUES "
            "('job_video_mig_bad_attempt', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'9:16', 5, -1)",
        ),
        (
            "ck_video_jobs_poll_count",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds, poll_count) VALUES "
            "('job_video_mig_bad_poll', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'9:16', 5, -1)",
        ),
        (
            "ck_video_jobs_download_attempt_count",
            "INSERT INTO video_generation_jobs "
            "(id, workspace_id, status, provider, prompt, storyboard_json, aspect_ratio, "
            "duration_seconds, download_attempt_count) VALUES "
            "('job_video_mig_bad_download', 'ws_video_mig', 'queued', 'demo', 'prompt', '{}', "
            "'9:16', 5, -1)",
        ),
        (
            "ck_video_budgets_consumed_lte_budget",
            "INSERT INTO video_generation_budgets "
            "(id, workspace_id, day, budget, consumed) VALUES "
            "('budget_video_mig_bad', 'ws_video_mig', '2026-08-03', 1, 2)",
        ),
    )
    for constraint_name, statement in invalid_statements:
        with postgres_engine.begin() as connection, pytest.raises(
            Exception, match=constraint_name
        ):
            connection.execute(text(statement))

    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM workspaces WHERE id='ws_video_mig'"))
        assert (
            connection.scalar(
                text("SELECT count(*) FROM video_generation_jobs WHERE id='job_video_mig'")
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM video_generation_budgets WHERE id='budget_video_mig'")
            )
            == 0
        )


def test_beta_readiness_schema_matches_the_declared_models(postgres_engine) -> None:
    """Wave 14 tables and the invite foreign key must not drift from ORM metadata."""

    _upgrade("head")
    owned_tables = {
        "beta_invites",
        "password_reset_tokens",
        "product_feedback",
        "abuse_reports",
        "usage_adjustments",
    }
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = _flatten_diffs(compare_metadata(context, Base.metadata))

    divergences = [
        entry
        for entry in diffs
        if _diff_table(entry) in owned_tables
        or (_diff_table(entry) == "pending_signups" and _diff_column(entry) == "beta_invite_id")
    ]
    assert divergences == [], f"025 no coincide con los modelos: {divergences}"
