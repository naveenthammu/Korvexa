"""Add leave requests for day-salary payroll."""

from alembic import op
import sqlalchemy as sa


revision = "20260708_0005"
down_revision = "20260708_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "leave_requests" not in inspector.get_table_names():
        op.create_table(
            "leave_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("employee_id", sa.String(length=36), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("leave_type", sa.String(length=32), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("leave_requests")}
    for name, columns in (
        ("ix_leave_requests_tenant_id", ["tenant_id"]),
        ("ix_leave_requests_branch_id", ["branch_id"]),
        ("ix_leave_requests_employee_id", ["employee_id"]),
        ("ix_leave_requests_tenant_branch_status", ["tenant_id", "branch_id", "status"]),
    ):
        if name not in indexes:
            op.create_index(name, "leave_requests", columns)


def downgrade() -> None:
    bind = op.get_bind()
    if "leave_requests" in sa.inspect(bind).get_table_names():
        op.drop_table("leave_requests")
