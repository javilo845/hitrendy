from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import settings


def _alembic_config() -> Config:
    backend_dir = Path(__file__).parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def test_demo_sqlite_reaches_head_and_reapplies_wave14(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'hitrendy.db'}"
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = settings.database_url
    settings.database_url = database_url
    try:
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "026"
            assert connection.scalar(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'index' AND name = 'uq_trend_run_daily_scope'"
                )
            ) == "uq_trend_run_daily_scope"

        command.downgrade(config, "024")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "026"
        engine.dispose()
    finally:
        settings.database_url = previous_url


def test_sqlite_trend_scope_migration_consolidates_legacy_rows(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'hitrendy.db'}"
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = settings.database_url
    settings.database_url = database_url
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "020")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO trend_runs (
                        id, fingerprint, region, category, status,
                        sources_attempted, sources_succeeded, sources_failed,
                        started_at, finished_at
                    ) VALUES
                        (
                            'run-complete', 'fingerprint-complete', ' hn ', ' Gastronomy ',
                            'completed', '["rss"]', '["rss"]', '[]',
                            '2026-07-30T08:00:00+00:00', '2026-07-30T09:00:00+00:00'
                        ),
                        (
                            'run-failed', 'fingerprint-failed', 'HN', 'gastronomy',
                            'failed', '["api"]', '[]', '["api"]',
                            '2026-07-30T10:00:00+00:00', '2026-07-30T10:00:00+00:00'
                        )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO trend_evidence (
                        id, source, source_url, canonical_url, observed_at,
                        region, observation_window, evidence_fingerprint
                    ) VALUES (
                        'evidence-api', 'api', 'https://example.test/api',
                        'https://example.test/api', '2026-07-30T10:00:00+00:00',
                        'HN', 'daily', 'evidence-fingerprint'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO trend_run_evidence (trend_run_id, trend_evidence_id)
                    VALUES ('run-failed', 'evidence-api')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO idempotency_records (
                        id, workspace_id, endpoint, key, response_json,
                        payload_hash, status
                    ) VALUES (
                        'refresh-record', 'workspace', 'POST:/trends/refresh',
                        'refresh-key', '{"id":"run-failed"}', 'legacy', 'completed'
                    )
                    """
                )
            )

        command.upgrade(config, "021")
        with engine.connect() as connection:
            survivor = connection.execute(
                text(
                    """
                    SELECT id, region, category, sources_attempted,
                           sources_succeeded, sources_failed
                    FROM trend_runs
                    """
                )
            ).mappings().one()
            assert survivor["id"] == "run-complete"
            assert survivor["region"] == "HN"
            assert survivor["category"] == "gastronomy"
            assert survivor["sources_attempted"] == '["api", "rss"]'
            assert survivor["sources_succeeded"] == '["api", "rss"]'
            assert survivor["sources_failed"] == "[]"
            assert connection.scalar(
                text("SELECT trend_run_id FROM trend_run_evidence")
            ) == "run-complete"
            assert connection.scalar(
                text("SELECT response_json FROM idempotency_records WHERE id = 'refresh-record'")
            ) == '{"id": "run-complete"}'
    finally:
        engine.dispose()
        settings.database_url = previous_url


def test_sqlite_trend_scope_migration_reuses_an_existing_window_column(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'hitrendy.db'}"
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = settings.database_url
    settings.database_url = database_url
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "020")
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE trend_runs ADD COLUMN window_start DATETIME")
            )

        command.upgrade(config, "021")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "021"
            assert connection.scalar(
                text(
                    "SELECT COUNT(*) FROM pragma_table_info('trend_runs') "
                    "WHERE name = 'window_start'"
                )
            ) == 1
    finally:
        engine.dispose()
        settings.database_url = previous_url


def test_sqlite_repairs_missing_template_public_flag(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'hitrendy.db'}"
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = settings.database_url
    settings.database_url = database_url
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "025")
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE templates DROP COLUMN is_public"))

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "026"
            assert connection.scalar(
                text(
                    "SELECT COUNT(*) FROM pragma_table_info('templates') "
                    "WHERE name = 'is_public'"
                )
            ) == 1
            assert connection.scalar(
                text("SELECT is_public FROM templates WHERE id = 'tpl_instagram_01'")
            ) == 1
    finally:
        engine.dispose()
        settings.database_url = previous_url
