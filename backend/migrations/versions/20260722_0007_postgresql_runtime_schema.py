"""move runtime schema changes into PostgreSQL migrations

Revision ID: 20260722_0007
Revises: 20260718_0006
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260722_0007"
down_revision = "20260718_0006"
branch_labels = None
depends_on = None


def column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in column_names(bind, table_name):
        op.add_column(table_name, column)


def create_index_if_missing(bind, name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "payments" in tables:
        add_column_if_missing(bind, "payments", sa.Column("provider", sa.String(length=32), nullable=True))
        add_column_if_missing(bind, "payments", sa.Column("gateway_order_id", sa.String(length=120), nullable=True))
        add_column_if_missing(bind, "payments", sa.Column("gateway_payment_id", sa.String(length=120), nullable=True))
        add_column_if_missing(bind, "payments", sa.Column("gateway_signature", sa.String(length=180), nullable=True))

    if "payrolls" in tables:
        add_column_if_missing(bind, "payrolls", sa.Column("payment_mode", sa.String(length=32), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("present_days", sa.Integer(), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("absent_days", sa.Integer(), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("payable_days", sa.Integer(), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("approved_leave_days", sa.Integer(), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("payment_reference", sa.String(length=120), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("payout_provider", sa.String(length=32), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("payout_id", sa.String(length=120), nullable=True))
        add_column_if_missing(bind, "payrolls", sa.Column("payout_status", sa.String(length=32), nullable=True))

    if "discount_requests" not in tables:
        op.create_table(
            "discount_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("requested_by_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("amount_or_percentage", sa.Numeric(12, 2), nullable=False),
            sa.Column("is_percentage", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "online_delivery_orders" not in tables:
        op.create_table(
            "online_delivery_orders",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("external_order_id", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
            sa.Column("customer_name", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("customer_phone", sa.String(length=40), nullable=True),
            sa.Column("delivery_address", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("rider_name", sa.String(length=160), nullable=True),
            sa.Column("rider_phone", sa.String(length=40), nullable=True),
            sa.Column("payment_mode", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "provider", "external_order_id", name="uq_delivery_external_order"),
        )

    indexes = (
        ("ix_branches_tenant_id", "branches", ["tenant_id"], False),
        ("ix_categories_branch_id", "categories", ["branch_id"], False),
        ("ix_categories_tenant_id", "categories", ["tenant_id"], False),
        ("ix_roles_name", "roles", ["name"], False),
        ("ix_roles_tenant_id", "roles", ["tenant_id"], False),
        ("ix_users_branch_id", "users", ["branch_id"], False),
        ("ix_users_email", "users", ["email"], True),
        ("ix_users_role", "users", ["role"], False),
        ("ix_users_tenant_id", "users", ["tenant_id"], False),
        ("ix_user_roles_branch_id", "user_roles", ["branch_id"], False),
        ("ix_user_roles_role_id", "user_roles", ["role_id"], False),
        ("ix_user_roles_tenant_id", "user_roles", ["tenant_id"], False),
        ("ix_user_roles_user_id", "user_roles", ["user_id"], False),
        ("ix_user_sessions_branch_id", "user_sessions", ["branch_id"], False),
        ("ix_user_sessions_refresh_token_hash", "user_sessions", ["refresh_token_hash"], True),
        ("ix_user_sessions_tenant_id", "user_sessions", ["tenant_id"], False),
        ("ix_user_sessions_user_id", "user_sessions", ["user_id"], False),
        ("ix_password_reset_tokens_tenant_id", "password_reset_tokens", ["tenant_id"], False),
        ("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], True),
        ("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], False),
        ("ix_products_branch_id", "products", ["branch_id"], False),
        ("ix_products_tenant_id", "products", ["tenant_id"], False),
        ("ix_tables_branch_id", "tables", ["branch_id"], False),
        ("ix_tables_tenant_id", "tables", ["tenant_id"], False),
        ("ix_customers_phone", "customers", ["phone"], False),
        ("ix_customers_tenant_id", "customers", ["tenant_id"], False),
        ("ix_orders_branch_id", "orders", ["branch_id"], False),
        ("ix_orders_tenant_id", "orders", ["tenant_id"], False),
        ("ix_order_items_order_id", "order_items", ["order_id"], False),
        ("ix_payments_order_id", "payments", ["order_id"], False),
        ("ix_suppliers_tenant_id", "suppliers", ["tenant_id"], False),
        ("ix_inventory_items_branch_id", "inventory_items", ["branch_id"], False),
        ("ix_inventory_items_tenant_id", "inventory_items", ["tenant_id"], False),
        ("ix_stock_movements_branch_id", "stock_movements", ["branch_id"], False),
        ("ix_stock_movements_inventory_item_id", "stock_movements", ["inventory_item_id"], False),
        ("ix_stock_movements_order_id", "stock_movements", ["order_id"], False),
        ("ix_stock_movements_tenant_id", "stock_movements", ["tenant_id"], False),
        ("ix_purchase_orders_branch_id", "purchase_orders", ["branch_id"], False),
        ("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"], False),
        ("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"], False),
        ("ix_employees_branch_id", "employees", ["branch_id"], False),
        ("ix_employees_tenant_id", "employees", ["tenant_id"], False),
        ("ix_employees_user_id", "employees", ["user_id"], False),
        ("ix_attendances_branch_id", "attendances", ["branch_id"], False),
        ("ix_attendances_employee_id", "attendances", ["employee_id"], False),
        ("ix_attendances_tenant_id", "attendances", ["tenant_id"], False),
        ("ix_payrolls_branch_id", "payrolls", ["branch_id"], False),
        ("ix_payrolls_employee_id", "payrolls", ["employee_id"], False),
        ("ix_payrolls_tenant_id", "payrolls", ["tenant_id"], False),
        ("ix_commission_rules_tenant_id", "commission_rules", ["tenant_id"], False),
        ("ix_incentives_branch_id", "incentives", ["branch_id"], False),
        ("ix_incentives_employee_id", "incentives", ["employee_id"], False),
        ("ix_incentives_tenant_id", "incentives", ["tenant_id"], False),
        ("ix_audit_logs_action", "audit_logs", ["action"], False),
        ("ix_audit_logs_branch_id", "audit_logs", ["branch_id"], False),
        ("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"], False),
        ("ix_discount_requests_branch_id", "discount_requests", ["branch_id"], False),
        ("ix_discount_requests_order_id", "discount_requests", ["order_id"], False),
        ("ix_discount_requests_requested_by_id", "discount_requests", ["requested_by_id"], False),
        ("ix_discount_requests_tenant_id", "discount_requests", ["tenant_id"], False),
        ("ix_leave_requests_branch_id", "leave_requests", ["branch_id"], False),
        ("ix_leave_requests_employee_id", "leave_requests", ["employee_id"], False),
        ("ix_leave_requests_tenant_id", "leave_requests", ["tenant_id"], False),
        ("ix_product_recipes_branch_id", "product_recipes", ["branch_id"], False),
        ("ix_product_recipes_inventory_item_id", "product_recipes", ["inventory_item_id"], False),
        ("ix_product_recipes_product_id", "product_recipes", ["product_id"], False),
        ("ix_product_recipes_tenant_id", "product_recipes", ["tenant_id"], False),
        ("ix_refunds_branch_id", "refunds", ["branch_id"], False),
        ("ix_refunds_gateway_refund_id", "refunds", ["gateway_refund_id"], True),
        ("ix_refunds_order_id", "refunds", ["order_id"], False),
        ("ix_refunds_payment_id", "refunds", ["payment_id"], False),
        ("ix_refunds_provider", "refunds", ["provider"], False),
        ("ix_refunds_receipt", "refunds", ["receipt"], True),
        ("ix_refunds_status", "refunds", ["status"], False),
        ("ix_refunds_tenant_id", "refunds", ["tenant_id"], False),
        ("ix_online_delivery_orders_branch_id", "online_delivery_orders", ["branch_id"], False),
        ("ix_online_delivery_orders_external_order_id", "online_delivery_orders", ["external_order_id"], False),
        ("ix_online_delivery_orders_order_id", "online_delivery_orders", ["order_id"], False),
        ("ix_online_delivery_orders_provider", "online_delivery_orders", ["provider"], False),
        ("ix_online_delivery_orders_status", "online_delivery_orders", ["status"], False),
        ("ix_online_delivery_orders_tenant_id", "online_delivery_orders", ["tenant_id"], False),
    )
    for name, table_name, columns, unique in indexes:
        create_index_if_missing(bind, name, table_name, columns, unique)

    composite_indexes = (
        ("ix_orders_tenant_branch_created", "orders", ["tenant_id", "branch_id", "created_at"]),
        ("ix_orders_tenant_branch_status", "orders", ["tenant_id", "branch_id", "status"]),
        ("ix_orders_tenant_branch_kds", "orders", ["tenant_id", "branch_id", "kds_status"]),
        ("ix_orders_tenant_branch_type", "orders", ["tenant_id", "branch_id", "order_type"]),
        ("ix_tables_tenant_branch_status", "tables", ["tenant_id", "branch_id", "status"]),
        ("ix_tables_merged_with", "tables", ["merged_with"]),
        ("ix_attendances_tenant_branch_checkin", "attendances", ["tenant_id", "branch_id", "check_in"]),
        ("ix_employees_tenant_branch_active", "employees", ["tenant_id", "branch_id", "active"]),
        ("ix_discount_requests_tenant_branch_status", "discount_requests", ["tenant_id", "branch_id", "status"]),
        ("ix_inventory_items_tenant_branch_qty", "inventory_items", ["tenant_id", "branch_id", "quantity"]),
        ("ix_purchase_orders_tenant_branch_created", "purchase_orders", ["tenant_id", "branch_id", "created_at"]),
        ("ix_user_sessions_tenant_branch_created", "user_sessions", ["tenant_id", "branch_id", "created_at"]),
        ("ix_online_delivery_branch_status", "online_delivery_orders", ["tenant_id", "branch_id", "status"]),
        ("ix_online_delivery_created", "online_delivery_orders", ["tenant_id", "branch_id", "created_at"]),
    )
    for name, table_name, columns in composite_indexes:
        create_index_if_missing(bind, name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "online_delivery_orders" in tables:
        op.drop_table("online_delivery_orders")
    if "discount_requests" in tables:
        op.drop_table("discount_requests")

    for table_name, columns in {
        "payments": ("gateway_signature", "gateway_payment_id", "gateway_order_id", "provider"),
        "payrolls": (
            "payout_status",
            "payout_id",
            "payout_provider",
            "payment_reference",
            "approved_leave_days",
            "payable_days",
            "absent_days",
            "present_days",
            "payment_mode",
        ),
    }.items():
        if table_name not in tables:
            continue
        existing = column_names(bind, table_name)
        for column_name in columns:
            if column_name in existing:
                op.drop_column(table_name, column_name)
