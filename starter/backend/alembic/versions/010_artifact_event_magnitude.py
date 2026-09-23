"""add artifact event edit magnitude

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("artifact_events") as batch_op:
        batch_op.add_column(sa.Column("magnitude_percent", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("artifact_events") as batch_op:
        batch_op.drop_column("magnitude_percent")
