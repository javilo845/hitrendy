"""store idempotency payload fingerprints and processing state

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column("payload_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "idempotency_records",
        sa.Column("status", sa.String(16), nullable=True),
    )
    op.execute(
        "UPDATE idempotency_records SET payload_hash = 'legacy', status = 'completed' "
        "WHERE payload_hash IS NULL OR status IS NULL"
    )
    with op.batch_alter_table("idempotency_records") as batch_op:
        batch_op.alter_column("payload_hash", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("status", existing_type=sa.String(16), nullable=False)
        batch_op.alter_column(
            "response_json",
            existing_type=sa.Text(),
            existing_nullable=False,
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("idempotency_records") as batch_op:
        batch_op.alter_column(
            "response_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.drop_column("status")
        batch_op.drop_column("payload_hash")
