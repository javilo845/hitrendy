"""Verified trend evidence framework.

Revision ID: 019
Revises: 018
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trend_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("category", sa.String(40)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("sources_attempted", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sources_succeeded", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sources_failed", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("public_error", sa.String(240)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','partial','failed')",
            name="ck_trend_run_status",
        ),
    )
    op.create_index("ix_trend_runs_region", "trend_runs", ["region"])
    op.create_index("ix_trend_runs_category", "trend_runs", ["category"])
    op.create_index("ix_trend_runs_status", "trend_runs", ["status"])
    op.create_table(
        "trend_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("group_key", sa.String(64), nullable=False, unique=True),
        sa.Column("observation_window", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("category", sa.String(40)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_score", sa.Float(), nullable=False),
        sa.Column("scoring_version", sa.String(32), nullable=False),
        sa.Column("component_scores", sa.Text(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for name, cols in (
        ("ix_trend_items_region", ["region"]),
        ("ix_trend_items_category", ["category"]),
        ("ix_trend_items_observation_window", ["observation_window"]),
        ("ix_trend_items_observed_at", ["observed_at"]),
        ("ix_trend_items_total_score", ["total_score"]),
    ):
        op.create_index(name, "trend_items", cols)
    op.create_table(
        "trend_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("canonical_url", sa.String(1000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("observation_window", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source", "canonical_url", "region", "observation_window",
            name="uq_trend_evidence_source_url_window",
        ),
    )
    op.create_index("ix_trend_evidence_observation_window", "trend_evidence", ["observation_window"])
    op.create_table(
        "trend_item_evidence",
        sa.Column(
            "trend_item_id",
            sa.String(64),
            sa.ForeignKey("trend_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "trend_evidence_id",
            sa.String(64),
            sa.ForeignKey("trend_evidence.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "trend_run_evidence",
        sa.Column(
            "trend_run_id",
            sa.String(64),
            sa.ForeignKey("trend_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "trend_evidence_id",
            sa.String(64),
            sa.ForeignKey("trend_evidence.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "workspace_trend_relevance",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trend_item_id",
            sa.String(64),
            sa.ForeignKey("trend_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("relevance_version", sa.String(32), nullable=False),
        sa.Column("component_scores", sa.Text(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "trend_item_id", name="uq_workspace_trend_relevance"),
    )
    op.create_index(
        "ix_workspace_trend_relevance_workspace_id", "workspace_trend_relevance", ["workspace_id"]
    )
    op.create_index(
        "ix_workspace_trend_relevance_trend_item_id", "workspace_trend_relevance", ["trend_item_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_trend_relevance_trend_item_id", table_name="workspace_trend_relevance"
    )
    op.drop_index(
        "ix_workspace_trend_relevance_workspace_id", table_name="workspace_trend_relevance"
    )
    op.drop_table("workspace_trend_relevance")
    op.drop_table("trend_run_evidence")
    op.drop_table("trend_item_evidence")
    op.drop_index("ix_trend_evidence_observation_window", table_name="trend_evidence")
    op.drop_table("trend_evidence")
    for name in (
        "ix_trend_items_total_score",
        "ix_trend_items_observed_at",
        "ix_trend_items_category",
        "ix_trend_items_observation_window",
        "ix_trend_items_region",
    ):
        op.drop_index(name, table_name="trend_items")
    op.drop_table("trend_items")
    for name in ("ix_trend_runs_status", "ix_trend_runs_category", "ix_trend_runs_region"):
        op.drop_index(name, table_name="trend_runs")
    op.drop_table("trend_runs")
