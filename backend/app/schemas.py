from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=160)
    owner_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=40)
    tenant_settings: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)


class RefundCreate(BaseModel):
    payment_id: str | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(default=None, max_length=255)
    speed: Literal["normal"] = "normal"


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=64)
    address: str = Field(default="", max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    settings: dict[str, Any] = Field(default_factory=dict)


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    status: Literal["active", "inactive"] | None = None
    settings: dict[str, Any] | None = None


class CategoryCreate(BaseModel):
    branch_id: str
    name: str = Field(min_length=1, max_length=160)


class ProductCreate(BaseModel):
    branch_id: str
    category_id: str | None = None
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    sku: str | None = Field(default=None, max_length=80)
    price: str
    tax_rate: str = "0.00"
    variants: list[dict[str, Any]] = Field(default_factory=list)
    addons: list[dict[str, Any]] = Field(default_factory=list)
    combo_items: list[str] = Field(default_factory=list)
    image_url: str | None = None
    available: bool = True


class ProductRecipeIngredient(BaseModel):
    inventory_item_id: str
    quantity_per_unit: str
    wastage_percent: str = "0.00"
    active: bool = True


class ProductRecipeUpdate(BaseModel):
    items: list[ProductRecipeIngredient] = Field(default_factory=list)


class TableCreate(BaseModel):
    branch_id: str
    name: str = Field(min_length=1, max_length=80)
    capacity: int = Field(default=2, ge=1, le=40)
    status: Literal["available", "occupied", "reserved", "cleaning", "out_of_service"] = "available"
    floor_area: str = Field(default="Ground Floor", min_length=1, max_length=64)


class TableFloorCreate(BaseModel):
    branch_id: str
    name: str = Field(min_length=1, max_length=64)


class TableFloorUpdate(BaseModel):
    branch_id: str
    current_name: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)


class TableMerge(BaseModel):
    table_id_1: str
    table_id_2: str


class TableSplit(BaseModel):
    table_id: str


class TableTransfer(BaseModel):
    from_table_id: str
    to_table_id: str


class TableReserve(BaseModel):
    table_id: str
    customer_name: str
    customer_phone: str


class UserCreate(BaseModel):
    branch_id: str | None = None
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["tenant_owner", "manager", "cashier", "waiter", "kitchen_staff", "platform_admin", "accountant"]
    permissions: list[str] | None = None


class UserUpdate(BaseModel):
    branch_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    role: Literal["manager", "cashier", "waiter", "kitchen_staff", "accountant"] | None = None
    status: Literal["active", "inactive"] | None = None
    permissions: list[str] | None = None
    locked: bool | None = None


class EmployeeCreate(BaseModel):
    branch_id: str
    employee_id: str | None = None
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = None
    role: Literal["manager", "cashier", "waiter", "kitchen_staff", "accountant"]
    base_salary: str | int | float = "0.00"
    password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool = True

class EmployeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = None
    role: Literal["manager", "cashier", "waiter", "kitchen_staff", "accountant"] | None = None
    base_salary: str | int | float | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool | None = None


class AttendanceAction(BaseModel):
    employee_id: str
    shift_type: str = "General"


class AttendanceUpdate(BaseModel):
    check_in: str | None = None
    check_out: str | None = None
    overtime_minutes: int | None = None
    overtime_status: Literal["none", "pending", "approved", "rejected"] | None = None


class LeaveCreate(BaseModel):
    branch_id: str
    employee_id: str
    type: Literal["sick", "vacation", "unpaid", "other"] = "sick"
    start_date: str
    end_date: str
    reason: str = Field(default="", max_length=500)


class LeaveUpdate(BaseModel):
    type: Literal["sick", "vacation", "unpaid", "other"] | None = None
    start_date: str | None = None
    end_date: str | None = None
    reason: str | None = Field(default=None, max_length=500)
    status: Literal["pending", "approved", "rejected"] | None = None


class PayrollPay(BaseModel):
    payment_mode: Literal["cash", "bank", "upi", "payroll"]
    payment_reference: str | None = Field(default=None, max_length=120)
    gateway_provider: Literal["razorpayx"] | None = None
    recipient_upi: str | None = Field(default=None, max_length=120)
    recipient_name: str | None = Field(default=None, max_length=160)
    recipient_email: EmailStr | None = None
    recipient_phone: str | None = Field(default=None, max_length=40)


