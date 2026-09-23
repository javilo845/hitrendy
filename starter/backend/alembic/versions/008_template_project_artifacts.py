"""make template projects editable artifacts

Revision ID: 008
Revises: 007
"""

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generated_artifacts") as batch_op:
        batch_op.alter_column("conversation_id", existing_type=sa.String(64), nullable=True)
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("source_template_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("source_template_id")
    with op.batch_alter_table("generated_artifacts") as batch_op:
        batch_op.alter_column("conversation_id", existing_type=sa.String(64), nullable=False)
