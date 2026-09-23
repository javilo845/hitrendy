"""add artifact feedback

Revision ID: 007
Revises: 006
"""

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_artifact_feedback_artifact_id", "artifact_feedback", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_feedback_artifact_id", table_name="artifact_feedback")
    op.drop_table("artifact_feedback")
