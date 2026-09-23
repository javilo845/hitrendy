"""add artifact interaction events

Revision ID: 009
Revises: 008
"""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_artifact_events_artifact_id", "artifact_events", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_events_artifact_id", table_name="artifact_events")
    op.drop_table("artifact_events")