class PayrollUpdate(BaseModel):
    day_salary: str | int | float | None = None
    base_salary: str | int | float | None = None
    allowances: str | int | float | None = None
    deductions: str | int | float | None = None
    incentives: str | int | float | None = None


class IncentiveCreate(BaseModel):
    branch_id: str | None = None
    employee_id: str | None = None  # if None, applies to all
    sales_amount: str | int | float = "0.00"
    incentive_amount: str | int | float = "0.00"


class IncentiveUpdate(BaseModel):
    employee_id: str | None = None
    sales_amount: str | int | float | None = None
    incentive_amount: str | int | float | None = None


class DiscountRequestCreate(BaseModel):
    order_id: str
    amount_or_percentage: str
    is_percentage: bool = False


class DiscountRequestApprove(BaseModel):
    status: Literal["approved", "rejected"]


class SecuritySettingsUpdate(BaseModel):
    password_min_length: int | None = None
    session_timeout_minutes: int | None = None
    multi_device_login: bool | None = None
    two_factor_auth: bool | None = None
    login_attempts_threshold: int | None = None


class InventoryItemCreate(BaseModel):
    branch_id: str
    name: str = Field(min_length=1, max_length=180)
    unit: str = Field(default="unit", max_length=40)
    quantity: str = "0.00"
    low_stock_threshold: str = "0.00"
    supplier_name: str | None = None


class InventoryItemAdjust(BaseModel):
    quantity: str
    notes: str | None = None


class PurchaseOrderCreate(BaseModel):
    branch_id: str
    supplier_name: str
    items: list[dict[str, Any]]


class OrderCreate(BaseModel):
    branch_id: str
    table_id: str | None = None
    customer: dict[str, Any] | None = None
    order_type: Literal["dine_in", "takeaway", "delivery"] = "dine_in"
    discount_amount: str = "0.00"
    items: list[dict[str, Any]]


class QrOrderAddonSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class QrOrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    quantity: int = Field(default=1, ge=1, le=99)
    variant_name: str | None = Field(default=None, max_length=120)
    addons: list[QrOrderAddonSelection] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=255)


class QrOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: str
    table_id: str
    customer_name: str = Field(default="QR Guest", max_length=160)
    customer_phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=500)
    items: list[QrOrderItem] = Field(min_length=1, max_length=100)


class OnlineDeliveryOrderItem(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=99)
    notes: str | None = Field(default=None, max_length=255)


class OnlineDeliveryOrderCreate(BaseModel):
    branch_id: str
    provider: Literal["swiggy", "zomato", "own", "other"]
    external_order_id: str = Field(min_length=2, max_length=80)
    customer_name: str = Field(default="Online Customer", max_length=160)
    customer_phone: str | None = Field(default=None, max_length=40)
    delivery_address: str = Field(default="", max_length=255)
    rider_name: str | None = Field(default=None, max_length=160)
    rider_phone: str | None = Field(default=None, max_length=40)
    payment_mode: Literal["prepaid", "cod", "upi", "card", "unknown"] = "unknown"
    payment_status: Literal["paid", "unpaid", "pending"] = "pending"
    commission_amount: str = "0.00"
    notes: str | None = Field(default=None, max_length=500)
    items: list[OnlineDeliveryOrderItem] = Field(min_length=1)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OnlineDeliveryStatusUpdate(BaseModel):
    status: Literal["new", "accepted", "rejected", "cancelled", "ready", "picked_up", "delivered"]


class PaymentsCreate(BaseModel):
    payments: list[dict[str, Any]]


class PaymentGatewayVerify(BaseModel):
    gateway_order_id: str = Field(min_length=4, max_length=120)
    gateway_payment_id: str = Field(min_length=4, max_length=120)
    gateway_signature: str = Field(min_length=20, max_length=180)


class KdsUpdate(BaseModel):
    kds_status: Literal["new", "accepted", "preparing", "ready", "served", "delivered"]


class ApiEnvelope(BaseModel):
    success: bool
    data: Any = None
    message: str = ""
    errors: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")
