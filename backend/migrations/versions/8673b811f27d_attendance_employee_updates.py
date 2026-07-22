"""attendance_employee_updates

Revision ID: 8673b811f27d
Revises: 20260704_0002
Create Date: 2026-07-05 07:32:40.617155
"""
from alembic import op
import sqlalchemy as sa



revision = '8673b811f27d'
down_revision = '20260704_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    attendance_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("attendances")
    }
    employee_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("employees")
    }
    if "overtime_status" not in attendance_columns:
        op.add_column(
            "attendances",
            sa.Column(
                "overtime_status",
                sa.String(length=32),
                server_default="none",
                nullable=False,
            ),
        )
    if "active" not in employee_columns:
        op.add_column(
            "employees",
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    employee_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("employees")
    }
    attendance_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("attendances")
    }
    if "active" in employee_columns:
        op.drop_column("employees", "active")
    if "overtime_status" in attendance_columns:
        op.drop_column("attendances", "overtime_status")
