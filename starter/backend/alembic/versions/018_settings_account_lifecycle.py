"""Durable account deletion jobs and administrative audit trail.

Revision ID: 018
Revises: 017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True))
    # No foreign key to users/workspaces on purpose: the job must survive the
    # rows it deletes so the public status endpoint can still answer.
    op.create_table(
        "account_purge_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_token_hash", sa.String(length=64), nullable=True),
        sa.Column("status_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_account_purge_job_user"),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed')", name="ck_purge_status"
        ),
    )
    op.create_index(
        "ix_account_purge_jobs_status_token_hash",
        "account_purge_jobs",
        ["status_token_hash"],
        unique=True,
    )
    op.create_index("ix_account_purge_jobs_workspace_id", "account_purge_jobs", ["workspace_id"])
    op.create_index("ix_account_purge_jobs_status", "account_purge_jobs", ["status"])
    op.create_index("ix_account_purge_jobs_next_attempt_at", "account_purge_jobs", ["next_attempt_at"])
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.String(length=64), nullable=True),
        sa.Column("target_workspace_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_audit_events_actor", "admin_audit_events", ["actor"])
    op.create_index("ix_admin_audit_events_target_user_id", "admin_audit_events", ["target_user_id"])
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_target_user_id", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_actor", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_index("ix_account_purge_jobs_next_attempt_at", table_name="account_purge_jobs")
    op.drop_index("ix_account_purge_jobs_status", table_name="account_purge_jobs")
    op.drop_index("ix_account_purge_jobs_workspace_id", table_name="account_purge_jobs")
    op.drop_index("ix_account_purge_jobs_status_token_hash", table_name="account_purge_jobs")
    op.drop_table("account_purge_jobs")
    op.drop_column("users", "deletion_requested_at")
