"""phase1 foundation

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("subscription_plan", sa.String(64), server_default="trial"),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=True)

    op.create_table(
        "branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("address", sa.String(255), server_default=""),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_branch_code_per_tenant"),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.String(255), server_default=""),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(180), nullable=False, unique=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1"),
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0.00"),
        sa.Column("variants", sa.JSON(), nullable=True),
        sa.Column("addons", sa.JSON(), nullable=True),
        sa.Column("combo_items", sa.JSON(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("available", sa.Boolean(), server_default="1"),
    )

    op.create_table(
        "tables",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="2"),
        sa.Column("status", sa.String(32), server_default="available"),
        sa.Column("floor_area", sa.String(64), server_default="Ground Floor"),
        sa.Column("merged_with", sa.String(36), nullable=True),
        sa.Column("order_id", sa.String(36), nullable=True),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("table_id", sa.String(36), sa.ForeignKey("tables.id"), nullable=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("order_type", sa.String(32), server_default="dine_in"),
        sa.Column("status", sa.String(32), server_default="held"),
        sa.Column("kds_status", sa.String(32), server_default="pending"),
        sa.Column("subtotal", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("total", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("payment_status", sa.String(32), server_default="unpaid"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("variant_name", sa.String(120), nullable=True),
        sa.Column("addons", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference", sa.String(180), nullable=True),
        sa.Column("status", sa.String(32), server_default="captured"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("low_stock_threshold", sa.Numeric(12, 2), server_default="0.00"),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("inventory_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("po_number", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("employee_id", sa.String(60), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(180), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("joining_date", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "attendances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("check_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shift_type", sa.String(32), server_default="General"),
        sa.Column("late_minutes", sa.Integer(), server_default="0"),
        sa.Column("overtime_minutes", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "payrolls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("salary_period", sa.String(7), nullable=False),
        sa.Column("base_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("allowances", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("deductions", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("incentives", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("net_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "commission_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("incentive_rate", sa.Numeric(5, 2), nullable=False),
    )

    op.create_table(
        "incentives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("sales_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("incentive_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("incentive_date", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "security_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, unique=True),
        sa.Column("password_min_length", sa.Integer(), server_default="8"),
        sa.Column("session_timeout_minutes", sa.Integer(), server_default="30"),
        sa.Column("multi_device_login", sa.Boolean(), server_default="1"),
        sa.Column("two_factor_auth", sa.Boolean(), server_default="0"),
        sa.Column("login_attempts_threshold", sa.Integer(), server_default="5"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("security_settings")
    op.drop_table("incentives")
    op.drop_table("commission_rules")
    op.drop_table("payrolls")
    op.drop_table("attendances")
    op.drop_table("employees")
    op.drop_table("purchase_orders")
    op.drop_table("stock_movements")
    op.drop_table("inventory_items")
    op.drop_table("suppliers")
    op.drop_table("payments")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("customers")
    op.drop_table("tables")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("password_reset_tokens")
    op.drop_table("user_sessions")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("branches")
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
