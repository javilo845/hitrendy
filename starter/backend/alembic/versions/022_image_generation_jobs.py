"""Durable image generation jobs and per-workspace daily budget."""

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The budget ledger is created first: a job carries the id of the exact
    # reservation it consumed, so a refund can never land on another period.
    op.create_table(
        "image_generation_budgets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id", "period_start", name="uq_image_generation_budget_period"
        ),
        sa.CheckConstraint("budget > 0", name="ck_image_generation_budget_positive"),
        sa.CheckConstraint(
            "consumed >= 0 AND consumed <= budget",
            name="ck_image_generation_budget_consumed",
        ),
    )
    op.create_index(
        "ix_image_generation_budgets_workspace_id",
        "image_generation_budgets",
        ["workspace_id"],
    )

    op.create_table(
        "image_generation_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("aspect_ratio", sa.String(8), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.String(600), nullable=True),
        sa.Column("reference_asset_id", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("asset_id", sa.String(64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        # The reservation this job consumed. Bound to the period that paid, so a
        # failure noticed after UTC midnight still refunds the previous day.
        sa.Column(
            "budget_id",
            sa.String(64),
            sa.ForeignKey("image_generation_budgets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The fencing token of the worker that owns the job right now.
        sa.Column("claim_token", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        # Non-null means the request left for the provider and may have been
        # billed. No worker re-issues such a job.
        sa.Column("provider_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "aspect_ratio IN ('1:1', '4:5', '9:16')",
            name="ck_image_generation_job_ratio",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'provider_started', "
            "'succeeded', 'failed', 'cancelled')",
            name="ck_image_generation_job_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_image_generation_job_attempts"),
        sa.CheckConstraint(
            "status <> 'provider_started' OR provider_started_at IS NOT NULL",
            name="ck_image_generation_job_provider_started",
        ),
    )
    op.create_index(
        "ix_image_generation_jobs_workspace_id", "image_generation_jobs", ["workspace_id"]
    )
    op.create_index("ix_image_generation_jobs_status", "image_generation_jobs", ["status"])
    # The worker claims the oldest queued job, so the claim predicate is indexed.
    op.create_index(
        "ix_image_generation_jobs_status_created",
        "image_generation_jobs",
        ["status", "created_at"],
    )
    # A browser reload asks for the newest job of one project, scoped to its own
    # workspace.
    op.create_index(
        "ix_image_generation_jobs_workspace_project",
        "image_generation_jobs",
        ["workspace_id", "project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_generation_jobs_workspace_project", "image_generation_jobs")
    op.drop_index("ix_image_generation_jobs_status_created", "image_generation_jobs")
    op.drop_index("ix_image_generation_jobs_status", "image_generation_jobs")
    op.drop_index("ix_image_generation_jobs_workspace_id", "image_generation_jobs")
    op.drop_table("image_generation_jobs")
    op.drop_index("ix_image_generation_budgets_workspace_id", "image_generation_budgets")
    op.drop_table("image_generation_budgets")
