"""add user custom permissions

Revision ID: 20260708_0003_permissions
Revises: 8673b811f27d
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20260708_0003_permissions"
down_revision = "8673b811f27d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "custom_permissions" not in columns:
        op.add_column(
            "users",
            sa.Column("custom_permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "custom_permissions" in columns:
        op.drop_column("users", "custom_permissions")
