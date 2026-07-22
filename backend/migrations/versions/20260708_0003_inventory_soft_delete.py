"""inventory soft delete

Revision ID: 20260708_0003
Revises: 20260704_0002
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260708_0003"
down_revision = "20260704_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_column("active")
