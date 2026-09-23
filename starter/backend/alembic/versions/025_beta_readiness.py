"""Add closed-beta operations: recovery, invites, feedback and abuse reports.

Revision ID: 025
Revises: 024
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("email_normalized", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("note", sa.String(240), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active','redeemed','revoked')", name="ck_beta_invite_status"
        ),
    )
    op.create_index("ix_beta_invites_code_hash", "beta_invites", ["code_hash"], unique=True)
    op.create_index("ix_beta_invites_email_normalized", "beta_invites", ["email_normalized"])
    op.create_index("ix_beta_invites_status", "beta_invites", ["status"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])

    op.create_table(
        "product_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_product_feedback_workspace_key"
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_feedback_rating"
        ),
    )
    op.create_index("ix_product_feedback_workspace_id", "product_feedback", ["workspace_id"])
    op.create_index("ix_product_feedback_user_id", "product_feedback", ["user_id"])
    op.create_index("ix_product_feedback_status", "product_feedback", ["status"])

    op.create_table(
        "abuse_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reporter_user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_abuse_reports_workspace_id", "abuse_reports", ["workspace_id"])
    op.create_index("ix_abuse_reports_reporter_user_id", "abuse_reports", ["reporter_user_id"])
    op.create_index("ix_abuse_reports_status", "abuse_reports", ["status"])

    op.create_table(
        "usage_adjustments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("capability", sa.String(32), nullable=True),
        sa.Column("delta_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_usage_adjustments_workspace_id", "usage_adjustments", ["workspace_id"])
    op.create_index("ix_usage_adjustments_created_at", "usage_adjustments", ["created_at"])

    invite_column = sa.Column(
        "beta_invite_id",
        sa.String(64),
        sa.ForeignKey(
            "beta_invites.id",
            name="fk_pending_signups_beta_invite_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("pending_signups", recreate="always") as batch:
            batch.add_column(invite_column)
    else:
        op.add_column("pending_signups", invite_column)
    op.create_index("ix_pending_signups_beta_invite_id", "pending_signups", ["beta_invite_id"])


def downgrade() -> None:
    op.drop_index("ix_pending_signups_beta_invite_id", table_name="pending_signups")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("pending_signups", recreate="always") as batch:
            batch.drop_column("beta_invite_id")
    else:
        op.drop_column("pending_signups", "beta_invite_id")

    op.drop_index("ix_abuse_reports_status", table_name="abuse_reports")
    op.drop_index("ix_abuse_reports_reporter_user_id", table_name="abuse_reports")
    op.drop_index("ix_abuse_reports_workspace_id", table_name="abuse_reports")
    op.drop_table("abuse_reports")

    op.drop_index("ix_usage_adjustments_created_at", table_name="usage_adjustments")
    op.drop_index("ix_usage_adjustments_workspace_id", table_name="usage_adjustments")
    op.drop_table("usage_adjustments")

    op.drop_index("ix_product_feedback_status", table_name="product_feedback")
    op.drop_index("ix_product_feedback_user_id", table_name="product_feedback")
    op.drop_index("ix_product_feedback_workspace_id", table_name="product_feedback")
    op.drop_table("product_feedback")

    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_beta_invites_status", table_name="beta_invites")
    op.drop_index("ix_beta_invites_email_normalized", table_name="beta_invites")
    op.drop_index("ix_beta_invites_code_hash", table_name="beta_invites")
    op.drop_table("beta_invites")
