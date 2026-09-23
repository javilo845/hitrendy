"""Add bounded asynchronous video jobs, budget ledger and asset duration."""

import sqlalchemy as sa

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("duration_seconds", sa.Integer(), nullable=True))

    op.create_table(
        "video_generation_budgets",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_video_budgets_workspace_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.PrimaryKeyConstraint("id", name="pk_video_generation_budgets"),
        sa.UniqueConstraint(
            "workspace_id",
            "day",
            name="uq_video_budgets_workspace_day",
        ),
        sa.CheckConstraint(
            "consumed >= 0",
            name="ck_video_budgets_consumed_nonnegative",
        ),
        sa.CheckConstraint(
            "budget >= 0",
            name="ck_video_budgets_budget_nonnegative",
        ),
        sa.CheckConstraint(
            "consumed <= budget",
            name="ck_video_budgets_consumed_lte_budget",
        ),
    )
    op.create_index(
        "ix_video_generation_budgets_workspace_id",
        "video_generation_budgets",
        ["workspace_id"],
    )

    op.create_table(
        "video_generation_jobs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_video_jobs_workspace_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey(
                "projects.id",
                name="fk_video_jobs_project_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("storyboard_json", sa.Text(), nullable=False),
        sa.Column(
            "source_asset_id",
            sa.String(64),
            nullable=True,
        ),
        sa.Column("aspect_ratio", sa.String(16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("provider_job_id", sa.String(191), nullable=True),
        sa.Column("provider_status", sa.String(48), nullable=True),
        sa.Column("asset_id", sa.String(64), nullable=True),
        sa.Column(
            "budget_id",
            sa.String(64),
            sa.ForeignKey(
                "video_generation_budgets.id",
                name="fk_video_jobs_budget_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.String(64),
            sa.ForeignKey(
                "users.id",
                name="fk_video_jobs_requested_by_user_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("claim_token", sa.String(64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "download_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_video_generation_jobs"),
        sa.UniqueConstraint(
            "provider",
            "provider_job_id",
            name="uq_video_jobs_provider_job",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'preparing', 'submitting', 'provider_pending', "
            "'downloading', 'succeeded', 'failed', 'cancelled', 'execution_unknown')",
            name="ck_video_jobs_status",
        ),
        sa.CheckConstraint(
            "aspect_ratio IN ('9:16')",
            name="ck_video_jobs_aspect_ratio",
        ),
        sa.CheckConstraint(
            "duration_seconds > 0 AND duration_seconds <= 60",
            name="ck_video_jobs_duration_seconds",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_video_jobs_attempt_count",
        ),
        sa.CheckConstraint(
            "poll_count >= 0",
            name="ck_video_jobs_poll_count",
        ),
        sa.CheckConstraint(
            "download_attempt_count >= 0",
            name="ck_video_jobs_download_attempt_count",
        ),
        sa.CheckConstraint(
            "asset_id IS NULL OR status = 'succeeded'",
            name="ck_video_jobs_asset_requires_succeeded",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR asset_id IS NOT NULL",
            name="ck_video_jobs_succeeded_requires_asset",
        ),
    )
    op.create_index(
        "ix_video_generation_jobs_workspace_id",
        "video_generation_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_video_generation_jobs_project_id",
        "video_generation_jobs",
        ["project_id"],
    )
    op.create_index("ix_video_generation_jobs_status", "video_generation_jobs", ["status"])
    op.create_index(
        "ix_video_jobs_claim",
        "video_generation_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_video_jobs_polling",
        "video_generation_jobs",
        ["status", "last_polled_at"],
    )
    op.create_index(
        "ix_video_jobs_requested_by_user",
        "video_generation_jobs",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_video_jobs_workspace_project",
        "video_generation_jobs",
        ["workspace_id", "project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_jobs_workspace_project", table_name="video_generation_jobs")
    op.drop_index("ix_video_jobs_polling", table_name="video_generation_jobs")
    op.drop_index("ix_video_jobs_requested_by_user", table_name="video_generation_jobs")
    op.drop_index("ix_video_jobs_claim", table_name="video_generation_jobs")
    op.drop_index("ix_video_generation_jobs_status", table_name="video_generation_jobs")
    op.drop_index("ix_video_generation_jobs_project_id", table_name="video_generation_jobs")
    op.drop_index("ix_video_generation_jobs_workspace_id", table_name="video_generation_jobs")
    op.drop_table("video_generation_jobs")
    op.drop_index(
        "ix_video_generation_budgets_workspace_id",
        table_name="video_generation_budgets",
    )
    op.drop_table("video_generation_budgets")
    op.drop_column("assets", "duration_seconds")
