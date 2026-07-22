"""add refunds

Revision ID: 20260718_0006
Revises: 20260708_0005
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260718_0006"
down_revision = "20260708_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refunds" not in inspector.get_table_names():
        op.create_table(
            "refunds",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_id", sa.String(length=36), sa.ForeignKey("payments.id"), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("gateway_refund_id", sa.String(length=120), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("receipt", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        inspector = sa.inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("refunds")}
    for name, columns, unique in (
        ("ix_refunds_tenant_id", ["tenant_id"], False),
        ("ix_refunds_branch_id", ["branch_id"], False),
        ("ix_refunds_order_id", ["order_id"], False),
        ("ix_refunds_payment_id", ["payment_id"], False),
        ("ix_refunds_provider", ["provider"], False),
        ("ix_refunds_gateway_refund_id", ["gateway_refund_id"], True),
        ("ix_refunds_status", ["status"], False),
        ("ix_refunds_receipt", ["receipt"], True),
    ):
        if name not in indexes:
            op.create_index(name, "refunds", columns, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    if "refunds" in sa.inspect(bind).get_table_names():
        op.drop_table("refunds")
