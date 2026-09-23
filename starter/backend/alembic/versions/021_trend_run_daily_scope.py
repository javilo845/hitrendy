"""Add an explicit durable UTC-day identity to trend runs.

Consolidating historical runs into one row per ``window_start + region +
category`` deletes rows whose ``id`` other durable contracts already point at.
The migration therefore materialises an explicit ``removed_id -> survivor_id``
mapping *before* deleting anything and rewrites every real reference through
it:

* ``trend_run_evidence.trend_run_id`` (the only foreign key to ``trend_runs``)
  is re-linked to the survivor so no evidence row is orphaned or deleted.
* the merged run reports merged source traceability.
* stored idempotent ``POST:/trends/refresh`` responses keep replaying byte for
  byte, except for the consolidated run id they returned.

Revision ID: 021
Revises: 020
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSOLIDATION_TABLE = "trend_run_daily_scope_consolidation_021"

REFRESH_ENDPOINT = "POST:/trends/refresh"


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return value.replace(tzinfo=UTC).timestamp()


def _has_column(connection: sa.Connection, table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(connection).get_columns(table_name)
    )


def _source_set(value: object) -> set[str]:
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload if item is not None}


def _sqlite_upgrade(connection: sa.Connection) -> None:
    """Apply 021 without PostgreSQL-only JSON/window syntax.

    SQLite is the credential-free demo database. The PostgreSQL path below is
    intentionally kept unchanged for the larger, set-based migration, while
    this branch performs the same bounded consolidation in Python so a fresh
    demo install can still run every migration to head.
    """

    connection.execute(
        sa.text(
            """
            UPDATE trend_runs
            SET
                region = upper(trim(region)),
                category = nullif(lower(trim(category)), ''),
                window_start = datetime(started_at, 'start of day')
            """
        )
    )
    rows = [
        dict(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT id, region, category, status, sources_attempted,
                       sources_succeeded, sources_failed, started_at, finished_at,
                       window_start
                FROM trend_runs
                """
            )
        ).mappings()
    ]
    scopes: defaultdict[tuple[str, str, str | None], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        category = row["category"]
        scopes[(str(row["window_start"]), str(row["region"]), category if category is None else str(category))].append(row)

    status_rank = {"completed": 0, "partial": 1, "processing": 2, "pending": 3}
    mapping: dict[str, str] = {}
    duplicate_groups: list[tuple[dict[str, object], list[dict[str, object]]]] = []
    for members in scopes.values():
        if len(members) < 2:
            continue
        members.sort(
            key=lambda row: (
                status_rank.get(str(row["status"]), 4),
                0 if _parse_datetime(row["finished_at"]) is not None else 1,
                -_timestamp(_parse_datetime(row["finished_at"])),
                -_timestamp(_parse_datetime(row["started_at"])),
                str(row["id"]),
            )
        )
        survivor = members[0]
        removed = members[1:]
        duplicate_groups.append((survivor, members))
        for row in removed:
            mapping[str(row["id"])] = str(survivor["id"])

    evidence_by_run: defaultdict[str, set[str]] = defaultdict(set)
    evidence_sources_by_run: defaultdict[str, set[str]] = defaultdict(set)
    for link in connection.execute(
        sa.text(
            """
            SELECT links.trend_run_id, links.trend_evidence_id, evidence.source
            FROM trend_run_evidence AS links
            JOIN trend_evidence AS evidence
              ON evidence.id = links.trend_evidence_id
            """
        )
    ).mappings():
        run_id = str(link["trend_run_id"])
        evidence_by_run[run_id].add(str(link["trend_evidence_id"]))
        evidence_sources_by_run[run_id].add(str(link["source"]))

    for removed_id, survivor_id in mapping.items():
        for evidence_id in evidence_by_run[removed_id]:
            connection.execute(
                sa.text(
                    """
                    INSERT OR IGNORE INTO trend_run_evidence
                        (trend_run_id, trend_evidence_id)
                    VALUES (:survivor_id, :evidence_id)
                    """
                ),
                {"survivor_id": survivor_id, "evidence_id": evidence_id},
            )

    for survivor, members in duplicate_groups:
        attempted: set[str] = set()
        succeeded: set[str] = set()
        failed: set[str] = set()
        survivor_id = str(survivor["id"])
        for member in members:
            attempted.update(_source_set(member["sources_attempted"]))
            succeeded.update(_source_set(member["sources_succeeded"]))
            failed.update(_source_set(member["sources_failed"]))
            succeeded.update(evidence_sources_by_run[str(member["id"])])
        failed.difference_update(succeeded)
        attempted.update(succeeded)
        connection.execute(
            sa.text(
                """
                UPDATE trend_runs
                SET sources_attempted = :attempted,
                    sources_succeeded = :succeeded,
                    sources_failed = :failed
                WHERE id = :survivor_id
                """
            ),
            {
                "attempted": json.dumps(sorted(attempted)),
                "succeeded": json.dumps(sorted(succeeded)),
                "failed": json.dumps(sorted(failed)),
                "survivor_id": survivor_id,
            },
        )

    if mapping:
        for record in connection.execute(
            sa.text(
                """
                SELECT id, response_json
                FROM idempotency_records
                WHERE endpoint = :endpoint
                  AND status = 'completed'
                  AND response_json IS NOT NULL
                """
            ),
            {"endpoint": REFRESH_ENDPOINT},
        ).mappings():
            try:
                document = json.loads(record["response_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(document, dict):
                continue
            old_id = document.get("id")
            if old_id not in mapping:
                continue
            document["id"] = mapping[old_id]
            connection.execute(
                sa.text(
                    "UPDATE idempotency_records SET response_json = :response_json WHERE id = :id"
                ),
                {
                    "id": record["id"],
                    "response_json": json.dumps(document, ensure_ascii=False),
                },
            )

        for removed_id in mapping:
            connection.execute(
                sa.text("DELETE FROM trend_run_evidence WHERE trend_run_id = :run_id"),
                {"run_id": removed_id},
            )
            connection.execute(
                sa.text("DELETE FROM trend_runs WHERE id = :run_id"),
                {"run_id": removed_id},
            )

    # SQLite cannot express PostgreSQL's NULLS NOT DISTINCT unique constraint.
    # Coalescing category preserves the intended one-row-per-null-category
    # scope and keeps the application invariant enforceable after migration.
    with op.batch_alter_table("trend_runs", recreate="always") as batch:
        batch.alter_column("window_start", nullable=False)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_trend_run_daily_scope
        ON trend_runs(window_start, region, coalesce(category, ''))
        """
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _has_column(connection, "trend_runs", "window_start"):
        op.add_column(
            "trend_runs",
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        )
    if connection.dialect.name == "sqlite":
        _sqlite_upgrade(connection)
        return
    op.execute(
        """
        UPDATE trend_runs
        SET
            region = upper(btrim(region)),
            category = nullif(lower(btrim(category)), ''),
            window_start = (
                date_trunc('day', started_at AT TIME ZONE 'UTC')
                AT TIME ZONE 'UTC'
            )
        """
    )

    # Deterministic survivor per scope/day, computed once and stored so every
    # later statement (and the DELETE itself) uses exactly the same mapping.
    op.execute(f"DROP TABLE IF EXISTS {CONSOLIDATION_TABLE}")
    op.execute(
        f"""
        CREATE TEMPORARY TABLE {CONSOLIDATION_TABLE} AS
        WITH ranked AS (
            SELECT
                id,
                first_value(id) OVER scope AS survivor_id,
                row_number() OVER scope AS position
            FROM trend_runs
            WINDOW scope AS (
                PARTITION BY window_start, region, category
                ORDER BY
                    CASE status
                        WHEN 'completed' THEN 0
                        WHEN 'partial' THEN 1
                        WHEN 'processing' THEN 2
                        WHEN 'pending' THEN 3
                        ELSE 4
                    END,
                    finished_at DESC NULLS LAST,
                    started_at DESC,
                    id
            )
        )
        SELECT id AS removed_id, survivor_id
        FROM ranked
        WHERE position > 1
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX ON {CONSOLIDATION_TABLE} (removed_id)
        """
    )

    # 1. Evidence links from every redundant run move to the survivor.
    #    Evidence rows themselves are never touched, so TrendEvidence ids and
    #    their private payloads stay exactly as they were.
    op.execute(
        f"""
        INSERT INTO trend_run_evidence (trend_run_id, trend_evidence_id)
        SELECT mapping.survivor_id, links.trend_evidence_id
        FROM {CONSOLIDATION_TABLE} AS mapping
        JOIN trend_run_evidence AS links
          ON links.trend_run_id = mapping.removed_id
        ON CONFLICT DO NOTHING
        """
    )

    # 2. The survivor reports the merged traceability of the whole scope/day:
    #    attempted = union of everything attempted, succeeded = union of
    #    everything that succeeded (including whatever produced the evidence
    #    now linked to the survivor), failed = union of failures minus the
    #    sources that ultimately succeeded. Ordering is stable and duplicate
    #    free; malformed legacy values degrade to an empty array instead of
    #    aborting the migration.
    op.execute(
        f"""
        WITH members AS (
            SELECT survivor_id, survivor_id AS run_id FROM {CONSOLIDATION_TABLE}
            UNION
            SELECT survivor_id, removed_id FROM {CONSOLIDATION_TABLE}
        ),
        survivors AS (
            SELECT DISTINCT survivor_id FROM members
        ),
        run_sources AS (
            SELECT DISTINCT
                members.survivor_id,
                bucket.name AS bucket,
                element AS source
            FROM members
            JOIN trend_runs ON trend_runs.id = members.run_id
            CROSS JOIN LATERAL (
                VALUES
                    ('attempted', trend_runs.sources_attempted),
                    ('succeeded', trend_runs.sources_succeeded),
                    ('failed', trend_runs.sources_failed)
            ) AS bucket(name, payload)
            CROSS JOIN LATERAL json_array_elements_text(
                CASE
                    WHEN bucket.payload IS JSON ARRAY THEN bucket.payload::json
                    ELSE '[]'::json
                END
            ) AS element
        ),
        evidence_sources AS (
            SELECT DISTINCT members.survivor_id, trend_evidence.source
            FROM members
            JOIN trend_run_evidence AS links
              ON links.trend_run_id = members.run_id
            JOIN trend_evidence ON trend_evidence.id = links.trend_evidence_id
        ),
        succeeded AS (
            SELECT survivor_id, source FROM run_sources WHERE bucket = 'succeeded'
            UNION
            SELECT survivor_id, source FROM evidence_sources
        ),
        failed AS (
            SELECT survivor_id, source FROM run_sources WHERE bucket = 'failed'
            EXCEPT
            SELECT survivor_id, source FROM succeeded
        ),
        attempted AS (
            SELECT survivor_id, source FROM run_sources
            UNION
            SELECT survivor_id, source FROM succeeded
        ),
        merged AS (
            SELECT
                survivors.survivor_id,
                COALESCE(attempted_agg.sources, '[]') AS sources_attempted,
                COALESCE(succeeded_agg.sources, '[]') AS sources_succeeded,
                COALESCE(failed_agg.sources, '[]') AS sources_failed
            FROM survivors
            LEFT JOIN (
                SELECT
                    survivor_id,
                    json_agg(source ORDER BY source COLLATE "C")::text AS sources
                FROM attempted
                GROUP BY survivor_id
            ) AS attempted_agg USING (survivor_id)
            LEFT JOIN (
                SELECT
                    survivor_id,
                    json_agg(source ORDER BY source COLLATE "C")::text AS sources
                FROM succeeded
                GROUP BY survivor_id
            ) AS succeeded_agg USING (survivor_id)
            LEFT JOIN (
                SELECT
                    survivor_id,
                    json_agg(source ORDER BY source COLLATE "C")::text AS sources
                FROM failed
                GROUP BY survivor_id
            ) AS failed_agg USING (survivor_id)
        )
        UPDATE trend_runs
        SET
            sources_attempted = merged.sources_attempted,
            sources_succeeded = merged.sources_succeeded,
            sources_failed = merged.sources_failed
        FROM merged
        WHERE trend_runs.id = merged.survivor_id
        """
    )

    # 3. Stored idempotent refresh responses must keep replaying, so the run id
    #    they returned is repointed to the survivor. Only the "id" member of a
    #    valid JSON object belonging to a completed POST:/trends/refresh record
    #    is rewritten: key order, formatting and every other member (including
    #    the workspace, key, payload hash and status columns) are preserved.
    op.execute(
        f"""
        WITH parsed AS MATERIALIZED (
            SELECT
                records.id AS record_id,
                records.response_json::json AS document
            FROM idempotency_records AS records
            WHERE records.endpoint = '{REFRESH_ENDPOINT}'
              AND records.status = 'completed'
              AND records.response_json IS JSON OBJECT
        ),
        targeted AS (
            SELECT parsed.record_id, parsed.document, mapping.survivor_id
            FROM parsed
            JOIN {CONSOLIDATION_TABLE} AS mapping
              ON mapping.removed_id = parsed.document ->> 'id'
        ),
        rewritten AS (
            SELECT
                targeted.record_id,
                json_object_agg(
                    entry.key,
                    CASE
                        WHEN entry.key = 'id' THEN to_json(targeted.survivor_id)
                        ELSE entry.value
                    END
                    ORDER BY entry.ordinality
                )::text AS response_json
            FROM targeted
            CROSS JOIN LATERAL json_each(targeted.document)
                WITH ORDINALITY AS entry(key, value, ordinality)
            GROUP BY targeted.record_id
        )
        UPDATE idempotency_records AS records
        SET response_json = rewritten.response_json
        FROM rewritten
        WHERE records.id = rewritten.record_id
        """
    )

    # 4. Only now the redundant runs can go away.
    op.execute(
        f"""
        DELETE FROM trend_runs
        USING {CONSOLIDATION_TABLE} AS mapping
        WHERE trend_runs.id = mapping.removed_id
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {CONSOLIDATION_TABLE}")

    op.alter_column("trend_runs", "window_start", nullable=False)
    op.create_unique_constraint(
        "uq_trend_run_daily_scope",
        "trend_runs",
        ["window_start", "region", "category"],
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.drop_index("uq_trend_run_daily_scope", table_name="trend_runs")
        with op.batch_alter_table("trend_runs", recreate="always") as batch:
            batch.drop_column("window_start")
        return
    op.drop_constraint(
        "uq_trend_run_daily_scope",
        "trend_runs",
        type_="unique",
    )
    op.drop_column("trend_runs", "window_start")
