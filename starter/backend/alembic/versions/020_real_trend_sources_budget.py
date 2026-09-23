"""Persist global quota reservations for real trend sources."""

import sqlalchemy as sa

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_provider_budgets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("budget > 0", name="ck_trend_provider_budget_positive"),
        sa.CheckConstraint(
            "consumed >= 0 AND consumed <= budget", name="ck_trend_provider_budget_consumed"
        ),
        sa.UniqueConstraint(
            "provider", "operation", "period_start", name="uq_trend_provider_budget_period"
        ),
    )
    op.create_index(
        "ix_trend_provider_budgets_provider_operation",
        "trend_provider_budgets",
        ["provider", "operation"],
    )


def downgrade() -> None:
    op.drop_index("ix_trend_provider_budgets_provider_operation", table_name="trend_provider_budgets")
    op.drop_table("trend_provider_budgets")
