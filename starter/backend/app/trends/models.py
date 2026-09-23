from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class TrendRun(Base):
    __tablename__ = "trend_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"), index=True)
    sources_attempted: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    sources_succeeded: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    sources_failed: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    public_error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','completed','partial','failed')",
            name="ck_trend_run_status",
        ),
        UniqueConstraint(
            "window_start",
            "region",
            "category",
            name="uq_trend_run_daily_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )


class TrendItem(Base):
    __tablename__ = "trend_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    group_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    observation_window: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    component_scores: Mapped[str] = mapped_column(Text, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrendEvidence(Base):
    __tablename__ = "trend_evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_window: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint(
            "source", "canonical_url", "region", "observation_window",
            name="uq_trend_evidence_source_url_window",
        ),
    )


class TrendItemEvidence(Base):
    """Idempotent link from a publishable item to a global observation."""

    __tablename__ = "trend_item_evidence"
    trend_item_id: Mapped[str] = mapped_column(
        ForeignKey("trend_items.id", ondelete="CASCADE"), primary_key=True
    )
    trend_evidence_id: Mapped[str] = mapped_column(
        ForeignKey("trend_evidence.id", ondelete="CASCADE"), primary_key=True
    )


class TrendRunEvidence(Base):
    """Minimal audit link: evidence is global, its observation is attributable to a run."""

    __tablename__ = "trend_run_evidence"
    trend_run_id: Mapped[str] = mapped_column(
        ForeignKey("trend_runs.id", ondelete="CASCADE"), primary_key=True
    )
    trend_evidence_id: Mapped[str] = mapped_column(
        ForeignKey("trend_evidence.id", ondelete="CASCADE"), primary_key=True
    )


class WorkspaceTrendRelevance(Base):
    __tablename__ = "workspace_trend_relevance"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trend_item_id: Mapped[str] = mapped_column(
        ForeignKey("trend_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_version: Mapped[str] = mapped_column(String(32), nullable=False)
    component_scores: Mapped[str] = mapped_column(Text, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "trend_item_id", name="uq_workspace_trend_relevance"),
    )


class TrendProviderBudget(Base):
    """Global, UTC-scoped reservation ledger for paid/limited source calls."""

    __tablename__ = "trend_provider_budgets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    budget: Mapped[int] = mapped_column(nullable=False)
    consumed: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        Index("ix_trend_provider_budgets_provider_operation", "provider", "operation"),
        UniqueConstraint(
            "provider", "operation", "period_start", name="uq_trend_provider_budget_period"
        ),
        CheckConstraint("budget > 0", name="ck_trend_provider_budget_positive"),
        CheckConstraint("consumed >= 0 AND consumed <= budget", name="ck_trend_provider_budget_consumed"),
    )
