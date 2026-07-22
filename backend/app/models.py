import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return uuid.uuid4().hex


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    subscription_plan: Mapped[str] = mapped_column(String(64), default="trial")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_branch_code_per_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), index=True)
    custom_permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    variants: Mapped[list] = mapped_column(JSON, default=list)  # list of {name, price_delta}
    addons: Mapped[list] = mapped_column(JSON, default=list)  # list of {name, price}
    combo_items: Mapped[list] = mapped_column(JSON, default=list)  # list of product_ids
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductRecipe(Base):
    __tablename__ = "product_recipes"
    __table_args__ = (UniqueConstraint("product_id", "inventory_item_id", name="uq_product_recipe_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    inventory_item_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity_per_unit: Mapped[float] = mapped_column(Numeric(12, 3))
    wastage_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RestaurantTable(Base):
    __tablename__ = "tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String(32), default="available")  # available, occupied, reserved, cleaning, out_of_service
    floor_area: Mapped[str] = mapped_column(String(64), default="Ground Floor")  # Ground Floor, First Floor, Rooftop, etc.
    merged_with: Mapped[str | None] = mapped_column(String(36), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    table_id: Mapped[str | None] = mapped_column(ForeignKey("tables.id"), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    order_type: Mapped[str] = mapped_column(String(32), default="dine_in")
    status: Mapped[str] = mapped_column(String(32), default="held")
    kds_status: Mapped[str] = mapped_column(String(32), default="pending")
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(32), default="unpaid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(cascade="all, delete-orphan")
    refunds: Mapped[list["Refund"]] = relationship(cascade="all, delete-orphan")


class OnlineDeliveryOrder(Base):
    __tablename__ = "online_delivery_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "external_order_id", name="uq_delivery_external_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_order_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    customer_name: Mapped[str] = mapped_column(String(160), default="")
    customer_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_address: Mapped[str] = mapped_column(String(255), default="")
    rider_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    rider_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payment_mode: Mapped[str] = mapped_column(String(32), default="unknown")
    payment_status: Mapped[str] = mapped_column(String(32), default="pending")
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    commission_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    items: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DiscountRequest(Base):
    __tablename__ = "discount_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    requested_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_or_percentage: Mapped[float] = mapped_column(Numeric(12, 2))
    is_percentage: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2))
    variant_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    addons: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="captured")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gateway_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gateway_signature: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    gateway_refund_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(180))
    unit: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    low_stock_threshold: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    inventory_item_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    movement_type: Mapped[str] = mapped_column(String(32))  # adjustment, purchase, order_fulfillment, wastage
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, completed, cancelled
    items: Mapped[list] = mapped_column(JSON, default=list)  # list of {name, quantity, unit, unit_cost}
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    employee_id: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(64))  # manager, cashier, waiter, kitchen_staff, accountant
    joining_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Attendance(Base):
    __tablename__ = "attendances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shift_type: Mapped[str] = mapped_column(String(32), default="General")
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_status: Mapped[str] = mapped_column(String(32), default="none")  # none, pending, approved, rejected


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type: Mapped[str] = mapped_column(String(32))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payroll(Base):
    __tablename__ = "payrolls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    salary_period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    base_salary: Mapped[float] = mapped_column(Numeric(12, 2))
    allowances: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    incentives: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    net_salary: Mapped[float] = mapped_column(Numeric(12, 2))
    
    # Track final calculated days so historical records don't magically change
    present_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    absent_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payable_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_leave_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, processing, paid
    payment_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)  # cash, bank, upi, payroll
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payout_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payout_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payout_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommissionRule(Base):
    __tablename__ = "commission_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    target_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    incentive_rate: Mapped[float] = mapped_column(Numeric(5, 2))  # percentage


class Incentive(Base):
    __tablename__ = "incentives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    sales_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    incentive_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    incentive_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecuritySettings(Base):
    __tablename__ = "security_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), unique=True)
    password_min_length: Mapped[int] = mapped_column(Integer, default=8)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30)
    multi_device_login: Mapped[bool] = mapped_column(Boolean, default=True)
    two_factor_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    login_attempts_threshold: Mapped[int] = mapped_column(Integer, default=5)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
