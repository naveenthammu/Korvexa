"""add product active flag

Revision ID: 20260708_0004
Revises: 20260708_0003, 20260708_0003_permissions
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20260708_0004"
down_revision = ("20260708_0003", "20260708_0003_permissions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("products")}
    if "active" not in columns:
        op.add_column(
            "products",
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("products")}
    if "active" in columns:
        op.drop_column("products", "active")
