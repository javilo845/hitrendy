"""Connected social accounts, with tokens stored only as encrypted envelopes."""

import sqlalchemy as sa

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_connections",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        # The id the provider issued, read back with the freshly exchanged token.
        # Never a value the browser supplied.
        sa.Column("provider_account_id", sa.String(191), nullable=False),
        # The public handle only, so two accounts can be told apart in Settings.
        sa.Column("display_name", sa.String(191), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(32), nullable=False, server_default="connected"),
        # AES-256-GCM envelopes. ``Text`` because truncating one would destroy the
        # credential, and there is no useful maximum to guess at.
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_scopes", sa.String(500), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        # A normalised code, never a provider error body.
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
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
        # One row per external account per provider per workspace: a repeated
        # handshake updates, it does not duplicate. Scoped to the workspace, so
        # two workspaces may connect the same account without learning about
        # each other.
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "provider_account_id",
            name="uq_social_connection_account",
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'expired', 'revoked', "
            "'degraded', 'error', 'disconnected')",
            name="ck_social_connection_status",
        ),
        sa.CheckConstraint(
            "account_type IN ('business', 'creator', 'personal', 'unknown')",
            name="ck_social_connection_account_type",
        ),
        # A connection presented as working must hold a token.
        sa.CheckConstraint(
            "status <> 'connected' OR encrypted_access_token IS NOT NULL",
            name="ck_social_connection_connected_token",
        ),
        # Disconnection is not a label: the credential is gone, or the row is not
        # disconnected.
        sa.CheckConstraint(
            "status <> 'disconnected' OR ("
            "encrypted_access_token IS NULL AND encrypted_refresh_token IS NULL"
            ")",
            name="ck_social_connection_disconnected_tokens",
        ),
        sa.CheckConstraint(
            "status <> 'disconnected' OR disconnected_at IS NOT NULL",
            name="ck_social_connection_disconnected_at",
        ),
    )
    op.create_index("ix_social_connections_workspace_id", "social_connections", ["workspace_id"])
    op.create_index("ix_social_connections_provider", "social_connections", ["provider"])
    # The listing reads one workspace, usually narrowed to one provider.
    op.create_index(
        "ix_social_connections_workspace_provider",
        "social_connections",
        ["workspace_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_social_connections_workspace_provider", "social_connections")
    op.drop_index("ix_social_connections_provider", "social_connections")
    op.drop_index("ix_social_connections_workspace_id", "social_connections")
    op.drop_table("social_connections")
