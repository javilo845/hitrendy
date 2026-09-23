"""add Google OAuth identities and authorization state

Revision ID: 015
Revises: 014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("email_at_link_time", sa.String(255), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_oauth_account_provider_subject"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_table(
        "oauth_authorization_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("nonce", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_oauth_authorization_requests_state_hash",
        "oauth_authorization_requests",
        ["state_hash"],
    )
    op.create_index(
        "ix_oauth_authorization_requests_expires_at",
        "oauth_authorization_requests",
        ["expires_at"],
    )
    with op.batch_alter_table("pending_signups") as batch_op:
        batch_op.create_unique_constraint(
            "uq_pending_signup_oauth_identity", ["oauth_provider", "oauth_subject"]
        )


def downgrade() -> None:
    with op.batch_alter_table("pending_signups") as batch_op:
        batch_op.drop_constraint("uq_pending_signup_oauth_identity", type_="unique")
    op.drop_index("ix_oauth_authorization_requests_expires_at", table_name="oauth_authorization_requests")
    op.drop_index("ix_oauth_authorization_requests_state_hash", table_name="oauth_authorization_requests")
    op.drop_table("oauth_authorization_requests")
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
