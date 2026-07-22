from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import smtplib
import textwrap
from decimal import Decimal
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text, func, update
from sqlalchemy.orm import Session, selectinload

from . import database
from .database import Base, get_db
from .models import (
    AuditLog,
    Branch,
    Category,
    InventoryItem,
    DiscountRequest,
    Order,
    OnlineDeliveryOrder,
    Payment,
    Refund,
    PasswordResetToken,
    Product,
    RestaurantTable,
    Role,
    Tenant,
    User,
    Customer,
    UserRole,
    UserSession,
    StockMovement,
    PurchaseOrder,
    Employee,
    Attendance,
    LeaveRequest,
    Payroll,
    CommissionRule,
    Incentive,
    SecuritySettings,
    ProductRecipe,
)
from .security import (
    ROLE_PERMISSIONS,
    RateLimiter,
    create_token,
    current_user,
    decode_token,
    hash_token,
    hash_password,
    require_permission,
    verify_password,
)
from .schemas import (
    BranchCreate,
    BranchUpdate,
    CategoryCreate,
    InventoryItemCreate,
    InventoryItemAdjust,
    PurchaseOrderCreate,
    KdsUpdate,
    LoginRequest,
    LogoutRequest,
    OnlineDeliveryOrderCreate,
    OnlineDeliveryStatusUpdate,
    OrderCreate,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PaymentsCreate,
    PaymentGatewayVerify,
    RefundCreate,
    QrOrderCreate,
    ProductCreate,
    ProductRecipeUpdate,
    RefreshRequest,
    RegisterRequest,
    DiscountRequestCreate,
    DiscountRequestApprove,
    PayrollPay,
    PayrollUpdate,
    LeaveCreate,
    LeaveUpdate,
    IncentiveCreate,
    IncentiveUpdate,
    AttendanceUpdate,
    TableCreate,
    TableFloorCreate,
    TableFloorUpdate,
    UserCreate,
    UserUpdate,
    TableMerge,
    TableSplit,
    TableTransfer,
    TableReserve,
    EmployeeCreate,
    EmployeeUpdate,
    AttendanceAction,
    SecuritySettingsUpdate,
)
from .services import (
    CAPTURED_PAYMENT_STATUSES,
    apply_payments,
    audit,
    build_order,
    business_timezone,
    business_today,
    create_supplier_if_needed,
    dashboard_metrics,
    fulfill_order_inventory,
    list_product_recipe,
    local_date,
    manager_dashboard_metrics,
    money,
    normalize_payment_status,
    replace_product_recipe,
    reverse_order_inventory,
    serialize_order,
    serialize_product_recipe,
)

ROLE_NAMES = ["super_admin", "platform_admin", "tenant_owner", "manager", "cashier", "waiter", "kitchen_staff", "accountant"]
TENANT_USER_MANAGED_ROLES = {"manager", "cashier", "waiter", "kitchen_staff", "accountant"}
CUSTOMIZABLE_ROLES = TENANT_USER_MANAGED_ROLES | {"tenant_owner"}
PROTECTED_USER_ROLES = {"super_admin", "platform_admin", "tenant_owner"}
ADMIN_PERMISSION_CODES = {
    "admin:tenant",
    "branch:manage",
    "menu:manage",
    "menu:view",
    "order:manage",
    "order:view",
    "payment:manage",
    "table:manage",
    "table:view",
    "inventory:manage",
    "inventory:view",
    "kds:view",
    "kds:manage",
    "report:view",
    "user:manage",
    "employee:view",
    "employee:manage",
    "audit:view",
    "settings:manage",
    "customer:manage",
    "customer:view",
    "discount:manage",
    "refund:manage",
    "void:manage",
    "shift:manage",
    "shift:view",
    "drawer:manage",
}
RECEIPT_WIDTH = 42
RECEIPT_ITEM_WIDTH = 21
RECEIPT_QTY_WIDTH = 4
RECEIPT_RATE_WIDTH = 8
RECEIPT_AMOUNT_WIDTH = 9
RECEIPT_LABEL_WIDTH = 24
RECEIPT_VALUE_WIDTH = RECEIPT_WIDTH - RECEIPT_LABEL_WIDTH
DEFAULT_TABLE_FLOORS = ["Ground Floor", "First Floor", "Rooftop", "VIP Area"]


def receipt_center(value: str) -> str:
    return str(value or "")[:RECEIPT_WIDTH].center(RECEIPT_WIDTH)


def receipt_rule() -> str:
    return "-" * RECEIPT_WIDTH


def receipt_kv(label: str, value: str | Decimal | float | int) -> str:
    return f"{str(label)[:RECEIPT_LABEL_WIDTH]:<{RECEIPT_LABEL_WIDTH}}{str(value)[:RECEIPT_VALUE_WIDTH]:>{RECEIPT_VALUE_WIDTH}}"


def receipt_money(value: Decimal | float | int | str | None) -> str:
    return f"{money(value or 0):.2f}"


def receipt_item_lines(name: str, quantity: int, rate: Decimal, amount: Decimal) -> list[str]:
    wrapped_names = textwrap.wrap(name or "Item", width=RECEIPT_ITEM_WIDTH) or ["Item"]
    lines = [
        f"{wrapped_names[0]:<{RECEIPT_ITEM_WIDTH}}"
        f"{quantity:>{RECEIPT_QTY_WIDTH}}"
        f"{receipt_money(rate):>{RECEIPT_RATE_WIDTH}}"
        f"{receipt_money(amount):>{RECEIPT_AMOUNT_WIDTH}}"
    ]
    for extra_name in wrapped_names[1:]:
        lines.append(
            f"{extra_name:<{RECEIPT_ITEM_WIDTH}}"
            f"{'':>{RECEIPT_QTY_WIDTH}}"
            f"{'':>{RECEIPT_RATE_WIDTH}}"
            f"{'':>{RECEIPT_AMOUNT_WIDTH}}"
        )
    return lines


def build_receipt_print_data(db: Session, order: Order, user: User) -> dict:
    branch = db.get(Branch, order.branch_id)
    tenant = db.get(Tenant, order.tenant_id)
    table = db.get(RestaurantTable, order.table_id) if order.table_id else None
    branch_settings = branch.settings if branch and branch.settings else {}
    tenant_settings = tenant.settings if tenant and tenant.settings else {}
    receipt_name = (
        branch_settings.get("receipt_name")
        or tenant_settings.get("receipt_name")
        or (branch.name if branch else None)
        or (tenant.name if tenant else "Korvexa POS")
    )
    gst_number = branch_settings.get("gst_number") or tenant_settings.get("gst_number") or "-"
    upi_id = branch_settings.get("upi_id") or tenant_settings.get("upi_id") or "-"
    upi_qr_url = branch_settings.get("upi_qr_url") or tenant_settings.get("upi_qr_url") or ""
    receipt_footer = branch_settings.get("receipt_footer") or tenant_settings.get("receipt_footer") or "Thank you! Visit again."
    created_at = order.created_at or datetime.now(UTC)
    bill_no = f"ORD-{order.id[:8].upper()}"
    captured_payments = [payment for payment in order.payments if normalize_payment_status(payment.status) in CAPTURED_PAYMENT_STATUSES]
    paid_amount = sum((money(payment.amount) for payment in captured_payments), Decimal("0.00"))
    balance = max(money(order.total) - paid_amount, Decimal("0.00"))
    taxable_value = max(money(order.subtotal) - money(order.discount_amount), Decimal("0.00"))
    tax_amount = money(order.tax_amount)
    effective_tax_rate = Decimal("0.00") if taxable_value == 0 else money((tax_amount / taxable_value) * Decimal("100"))
    split_tax_rate = money(effective_tax_rate / Decimal("2"))
    split_tax_amount = money(tax_amount / Decimal("2"))
    payment_methods = sorted({payment.method.upper().replace("_", " ") for payment in captured_payments})
    payment_mode = "MIXED" if len(payment_methods) > 1 else (payment_methods[0] if payment_methods else "UNPAID")
    upi_payment_uri = ""
    if upi_id and upi_id != "-":
        upi_payment_uri = "upi://pay?" + urlencode({
            "pa": upi_id,
            "pn": receipt_name,
            "am": receipt_money(order.total),
            "cu": "INR",
            "tn": bill_no,
        })

    lines = [receipt_center(receipt_name)]
    if branch and branch.address:
        for address_line in textwrap.wrap(branch.address, width=RECEIPT_WIDTH):
            lines.append(receipt_center(address_line))
    lines.append(receipt_center(f"GSTIN: {gst_number}"))
    if branch and branch.phone:
        lines.append(receipt_center(f"Phone: {branch.phone}"))
    lines.extend([
        receipt_rule(),
        receipt_center(f"Order No: {bill_no}"),
        receipt_center(f"Date: {created_at.strftime('%Y-%m-%d %H:%M')}"),
    ])
    if order.order_type == "dine_in":
        lines.append(receipt_center(f"Table: {table.name if table else '-'}"))
    else:
        lines.append(receipt_center(f"Type: {order.order_type.replace('_', ' ').title()}"))
    lines.extend([
        receipt_center(f"KOT No: KOT-{order.id[-4:].upper()}"),
        receipt_center(f"Cashier: {user.name}"),
    ])
    waiter_name = branch_settings.get("waiter_name") or tenant_settings.get("waiter_name")
    if waiter_name:
        lines.append(receipt_center(f"Waiter: {waiter_name}"))
    lines.extend([
        receipt_rule(),
        f"{'Item':<{RECEIPT_ITEM_WIDTH}}{'Qty':>{RECEIPT_QTY_WIDTH}}{'Rate':>{RECEIPT_RATE_WIDTH}}{'Amt':>{RECEIPT_AMOUNT_WIDTH}}",
        receipt_rule(),
    ])
    for item in order.items:
        line_amount = money(item.unit_price) * int(item.quantity)
        lines.extend(receipt_item_lines(item.name, int(item.quantity), money(item.unit_price), line_amount))
    lines.extend([
        receipt_rule(),
        receipt_kv("Subtotal", receipt_money(order.subtotal)),
        receipt_kv("Discount", receipt_money(order.discount_amount)),
        receipt_kv("Taxable Value", receipt_money(taxable_value)),
        receipt_kv(f"CGST ({receipt_money(split_tax_rate)}%)", receipt_money(split_tax_amount)),
        receipt_kv(f"SGST ({receipt_money(split_tax_rate)}%)", receipt_money(split_tax_amount)),
        receipt_kv("Grand Total", receipt_money(order.total)),
        receipt_rule(),
        receipt_kv("Payment Mode", payment_mode),
        receipt_kv("Paid Amount", receipt_money(paid_amount)),
        receipt_kv("Balance", receipt_money(balance)),
        "",
        receipt_center("Scan & Pay"),
        receipt_center(f"UPI ID: {upi_id}"),
        receipt_center(f"Name: {receipt_name}"),
        receipt_rule(),
        receipt_center(receipt_footer),
        receipt_center("GST included as applicable"),
    ])
    return {
        "text": "\n".join(lines),
        "receipt_name": receipt_name,
        "gst_number": gst_number,
        "upi_id": upi_id,
        "upi_qr_url": upi_qr_url,
        "upi_payment_uri": upi_payment_uri,
        "bill_no": bill_no,
    }


class ApiV1EnvelopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1"):
            await self.app(scope, receive, send)
            return

        original_path = scope.get("path", "")
        is_delivery_webhook = (
            original_path.startswith("/api/v1/integrations/swiggy/online-delivery/webhook")
            or original_path.startswith("/api/v1/integrations/zomato/online-delivery/webhook")
        )
        scoped = dict(scope)
        stripped_path = scoped["path"][7:] or "/"
        scoped["path"] = stripped_path
        scoped["raw_path"] = stripped_path.encode("utf-8")
        messages = []

        async def capture(message):
            messages.append(message)

        await self.app(scoped, receive, capture)
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        headers = [(key.lower(), value) for key, value in start.get("headers", [])]
        content_type = next((value.decode("latin-1") for key, value in headers if key == b"content-type"), "")

        if "application/json" in content_type:
            status_code = start["status"]
            parsed = json.loads(body or b"null")
            is_success = status_code < 400
            if is_delivery_webhook and is_success:
                await send(start)
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            body = json.dumps(
                {
                    "success": is_success,
                    "data": parsed if is_success else None,
                    "message": "" if is_success else parsed.get("detail", "Request failed") if isinstance(parsed, dict) else "Request failed",
                    "errors": [] if is_success else [parsed],
                },
                separators=(",", ":"),
            ).encode("utf-8")
            start["headers"] = [
                item for item in start.get("headers", []) if item[0].lower() not in {b"content-length", b"content-type"}
            ]
            start["headers"].extend([(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())])

        await send(start)
        await send({"type": "http.response.body", "body": body, "more_body": False})


def token_expiry(minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def naive_utcnow() -> datetime:
    return datetime.now(UTC)


def password_reset_link(reset_token: str) -> str:
    base_url = frontend_reset_url_config()
    if not base_url:
        raise HTTPException(status_code=503, detail="Password reset URL is not configured")
    parsed = urlparse(base_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "token"]
    query.append(("token", reset_token))
    return parsed._replace(query=urlencode(query)).geturl()


def password_reset_email_provider() -> str | None:
    smtp_host = (os.getenv("SMTP_HOST") or "").strip().lower()
    if not env_present("SMTP_HOST"):
        return None
    if not smtp_host:
        return None
    if "gmail" in smtp_host or "google" in smtp_host:
        return "google_smtp"
    return "smtp"


def smtp_port_config() -> int | None:
    raw_port = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        port = int(raw_port)
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def send_smtp_email(to_email: str, subject: str, content: str) -> str:
    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    smtp_username = (os.getenv("SMTP_USERNAME") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip()
    configured_from = (os.getenv("SMTP_FROM") or "").strip()
    smtp_from = configured_from if env_present("SMTP_FROM") else smtp_username
    if not env_present("SMTP_HOST") or not (env_present("SMTP_FROM") or env_present("SMTP_USERNAME")):
        return "not_configured"
    if ("gmail" in smtp_host.lower() or "google" in smtp_host.lower()) and (not env_present("SMTP_USERNAME") or not env_present("SMTP_PASSWORD")):
        return "not_configured"
    if "gmail" in smtp_host.lower() or "google" in smtp_host.lower():
        smtp_password = "".join(smtp_password.split())
    smtp_port = smtp_port_config()
    if smtp_port is None:
        return "not_configured"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = to_email
    message.set_content(content)

    smtp_ssl = (os.getenv("SMTP_SSL", "") or "").lower() in {"1", "true", "yes"} or smtp_port == 465
    smtp_client = smtplib.SMTP_SSL if smtp_ssl else smtplib.SMTP
    with smtp_client(smtp_host, smtp_port, timeout=10) as smtp:
        if not smtp_ssl and (os.getenv("SMTP_TLS", "true") or "").lower() not in {"0", "false", "no"}:
            smtp.starttls()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)
    return "sent"


def send_password_reset_email(to_email: str, reset_link: str) -> str:
    return send_smtp_email(
        to_email,
        "Korvexa password reset",
        "We received a request to reset your Korvexa password.\n\n"
        f"Open this secure link to set a new password:\n{reset_link}\n\n"
        "This link expires in 30 minutes. If you did not request this, ignore this email.",
    )


def send_password_reset_test_email(to_email: str) -> str:
    return send_smtp_email(
        to_email,
        "Korvexa password reset mail test",
        "Korvexa password reset mail is configured correctly.\n\n"
        "This is a configuration test. No password reset was requested and no reset token was created.",
    )


def invalidate_unused_password_reset_tokens(db: Session, user_id: str, used_at: datetime) -> None:
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=used_at)
    )


def amount_to_paise(value: Decimal | float | int | str) -> int:
    return int(money(value) * Decimal("100"))


def captured_payment_total(order: Order) -> Decimal:
    return sum((money(payment.amount) for payment in order.payments if normalize_payment_status(payment.status) in CAPTURED_PAYMENT_STATUSES), Decimal("0.00"))


def reusable_gateway_payment(db: Session, order: Order, due_amount: Decimal) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.provider == "razorpay",
            Payment.status.in_({"pending", "created"}),
            Payment.gateway_order_id.is_not(None),
            Payment.amount == due_amount,
        )
        .order_by(Payment.created_at.desc())
    )


def gateway_payment_response(order: Order, payment: Payment, key_id: str, amount: Decimal, currency: str = "INR", reused: bool = False) -> dict:
    return {
        "provider": "razorpay",
        "key_id": key_id,
        "order_id": order.id,
        "gateway_order_id": payment.gateway_order_id,
        "amount": f"{amount:.2f}",
        "amount_paise": amount_to_paise(amount),
        "currency": currency,
        "reused": reused,
    }


def razorpayx_payout_idempotency_key(payroll: Payroll) -> str:
    payout_status = (payroll.payout_status or "").lower()
    if payout_status in {"failed", "reversed", "rejected", "cancelled", "canceled"}:
        retry_source = payroll.payout_id or payout_status
        return f"payroll-{payroll.id}-retry-{retry_source}"[:120]
    return f"payroll-{payroll.id}"[:120]


def razorpay_credentials(prefix: str = "RAZORPAY") -> tuple[str, str]:
    key_id = (os.getenv(f"{prefix}_KEY_ID") or "").strip()
    key_secret = (os.getenv(f"{prefix}_KEY_SECRET") or os.getenv(f"{prefix}_SECRET") or "").strip()
    if prefix == "RAZORPAYX":
        key_id = key_id or (os.getenv("RAZORPAY_KEY_ID") or "").strip()
        key_secret = key_secret or (os.getenv("RAZORPAY_KEY_SECRET") or os.getenv("RAZORPAY_SECRET") or "").strip()
    if not key_id or not key_secret or looks_like_placeholder(key_id) or looks_like_placeholder(key_secret):
        raise HTTPException(status_code=503, detail=f"{prefix} credentials are not configured")
    return key_id, key_secret


def razorpay_key_mode(prefix: str = "RAZORPAY") -> str:
    key_id = (os.getenv(f"{prefix}_KEY_ID") or "").strip()
    if prefix == "RAZORPAYX":
        key_id = key_id or (os.getenv("RAZORPAY_KEY_ID") or "").strip()
    if not key_id or looks_like_placeholder(key_id):
        return "not_configured"
    normalized = key_id.lower()
    if normalized.startswith("rzp_test_") or "_test_" in normalized:
        return "test"
    if normalized.startswith("rzp_live_") or "_live_" in normalized:
        return "live"
    return "unknown"


def looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return False
    placeholder_markers = (
        "your-",
        "your_",
        "replace-with",
        "change-me",
        "changeme",
        "_or_test_",
        " or test ",
    )
    return any(marker in normalized for marker in placeholder_markers)


def env_present(name: str) -> bool:
    value = (os.getenv(name) or "").strip()
    return bool(value) and not looks_like_placeholder(value)


def first_present_env(*names: str) -> str | None:
    for name in names:
        if env_present(name):
            return name
    return None


def public_https_url_config(*names: str, allow_query: bool = False, strip_trailing_slash: bool = False) -> str:
    for name in names:
        if not env_present(name):
            continue
        value = (os.getenv(name) or "").strip()
        try:
            parsed = urlparse(value)
            parsed_port = parsed.port
        except ValueError:
            continue
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or (parsed.query and not allow_query)
            or parsed.fragment
            or any(character.isspace() for character in value)
        ):
            continue
        if parsed_port is not None and not 1 <= parsed_port <= 65535:
            continue
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            continue
        try:
            if not ipaddress.ip_address(hostname).is_global:
                continue
        except ValueError:
            pass
        return value.rstrip("/") if strip_trailing_slash else value
    return ""


def public_api_base_url_config() -> str:
    return public_https_url_config(
        "PUBLIC_API_BASE_URL",
        "API_PUBLIC_BASE_URL",
        strip_trailing_slash=True,
    )


def frontend_reset_url_config() -> str:
    return public_https_url_config("FRONTEND_RESET_URL", allow_query=True)


def delivery_api_base_url_config(prefix: str) -> str:
    return public_https_url_config(f"{prefix}_API_BASE_URL", strip_trailing_slash=True)


def integration_status_payload(branch_id: str | None = None) -> dict:
    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    smtp_provider = password_reset_email_provider()
    smtp_port = smtp_port_config()
    frontend_reset_url = frontend_reset_url_config()
    public_api_base_url = public_api_base_url_config()
    webhook_paths = {
        "razorpay": "/api/v1/integrations/razorpay/webhook",
        "razorpayx": "/api/v1/integrations/razorpayx/webhook",
        "swiggy": "/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch_id}",
        "zomato": "/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch_id}",
    }

    def public_webhook_url(path: str) -> str:
        if branch_id:
            path = path.replace("{branch_id}", branch_id)
        return f"{public_api_base_url}{path}" if public_api_base_url else path

    smtp_missing = []
    if not env_present("SMTP_HOST"):
        smtp_missing.append("SMTP_HOST")
    if not (env_present("SMTP_FROM") or env_present("SMTP_USERNAME")):
        smtp_missing.append("SMTP_FROM")
    if smtp_provider == "google_smtp":
        if not env_present("SMTP_USERNAME"):
            smtp_missing.append("SMTP_USERNAME")
        if not env_present("SMTP_PASSWORD"):
            smtp_missing.append("SMTP_PASSWORD")
    if not frontend_reset_url:
        smtp_missing.append("FRONTEND_RESET_URL")
    if smtp_port is None:
        smtp_missing.append("SMTP_PORT")

    razorpay_missing = []
    if not env_present("RAZORPAY_KEY_ID"):
        razorpay_missing.append("RAZORPAY_KEY_ID")
    if not first_present_env("RAZORPAY_KEY_SECRET", "RAZORPAY_SECRET"):
        razorpay_missing.append("RAZORPAY_KEY_SECRET")
    if not env_present("RAZORPAY_WEBHOOK_SECRET"):
        razorpay_missing.append("RAZORPAY_WEBHOOK_SECRET")
    if not public_api_base_url:
        razorpay_missing.append("PUBLIC_API_BASE_URL")

    razorpayx_missing = []
    if not first_present_env("RAZORPAYX_KEY_ID", "RAZORPAY_KEY_ID"):
        razorpayx_missing.append("RAZORPAYX_KEY_ID")
    if not first_present_env("RAZORPAYX_KEY_SECRET", "RAZORPAYX_SECRET", "RAZORPAY_KEY_SECRET", "RAZORPAY_SECRET"):
        razorpayx_missing.append("RAZORPAYX_KEY_SECRET")
    if not env_present("RAZORPAYX_ACCOUNT_NUMBER"):
        razorpayx_missing.append("RAZORPAYX_ACCOUNT_NUMBER")
    if not env_present("RAZORPAYX_WEBHOOK_SECRET"):
        razorpayx_missing.append("RAZORPAYX_WEBHOOK_SECRET")
    if not public_api_base_url:
        razorpayx_missing.append("PUBLIC_API_BASE_URL")

    def delivery_status(prefix: str) -> dict:
        provider_key = prefix.lower()
        missing = []
        if not delivery_api_base_url_config(prefix):
            missing.append(f"{prefix}_API_BASE_URL")
        if not first_present_env(f"{prefix}_API_TOKEN", f"{prefix}_API_KEY"):
            missing.append(f"{prefix}_API_TOKEN")
        if not first_present_env(f"{prefix}_OUTLET_ID", f"{prefix}_RESTAURANT_ID"):
            missing.append(f"{prefix}_OUTLET_ID")
        if not env_present(f"{prefix}_WEBHOOK_SECRET"):
            missing.append(f"{prefix}_WEBHOOK_SECRET")
        if not public_api_base_url:
            missing.append("PUBLIC_API_BASE_URL")
        return {
            "configured": len(missing) == 0,
            "missing": missing,
            "auth_header": os.getenv(f"{prefix}_AUTH_HEADER", "Authorization"),
            "auth_scheme": os.getenv(f"{prefix}_AUTH_SCHEME", "Bearer"),
            "webhook_url": public_webhook_url(webhook_paths[provider_key]),
        }

    return {
        "password_reset_mail": {
            "configured": len(smtp_missing) == 0,
            "provider": smtp_provider or "not_configured",
            "missing": smtp_missing,
            "reset_url_configured": bool(frontend_reset_url),
            "smtp_host_configured": env_present("SMTP_HOST"),
            "smtp_ssl": (os.getenv("SMTP_SSL", "") or "").lower() in {"1", "true", "yes"} or smtp_port == 465,
        },
        "razorpay": {
            "configured": len(razorpay_missing) == 0,
            "missing": razorpay_missing,
            "webhook_url": public_webhook_url(webhook_paths["razorpay"]),
        },
        "razorpayx": {
            "configured": len(razorpayx_missing) == 0,
            "missing": razorpayx_missing,
            "webhook_url": public_webhook_url(webhook_paths["razorpayx"]),
        },
        "swiggy": delivery_status("SWIGGY"),
        "zomato": delivery_status("ZOMATO"),
    }


def validate_razorpay_order_response(request_payload: dict, response_payload: dict) -> None:
    expected_amount = request_payload.get("amount")
    returned_amount = response_payload.get("amount")
    if returned_amount is not None:
        try:
            if int(returned_amount) != int(expected_amount):
                raise HTTPException(status_code=502, detail="Razorpay request failed: amount mismatch")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid amount") from exc

    expected_currency = str(request_payload.get("currency") or "").strip().upper()
    returned_currency = str(response_payload.get("currency") or expected_currency).strip().upper()
    if expected_currency and returned_currency and returned_currency != expected_currency:
        raise HTTPException(status_code=502, detail="Razorpay request failed: currency mismatch")


def validate_razorpay_payout_response(request_payload: dict, response_payload: dict) -> None:
    expected_amount = request_payload.get("amount")
    returned_amount = response_payload.get("amount")
    if returned_amount is not None:
        try:
            if int(returned_amount) != int(expected_amount):
                raise HTTPException(status_code=502, detail="Razorpay request failed: amount mismatch")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid amount") from exc

    for field in ("currency", "mode"):
        expected = str(request_payload.get(field) or "").strip().upper()
        returned = str(response_payload.get(field) or expected).strip().upper()
        if expected and returned and returned != expected:
            raise HTTPException(status_code=502, detail=f"Razorpay request failed: {field} mismatch")


def razorpay_request(
    method: str,
    path: str,
    payload: dict | None,
    prefix: str = "RAZORPAY",
    idempotency_key: str | None = None,
    params: dict | None = None,
) -> dict:
    key_id, key_secret = razorpay_credentials(prefix)
    headers = {"Content-Type": "application/json"}
    if idempotency_key:
        idempotency_header = "X-Refund-Idempotency" if path.rstrip("/").endswith("/refund") else "X-Payout-Idempotency"
        headers[idempotency_header] = idempotency_key
    request_options = {
        "auth": (key_id, key_secret),
        "headers": headers,
        "timeout": 20,
    }
    if params is not None:
        request_options["params"] = params
    if payload is not None:
        request_options["json"] = payload
    try:
        response = httpx.request(
            method,
            f"https://api.razorpay.com/v1{path}",
            **request_options,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid response") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid response")
        is_create_request = method.strip().upper() == "POST"
        if is_create_request and path in {"/orders", "/payouts"} and not data.get("id"):
            raise HTTPException(status_code=502, detail="Razorpay request failed: missing id")
        if is_create_request and path == "/orders":
            validate_razorpay_order_response(payload or {}, data)
        if is_create_request and path == "/payouts":
            validate_razorpay_payout_response(payload or {}, data)
        return data
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Razorpay request failed: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Razorpay request failed") from exc


RAZORPAY_DASHBOARD_PAGE_SIZE = 100
RAZORPAY_DASHBOARD_MAX_RECORDS = 500


def fetch_razorpay_collection(path: str, prefix: str, params: dict) -> tuple[list[dict], bool]:
    items: list[dict] = []
    for skip in range(0, RAZORPAY_DASHBOARD_MAX_RECORDS, RAZORPAY_DASHBOARD_PAGE_SIZE):
        page = razorpay_request(
            "GET",
            path,
            None,
            prefix=prefix,
            params={
                **params,
                "count": RAZORPAY_DASHBOARD_PAGE_SIZE,
                "skip": skip,
            },
        )
        page_items = page.get("items")
        if not isinstance(page_items, list) or any(not isinstance(item, dict) for item in page_items):
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid collection")
        items.extend(page_items)
        if len(page_items) < RAZORPAY_DASHBOARD_PAGE_SIZE:
            return items, False
    return items, True


def provider_paise_rupees(value: object) -> Decimal:
    try:
        amount_paise = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Razorpay request failed: invalid amount") from exc
    if amount_paise < 0:
        raise HTTPException(status_code=502, detail="Razorpay request failed: invalid amount")
    return money(Decimal(amount_paise) / Decimal("100"))


def provider_rupees(entity: dict) -> Decimal:
    currency = str(entity.get("currency") or "").strip().upper()
    if currency != "INR":
        raise HTTPException(status_code=502, detail="Razorpay request failed: invalid currency")
    return provider_paise_rupees(entity.get("amount"))


def provider_created_at(entity: dict) -> int | None:
    value = entity.get("created_at")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def provider_section_error(resource: str, exc: HTTPException) -> tuple[str, str]:
    if exc.status_code == 503 and "credentials are not configured" in str(exc.detail):
        label = "RazorpayX" if resource == "payouts" else "Razorpay"
        return "not_configured", f"{label} account is not configured"
    label = "RazorpayX" if resource == "payouts" else "Razorpay"
    return "unavailable", f"{label} API is unavailable"


def payment_dashboard_section(
    provider_items: list[dict],
    truncated: bool,
    payment_id_to_order: dict[str, str],
    gateway_order_to_order: dict[str, str],
) -> dict:
    matched = [
        item
        for item in provider_items
        if str(item.get("id") or "") in payment_id_to_order
        or str(item.get("order_id") or "") in gateway_order_to_order
    ]
    counts = {"created": 0, "authorized": 0, "captured": 0, "refunded": 0, "failed": 0}
    amounts = {"captured": Decimal("0"), "authorized": Decimal("0"), "failed": Decimal("0")}
    compact_items = []
    for item in matched:
        amount = provider_rupees(item)
        status_value = str(item.get("status") or "").strip().lower()
        if status_value not in counts:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid payment status")
        counts[status_value] += 1
        if status_value in {"captured", "refunded"} or item.get("captured") is True:
            amounts["captured"] += amount
        elif status_value == "authorized":
            amounts["authorized"] += amount
        elif status_value == "failed":
            amounts["failed"] += amount
        payment_id = str(item.get("id") or "")
        gateway_order_id = str(item.get("order_id") or "")
        compact_items.append({
            "id": payment_id,
            "local_order_id": payment_id_to_order.get(payment_id) or gateway_order_to_order.get(gateway_order_id),
            "gateway_order_id": gateway_order_id or None,
            "amount": f"{amount:.2f}",
            "currency": "INR",
            "status": status_value,
            "method": str(item.get("method") or "unknown").strip().lower(),
            "amount_refunded": f"{provider_paise_rupees(item.get('amount_refunded') or 0):.2f}",
            "created_at": provider_created_at(item),
        })
    compact_items.sort(key=lambda item: item["created_at"] or 0, reverse=True)
    return {
        "status": "live",
        "scanned": len(provider_items),
        "matched": len(matched),
        "truncated": truncated,
        "counts": counts,
        "amounts": {key: f"{money(value):.2f}" for key, value in amounts.items()},
        "items": compact_items[:50],
    }


def refund_dashboard_section(
    provider_items: list[dict],
    truncated: bool,
    refund_id_to_order: dict[str, str],
    payment_id_to_order: dict[str, str],
) -> dict:
    matched = [
        item
        for item in provider_items
        if str(item.get("id") or "") in refund_id_to_order
        or str(item.get("payment_id") or "") in payment_id_to_order
    ]
    counts = {"pending": 0, "processed": 0, "failed": 0}
    amounts = {"pending": Decimal("0"), "processed": Decimal("0"), "failed": Decimal("0")}
    compact_items = []
    for item in matched:
        amount = provider_rupees(item)
        status_value = str(item.get("status") or "").strip().lower()
        if status_value not in counts:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid refund status")
        counts[status_value] += 1
        amounts[status_value] += amount
        refund_id = str(item.get("id") or "")
        payment_id = str(item.get("payment_id") or "")
        compact_items.append({
            "id": refund_id,
            "payment_id": payment_id or None,
            "local_order_id": refund_id_to_order.get(refund_id) or payment_id_to_order.get(payment_id),
            "amount": f"{amount:.2f}",
            "currency": "INR",
            "status": status_value,
            "created_at": provider_created_at(item),
        })
    compact_items.sort(key=lambda item: item["created_at"] or 0, reverse=True)
    return {
        "status": "live",
        "scanned": len(provider_items),
        "matched": len(matched),
        "truncated": truncated,
        "counts": counts,
        "amounts": {key: f"{money(value):.2f}" for key, value in amounts.items()},
        "items": compact_items[:50],
    }


def payout_dashboard_section(
    provider_items: list[dict],
    truncated: bool,
    payout_id_to_payroll: dict[str, str],
) -> dict:
    matched = [item for item in provider_items if str(item.get("id") or "") in payout_id_to_payroll]
    counts = {"processed": 0, "in_flight": 0, "failed": 0}
    amounts = {"processed": Decimal("0"), "in_flight": Decimal("0"), "failed": Decimal("0")}
    compact_items = []
    for item in matched:
        amount = provider_rupees(item)
        status_value = str(item.get("status") or "").strip().lower()
        if status_value in {"processed", "completed", "settled"}:
            bucket = "processed"
        elif status_value in {"queued", "pending", "processing"}:
            bucket = "in_flight"
        elif status_value in {"failed", "reversed", "rejected", "cancelled", "canceled"}:
            bucket = "failed"
        else:
            raise HTTPException(status_code=502, detail="Razorpay request failed: invalid payout status")
        counts[bucket] += 1
        amounts[bucket] += amount
        payout_id = str(item.get("id") or "")
        compact_items.append({
            "id": payout_id,
            "local_payroll_id": payout_id_to_payroll.get(payout_id),
            "amount": f"{amount:.2f}",
            "currency": "INR",
            "status": status_value,
            "mode": str(item.get("mode") or "unknown").strip().upper(),
            "purpose": str(item.get("purpose") or "payout").strip().lower(),
            "utr": str(item.get("utr") or "").strip() or None,
            "created_at": provider_created_at(item),
        })
    compact_items.sort(key=lambda item: item["created_at"] or 0, reverse=True)
    return {
        "status": "live",
        "scanned": len(provider_items),
        "matched": len(matched),
        "truncated": truncated,
        "counts": counts,
        "amounts": {key: f"{money(value):.2f}" for key, value in amounts.items()},
        "items": compact_items[:50],
    }


def unavailable_dashboard_section(resource: str, status_value: str, error: str) -> dict:
    if resource == "payments":
        counts = {"created": 0, "authorized": 0, "captured": 0, "refunded": 0, "failed": 0}
        amounts = {"captured": "0.00", "authorized": "0.00", "failed": "0.00"}
    elif resource == "refunds":
        counts = {"pending": 0, "processed": 0, "failed": 0}
        amounts = {"pending": "0.00", "processed": "0.00", "failed": "0.00"}
    else:
        counts = {"processed": 0, "in_flight": 0, "failed": 0}
        amounts = {"processed": "0.00", "in_flight": "0.00", "failed": "0.00"}
    return {
        "status": status_value,
        "error": error,
        "scanned": 0,
        "matched": 0,
        "truncated": False,
        "counts": counts,
        "amounts": amounts,
        "items": [],
    }


def razorpay_dashboard_snapshot(db: Session, user: User, branch_id: str, days: int = 30) -> dict:
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    query_params = {"from": int(start.timestamp()), "to": int(now.timestamp())}

    payment_rows = db.execute(
        select(Payment, Order.id)
        .join(Order, Payment.order_id == Order.id)
        .where(
            Order.tenant_id == user.tenant_id,
            Order.branch_id == branch_id,
            (
                (Payment.provider == "razorpay")
                | (Payment.method == "razorpay")
                | Payment.gateway_order_id.is_not(None)
                | Payment.gateway_payment_id.is_not(None)
            ),
        )
    ).all()
    payment_id_to_order = {
        str(payment.gateway_payment_id): order_id
        for payment, order_id in payment_rows
        if payment.gateway_payment_id
    }
    gateway_order_to_order = {
        str(payment.gateway_order_id): order_id
        for payment, order_id in payment_rows
        if payment.gateway_order_id
    }
    refund_rows = db.scalars(
        select(Refund).where(
            Refund.tenant_id == user.tenant_id,
            Refund.branch_id == branch_id,
            ((Refund.provider == "razorpay") | Refund.gateway_refund_id.is_not(None)),
        )
    ).all()
    refund_id_to_order = {
        str(refund.gateway_refund_id): refund.order_id
        for refund in refund_rows
        if refund.gateway_refund_id
    }
    payout_rows = db.scalars(
        select(Payroll).where(
            Payroll.tenant_id == user.tenant_id,
            Payroll.branch_id == branch_id,
            ((Payroll.payout_provider == "razorpayx") | Payroll.payout_id.is_not(None)),
        )
    ).all()
    payout_id_to_payroll = {
        str(payroll.payout_id): payroll.id
        for payroll in payout_rows
        if payroll.payout_id
    }

    try:
        payment_items, payment_truncated = fetch_razorpay_collection("/payments", "RAZORPAY", query_params)
        payments = payment_dashboard_section(
            payment_items,
            payment_truncated,
            payment_id_to_order,
            gateway_order_to_order,
        )
    except HTTPException as exc:
        status_value, error = provider_section_error("payments", exc)
        payments = unavailable_dashboard_section("payments", status_value, error)

    try:
        refund_items, refund_truncated = fetch_razorpay_collection("/refunds", "RAZORPAY", query_params)
        refunds = refund_dashboard_section(
            refund_items,
            refund_truncated,
            refund_id_to_order,
            payment_id_to_order,
        )
    except HTTPException as exc:
        status_value, error = provider_section_error("refunds", exc)
        refunds = unavailable_dashboard_section("refunds", status_value, error)

    account_number = (os.getenv("RAZORPAYX_ACCOUNT_NUMBER") or "").strip()
    if not account_number or looks_like_placeholder(account_number):
        payouts = unavailable_dashboard_section(
            "payouts",
            "not_configured",
            "RazorpayX account is not configured",
        )
    else:
        try:
            payout_items, payout_truncated = fetch_razorpay_collection(
                "/payouts",
                "RAZORPAYX",
                {**query_params, "account_number": account_number},
            )
            payouts = payout_dashboard_section(payout_items, payout_truncated, payout_id_to_payroll)
        except HTTPException as exc:
            status_value, error = provider_section_error("payouts", exc)
            payouts = unavailable_dashboard_section("payouts", status_value, error)

    section_statuses = [payments["status"], refunds["status"], payouts["status"]]
    complete = all(status_value == "live" for status_value in section_statuses)
    if complete:
        overall_status = "live"
    elif any(status_value == "live" for status_value in section_statuses):
        overall_status = "partial"
    elif all(status_value == "not_configured" for status_value in section_statuses):
        overall_status = "not_configured"
    else:
        overall_status = "unavailable"

    captured = money(payments["amounts"]["captured"])
    refunded = money(refunds["amounts"]["processed"])
    paid_out = money(payouts["amounts"]["processed"])
    net_flow = captured - refunded - paid_out if complete else None
    return {
        "source": "razorpay_api",
        "status": overall_status,
        "modes": {
            "payments": razorpay_key_mode("RAZORPAY"),
            "payouts": razorpay_key_mode("RAZORPAYX"),
        },
        "fetched_at": now.isoformat(),
        "window": {
            "days": days,
            "from": query_params["from"],
            "to": query_params["to"],
            "max_records_per_resource": RAZORPAY_DASHBOARD_MAX_RECORDS,
        },
        "payments": payments,
        "refunds": refunds,
        "payouts": payouts,
        "totals": {
            "captured": f"{captured:.2f}",
            "refunded": f"{refunded:.2f}",
            "payouts": f"{paid_out:.2f}",
            "net_flow": f"{money(net_flow):.2f}" if net_flow is not None else None,
            "complete": complete,
        },
    }


def verify_razorpay_signature(gateway_order_id: str, gateway_payment_id: str, gateway_signature: str) -> None:
    _, key_secret = razorpay_credentials("RAZORPAY")
    message = f"{gateway_order_id}|{gateway_payment_id}".encode("utf-8")
    expected = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, gateway_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")


def verify_razorpay_webhook_signature(
    body: bytes,
    gateway_signature: str | None,
    secret_name: str = "RAZORPAY_WEBHOOK_SECRET",
) -> None:
    secret = (os.getenv(secret_name) or "").strip()
    if not secret or looks_like_placeholder(secret):
        raise HTTPException(status_code=503, detail=f"{secret_name} is not configured")
    if not gateway_signature:
        raise HTTPException(status_code=401, detail="Missing Razorpay webhook signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, gateway_signature):
        raise HTTPException(status_code=401, detail="Invalid Razorpay webhook signature")


def validate_razorpay_payment_amount(payment: Payment, payment_entity: dict) -> None:
    provider_amount = payment_entity.get("amount")
    if provider_amount is None:
        raise HTTPException(status_code=422, detail="Razorpay payment amount is missing")
    try:
        captured_amount = int(provider_amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Razorpay payment amount is invalid") from exc
    if captured_amount != amount_to_paise(payment.amount):
        raise HTTPException(status_code=409, detail="Razorpay payment amount mismatch")

    provider_currency = str(payment_entity.get("currency") or "").strip().upper()
    if not provider_currency:
        raise HTTPException(status_code=422, detail="Razorpay payment currency is missing")
    if provider_currency != "INR":
        raise HTTPException(status_code=409, detail="Razorpay payment currency mismatch")


def confirm_razorpay_payment_capture(payment: Payment, gateway_payment_id: str) -> None:
    payment_path_id = quote(gateway_payment_id, safe="")
    provider_payment = razorpay_request("GET", f"/payments/{payment_path_id}", None)

    def validate_provider_payment(data: dict) -> None:
        if str(data.get("id") or "") != gateway_payment_id:
            raise HTTPException(status_code=409, detail="Razorpay payment id mismatch")
        if str(data.get("order_id") or "") != str(payment.gateway_order_id or ""):
            raise HTTPException(status_code=409, detail="Razorpay payment order mismatch")
        validate_razorpay_payment_amount(payment, data)

    validate_provider_payment(provider_payment)
    provider_status = str(provider_payment.get("status") or "").strip().lower()
    if provider_status == "authorized":
        provider_payment = razorpay_request(
            "POST",
            f"/payments/{payment_path_id}/capture",
            {"amount": amount_to_paise(payment.amount), "currency": "INR"},
        )
        validate_provider_payment(provider_payment)
        provider_status = str(provider_payment.get("status") or "").strip().lower()

    if provider_status != "captured" or provider_payment.get("captured") is False:
        raise HTTPException(status_code=409, detail=f"Razorpay payment is not captured ({provider_status or 'unknown'})")


def validate_razorpay_payout_amount(payroll: Payroll, payout_entity: dict) -> None:
    provider_amount = payout_entity.get("amount")
    if provider_amount is None:
        raise HTTPException(status_code=422, detail="Razorpay payout amount is missing")
    try:
        paid_amount = int(provider_amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Razorpay payout amount is invalid") from exc
    if paid_amount != amount_to_paise(payroll.net_salary):
        raise HTTPException(status_code=409, detail="Razorpay payout amount mismatch")
    provider_currency = str(payout_entity.get("currency") or "").strip().upper()
    if not provider_currency:
        raise HTTPException(status_code=422, detail="Razorpay payout currency is missing")
    if provider_currency != "INR":
        raise HTTPException(status_code=409, detail="Razorpay payout currency mismatch")


def capture_gateway_payment_record(db: Session, payment: Payment, gateway_payment_id: str, gateway_signature: str | None = None) -> Order:
    order = db.get(Order, payment.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if payment.status == "captured" and payment.gateway_payment_id == gateway_payment_id:
        return order
    if payment.status not in {"pending", "created"}:
        raise HTTPException(status_code=409, detail="Gateway payment is not pending")

    original_status = payment.status
    if captured_payment_total(order) + money(payment.amount) > money(order.total):
        raise HTTPException(status_code=409, detail="Order is already paid")
    payment.status = "captured"
    payment.reference = gateway_payment_id
    payment.gateway_payment_id = gateway_payment_id
    if gateway_signature:
        payment.gateway_signature = gateway_signature

    total_paid = captured_payment_total(order)
    order.payment_status = "paid" if total_paid >= money(order.total) else ("partial" if total_paid > 0 else "unpaid")
    if original_status == "created" and order.payment_status == "paid":
        order.status = "completed"
        fulfill_order_inventory(db, order)
        table = db.scalar(select(RestaurantTable).where(RestaurantTable.order_id == order.id))
        if table:
            table.status = "available"
            table.order_id = None
    return order


REFUND_ACTIVE_STATUSES = {"created", "pending", "processing"}
REFUND_PROCESSED_STATUSES = {"processed", "completed", "refunded"}
REFUND_FAILED_STATUSES = {"failed", "reversed", "rejected", "cancelled", "canceled"}


def razorpay_refund_receipt(
    payment_id: str,
    refund_amount_paise: int,
    previously_refunded_paise: int,
    retry_source: str | None = None,
) -> str:
    source = f"{payment_id}:{refund_amount_paise}:{previously_refunded_paise}:{retry_source or ''}"
    return f"refund-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}"


def serialize_refund(refund: Refund) -> dict:
    return {
        "id": refund.id,
        "order_id": refund.order_id,
        "payment_id": refund.payment_id,
        "provider": refund.provider,
        "gateway_refund_id": refund.gateway_refund_id,
        "amount": f"{money(refund.amount):.2f}",
        "currency": refund.currency,
        "status": refund.status,
        "reason": refund.reason,
        "receipt": refund.receipt,
        "created_at": refund.created_at.isoformat(),
        "updated_at": refund.updated_at.isoformat(),
    }


def validate_razorpay_refund_entity(refund: Refund, payment: Payment, entity: dict) -> None:
    gateway_refund_id = str(entity.get("id") or "").strip()
    if not gateway_refund_id:
        raise HTTPException(status_code=502, detail="Razorpay refund response missing id")
    if str(entity.get("payment_id") or "") != str(payment.gateway_payment_id or ""):
        raise HTTPException(status_code=409, detail="Razorpay refund payment mismatch")
    try:
        provider_amount = int(entity.get("amount"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Razorpay refund amount is invalid") from exc
    if provider_amount != amount_to_paise(refund.amount):
        raise HTTPException(status_code=409, detail="Razorpay refund amount mismatch")
    provider_currency = str(entity.get("currency") or "").strip().upper()
    if provider_currency and provider_currency != refund.currency.upper():
        raise HTTPException(status_code=409, detail="Razorpay refund currency mismatch")


def refresh_order_refund_status(db: Session, order: Order) -> None:
    refunds = db.scalars(select(Refund).where(Refund.order_id == order.id)).all()
    active_refund = any(str(refund.status or "").lower() in REFUND_ACTIVE_STATUSES for refund in refunds)
    processed_total = sum(
        (money(refund.amount) for refund in refunds if str(refund.status or "").lower() in REFUND_PROCESSED_STATUSES),
        Decimal("0.00"),
    )
    captured_total = captured_payment_total(order)
    if active_refund:
        order.payment_status = "refund_pending"
    elif processed_total > 0 and processed_total >= captured_total:
        order.payment_status = "refunded"
    elif processed_total > 0:
        order.payment_status = "partially_refunded"
    else:
        order.payment_status = "paid" if captured_total >= money(order.total) else ("partial" if captured_total > 0 else "unpaid")


def online_delivery_items_with_totals(db: Session, tenant_id: str, branch_id: str, items: list[dict]) -> tuple[list[dict], Decimal, Decimal]:
    serialized: list[dict] = []
    subtotal = Decimal("0.00")
    total = Decimal("0.00")
    for item in items:
        product = db.get(Product, item["product_id"])
        if product is None or product.tenant_id != tenant_id or product.branch_id != branch_id or not product.active:
            raise HTTPException(status_code=400, detail="Invalid delivery item")
        quantity = int(item.get("quantity", 1))
        unit_price = money(product.price)
        line_subtotal = money(unit_price * quantity)
        tax_rate = money(product.tax_rate)
        line_tax = money(line_subtotal * tax_rate / Decimal("100"))
        line_total = line_subtotal + line_tax
        subtotal += line_subtotal
        total += line_total
        serialized.append({
            "product_id": product.id,
            "name": product.name,
            "quantity": quantity,
            "unit_price": f"{unit_price:.2f}",
            "tax_rate": f"{tax_rate:.2f}",
            "line_total": f"{line_total:.2f}",
            "notes": item.get("notes"),
        })
    return serialized, money(subtotal), money(total)


def serialize_online_delivery(order: OnlineDeliveryOrder) -> dict:
    return {
        "id": order.id,
        "branch_id": order.branch_id,
        "order_id": order.order_id,
        "provider": order.provider,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "delivery_address": order.delivery_address,
        "rider_name": order.rider_name,
        "rider_phone": order.rider_phone,
        "payment_mode": order.payment_mode,
        "payment_status": order.payment_status,
        "subtotal": f"{money(order.subtotal):.2f}",
        "total": f"{money(order.total):.2f}",
        "commission_amount": f"{money(order.commission_amount):.2f}",
        "items": order.items or [],
        "notes": order.notes,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def online_delivery_provider_path(provider: str, action: str, record: OnlineDeliveryOrder) -> str:
    prefix = provider.upper()
    defaults = {
        "zomato": {
            "accepted": "/online-ordering/v1/order/confirm",
            "rejected": "/online-ordering/v1/order/reject",
            "ready": "/online-ordering/v1/order/ready",
            "picked_up": "/online-ordering/v1/order/pickedup",
            "delivered": "/online-ordering/v1/order/delivered",
        },
        "swiggy": {
            "accepted": "/orders/{external_order_id}/accept",
            "rejected": "/orders/{external_order_id}/reject",
            "ready": "/orders/{external_order_id}/ready",
            "picked_up": "/orders/{external_order_id}/picked-up",
            "delivered": "/orders/{external_order_id}/delivered",
        },
    }
    env_name = f"{prefix}_{action.upper()}_PATH"
    path = (os.getenv(env_name) or defaults.get(provider, {}).get(action) or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail=f"{provider} does not support {action} updates")
    return path.format(external_order_id=record.external_order_id, order_id=record.order_id or "")


def provider_failure_message(data: dict) -> str | None:
    failed = False
    for flag in ("success", "accepted", "ok"):
        if data.get(flag) is False:
            failed = True
            break
    if not failed and data.get("code") is not None:
        try:
            failed = int(data["code"]) >= 400
        except (TypeError, ValueError):
            pass
    if not failed:
        status_text = str(data.get("status") or data.get("code") or "").strip().lower().replace("-", "_").replace(" ", "_")
        failed = status_text in {"failed", "failure", "error", "rejected", "declined", "denied"}
    if not failed:
        return None
    message = (
        data.get("message")
        or data.get("error")
        or data.get("error_message")
        or data.get("reason")
        or data.get("detail")
        or "provider rejected the update"
    )
    return str(message).strip() or "provider rejected the update"


def notify_online_delivery_provider(record: OnlineDeliveryOrder, action: str, strict: bool = True) -> dict | None:
    provider = record.provider.lower()
    if provider not in {"swiggy", "zomato"}:
        return None
    prefix = provider.upper()
    base_url = delivery_api_base_url_config(prefix)
    token = ((os.getenv(f"{prefix}_API_TOKEN") or os.getenv(f"{prefix}_API_KEY") or "")).strip()
    outlet_id = ((os.getenv(f"{prefix}_OUTLET_ID") or os.getenv(f"{prefix}_RESTAURANT_ID") or "")).strip()
    if (
        not base_url
        or looks_like_placeholder(base_url)
        or not token
        or looks_like_placeholder(token)
        or not outlet_id
        or looks_like_placeholder(outlet_id)
    ):
        if strict:
            raise HTTPException(status_code=503, detail=f"{provider.title()} integration is not configured")
        return None

    auth_header = (os.getenv(f"{prefix}_AUTH_HEADER", "Authorization") or "Authorization").strip() or "Authorization"
    auth_scheme = (os.getenv(f"{prefix}_AUTH_SCHEME", "Bearer") or "").strip()
    headers = {"Content-Type": "application/json"}
    headers[auth_header] = f"{auth_scheme} {token}".strip() if auth_scheme else token
    payload = {
        "provider": provider,
        "order_id": record.external_order_id,
        "external_order_id": record.external_order_id,
        "pos_order_id": record.order_id,
        "status": action,
        "outlet_id": outlet_id or None,
        "amount": f"{money(record.total):.2f}",
        "items": record.items or [],
    }
    path = online_delivery_provider_path(provider, action, record)
    try:
        response = httpx.post(f"{base_url}{path}", json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            return {"status": "sent"}
        if isinstance(data, dict):
            failure_message = provider_failure_message(data)
            if failure_message:
                if strict:
                    raise HTTPException(status_code=502, detail=f"{provider.title()} update failed: {failure_message}")
                return None
        return data
    except httpx.HTTPStatusError as exc:
        if strict:
            raise HTTPException(status_code=502, detail=f"{provider.title()} update failed: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        if strict:
            raise HTTPException(status_code=502, detail=f"{provider.title()} update failed") from exc
    return None


def delivery_webhook_secret_valid(provider: str, body: bytes, headers: dict[str, str]) -> bool:
    prefix = provider.upper()
    secret = (os.getenv(f"{prefix}_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return False
    if looks_like_placeholder(secret):
        return False
    auth_header = (os.getenv(f"{prefix}_WEBHOOK_AUTH_HEADER") or "").strip().lower()
    auth_scheme = (os.getenv(f"{prefix}_WEBHOOK_AUTH_SCHEME") or "").strip()
    if auth_header:
        supplied_authorization = (headers.get(auth_header) or "").strip()
        expected_authorization = f"{auth_scheme} {secret}".strip() if auth_scheme else secret
        if supplied_authorization and hmac.compare_digest(supplied_authorization, expected_authorization):
            return True
    supplied_secret = (
        headers.get("x-korvexa-webhook-secret")
        or headers.get(f"x-{provider}-webhook-secret")
        or headers.get("x-webhook-secret")
    )
    supplied_secret = supplied_secret.strip() if supplied_secret else None
    if supplied_secret and hmac.compare_digest(supplied_secret, secret):
        return True
    signature = (
        headers.get(f"x-{provider}-signature")
        or headers.get("x-hub-signature-256")
        or headers.get("x-signature")
    )
    if not signature:
        return False
    signature = signature.removeprefix("sha256=").strip()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def first_present(data: dict, keys: list[str], default=None):
    for key in keys:
        value = data
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value not in (None, ""):
            return value
    return default


def has_meaningful_value(value: object) -> bool:
    return value not in (None, "") and str(value).strip() != ""


def resolve_delivery_product(db: Session, tenant_id: str, branch_id: str, item: dict) -> Product | None:
    raw_id = str(first_present(item, ["product_id", "merchant_item_id", "sku", "item_id", "id"], "") or "")
    name = str(first_present(item, ["name", "item_name", "title"], "") or "")
    query = select(Product).where(Product.tenant_id == tenant_id, Product.branch_id == branch_id, Product.active.is_(True))
    if raw_id:
        product = db.scalar(query.where((Product.id == raw_id) | (Product.sku == raw_id)))
        if product:
            return product
    if name:
        return db.scalar(query.where(func.lower(Product.name) == name.lower()))
    return None


def delivery_item_quantity(item: dict) -> int:
    raw_quantity = first_present(item, ["quantity", "qty"], 1)
    if raw_quantity in (None, ""):
        raw_quantity = 1
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid delivery item quantity") from exc
    if quantity <= 0:
        raise HTTPException(status_code=422, detail="Invalid delivery item quantity")
    return quantity


def delivery_item_amount(value: object) -> Decimal:
    amount = money(value)
    if amount < 0:
        raise HTTPException(status_code=422, detail="Invalid delivery item amount")
    return amount


def delivery_order_amount(value: object) -> Decimal:
    amount = money(value)
    if amount < 0:
        raise HTTPException(status_code=422, detail="Invalid delivery order amount")
    return amount


def normalize_delivery_status(raw_status: object, has_unmapped_items: bool) -> str:
    if has_unmapped_items:
        return "needs_mapping"
    status_text = str(raw_status or "").strip().lower().replace("-", "_").replace(" ", "_")
    status_map = {
        "": "new",
        "created": "new",
        "placed": "new",
        "received": "new",
        "new": "new",
        "accepted": "accepted",
        "confirmed": "accepted",
        "restaurant_accepted": "accepted",
        "ready": "ready",
        "food_ready": "ready",
        "order_ready": "ready",
        "ready_for_pickup": "ready",
        "restaurant_ready": "ready",
        "rejected": "rejected",
        "restaurant_rejected": "rejected",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "customer_cancelled": "cancelled",
        "picked_up": "picked_up",
        "pickedup": "picked_up",
        "dispatched": "picked_up",
        "delivered": "delivered",
        "completed": "delivered",
    }
    return status_map.get(status_text, "new")


def normalize_delivery_payment_status(raw_payment_status: object, raw_payment_mode: object) -> str:
    status_text = str(raw_payment_status or "").strip().lower().replace("-", "_").replace(" ", "_")
    mode_text = str(raw_payment_mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    if status_text in {"paid", "prepaid", "completed", "complete", "success", "successful", "captured", "settled"}:
        return "paid"
    if status_text in {"unpaid", "not_paid", "cod", "cash_on_delivery"}:
        return "unpaid"
    if status_text in {"pending", "authorized", "created"}:
        return "pending"
    if not status_text:
        if mode_text in {"cod", "cash", "cash_on_delivery", "pay_on_delivery"}:
            return "unpaid"
        if mode_text in {"prepaid", "online", "card", "upi", "wallet"}:
            return "paid"
    return status_text or "pending"


def should_apply_delivery_webhook_status(current_status: str, next_status: str) -> bool:
    terminal_statuses = {"cancelled", "rejected", "delivered"}
    if next_status in terminal_statuses:
        return True
    status_rank = {
        "new": 0,
        "needs_mapping": 0,
        "accepted": 1,
        "ready": 2,
        "picked_up": 3,
        "delivered": 4,
    }
    return status_rank.get(next_status, -1) >= status_rank.get(current_status, 0)


def sync_delivery_status_to_order(db: Session, record: OnlineDeliveryOrder) -> None:
    if not record.order_id:
        return
    linked_order = db.get(Order, record.order_id)
    if not linked_order:
        return
    if record.status in {"cancelled", "rejected"}:
        linked_order.status = "cancelled"
    elif record.status == "ready":
        linked_order.kds_status = "ready"
    elif record.status == "delivered":
        linked_order.status = "completed"
        linked_order.kds_status = "delivered"


def normalize_delivery_webhook_payload(db: Session, tenant_id: str, branch_id: str, provider: str, payload: dict) -> dict:
    order_data = payload.get("order") if isinstance(payload.get("order"), dict) else payload
    raw_items = first_present(order_data, ["items", "order_items", "cart.items"], []) or []
    has_items = isinstance(raw_items, list) and len(raw_items) > 0
    items: list[dict] = []
    subtotal = Decimal("0.00")
    total = Decimal("0.00")
    for raw_item in raw_items:
        product = resolve_delivery_product(db, tenant_id, branch_id, raw_item)
        quantity = delivery_item_quantity(raw_item)
        name = str(first_present(raw_item, ["name", "item_name", "title"], product.name if product else "Unmapped item"))
        unit_price = delivery_item_amount(first_present(raw_item, ["unit_price", "price", "item_price"], product.price if product else 0))
        line_total = delivery_item_amount(first_present(raw_item, ["line_total", "total", "final_price"], unit_price * quantity))
        subtotal += unit_price * quantity
        total += line_total
        items.append({
            "product_id": product.id if product else "",
            "name": name,
            "quantity": quantity,
            "unit_price": f"{unit_price:.2f}",
            "tax_rate": f"{money(product.tax_rate if product else 0):.2f}",
            "line_total": f"{line_total:.2f}",
            "notes": first_present(raw_item, ["notes", "instructions"]),
            "unmapped": product is None,
        })
    has_unmapped_items = any(item.get("unmapped") for item in items)
    raw_status = first_present(order_data, ["status", "order_status", "state", "event", "event_type"], "")
    has_status = has_meaningful_value(raw_status)
    status_text = str(raw_status or "").strip().lower().replace("-", "_").replace(" ", "_")
    known_status = has_unmapped_items or status_text in {
        "",
        "created",
        "placed",
        "received",
        "new",
        "accepted",
        "confirmed",
        "restaurant_accepted",
        "ready",
        "food_ready",
        "order_ready",
        "ready_for_pickup",
        "restaurant_ready",
        "rejected",
        "restaurant_rejected",
        "cancelled",
        "canceled",
        "customer_cancelled",
        "picked_up",
        "pickedup",
        "dispatched",
        "delivered",
        "completed",
    }
    customer_name = first_present(order_data, ["customer.name", "customer_name", "user.name"])
    customer_phone = first_present(order_data, ["customer.phone", "customer_phone", "user.phone"])
    delivery_address = first_present(order_data, ["delivery_address", "address", "customer.address"])
    rider_name = first_present(order_data, ["rider.name", "delivery_partner.name"])
    rider_phone = first_present(order_data, ["rider.phone", "delivery_partner.phone"])
    payment_mode = first_present(order_data, ["payment.mode", "payment_mode"])
    payment_status = first_present(order_data, ["payment.status", "payment_status"])
    explicit_subtotal = first_present(order_data, ["subtotal"])
    explicit_total = first_present(order_data, ["total", "amount", "order_total"])
    commission_amount = first_present(order_data, ["commission_amount", "commission"])
    notes = first_present(order_data, ["notes", "instructions"])
    normalized_subtotal = delivery_order_amount(explicit_subtotal if explicit_subtotal not in (None, "") else subtotal)
    normalized_total = delivery_order_amount(explicit_total if explicit_total not in (None, "") else total or subtotal)
    normalized_commission_amount = delivery_order_amount(commission_amount if commission_amount not in (None, "") else 0)
    return {
        "provider": provider,
        "external_order_id": str(first_present(order_data, ["external_order_id", "order_id", "id", "display_id"], "")),
        "status": normalize_delivery_status(raw_status, has_unmapped_items),
        "customer_name": str(customer_name or "Online Customer"),
        "customer_phone": customer_phone,
        "delivery_address": str(delivery_address or ""),
        "rider_name": rider_name,
        "rider_phone": rider_phone,
        "payment_mode": str(payment_mode or "unknown").lower(),
        "payment_status": normalize_delivery_payment_status(payment_status, payment_mode),
        "subtotal": normalized_subtotal,
        "total": normalized_total,
        "commission_amount": normalized_commission_amount,
        "items": items,
        "notes": notes,
        "raw_payload": payload,
        "has_customer_name": has_meaningful_value(customer_name),
        "has_customer_phone": has_meaningful_value(customer_phone),
        "has_delivery_address": has_meaningful_value(delivery_address),
        "has_rider_name": has_meaningful_value(rider_name),
        "has_rider_phone": has_meaningful_value(rider_phone),
        "has_payment_mode": has_meaningful_value(payment_mode),
        "has_payment_status": has_meaningful_value(payment_status),
        "has_subtotal": has_meaningful_value(explicit_subtotal),
        "has_total": has_meaningful_value(explicit_total),
        "has_commission_amount": has_meaningful_value(commission_amount),
        "has_items": has_items,
        "has_notes": has_meaningful_value(notes),
        "has_status": has_status,
        "known_status": known_status,
    }


def normalize_lock_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def issue_auth_pair(db: Session, user: User, user_agent: str | None = None) -> dict:
    settings = security_policy(db, user)
    access_minutes = max(5, min(int(settings.session_timeout_minutes or 60), 1440))
    if not settings.multi_device_login:
        revoke_user_sessions(db, user.id)
    session_id = secrets.token_hex(16)
    access_token = create_token(str(user.id), user.role, user.tenant_id, "access", access_minutes, jti=session_id)
    refresh_token = create_token(str(user.id), user.role, user.tenant_id, "refresh", 60 * 24 * 30, jti=session_id)
    db.add(
        UserSession(
            id=session_id,
            tenant_id=user.tenant_id,
            branch_id=user.branch_id,
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            user_agent=user_agent,
            expires_at=token_expiry(60 * 24 * 30),
        )
    )
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


def revoke_user_sessions(db: Session, user_id: str) -> None:
    now = naive_utcnow()
    sessions = db.scalars(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = now


def ensure_branch_access(user: User, branch_id: str) -> None:
    if user.role in {"super_admin", "platform_admin", "tenant_owner", "manager"}:
        return
    if user.branch_id != branch_id:
        raise HTTPException(status_code=403, detail="Branch access denied")


def get_accessible_branch(db: Session, user: User, branch_id: str) -> Branch:
    branch = db.get(Branch, branch_id)
    if not branch or branch.tenant_id != user.tenant_id or not branch.active:
        raise HTTPException(status_code=404, detail="Branch not found")
    ensure_branch_access(user, branch_id)
    return branch


def is_branch_deleted(branch: Branch) -> bool:
    return bool((branch.settings or {}).get("deleted"))


def normalize_floor_name(value: str | None) -> str:
    floor = " ".join((value or "").strip().split())
    if not floor:
        raise HTTPException(status_code=400, detail="Floor name is required")
    if len(floor) > 64:
        raise HTTPException(status_code=400, detail="Floor name must be 64 characters or less")
    return floor


def branch_table_floors(branch: Branch, tables: list[RestaurantTable] | None = None) -> list[str]:
    seen: set[str] = set()
    floors: list[str] = []
    settings = branch.settings or {}
    configured_floors = settings.get("table_floors")

    def add_floor(value: str | None) -> None:
        if not value:
            return
        floor = normalize_floor_name(value)
        key = floor.casefold()
        if key not in seen:
            seen.add(key)
            floors.append(floor)

    for floor in (configured_floors if isinstance(configured_floors, list) else DEFAULT_TABLE_FLOORS):
        add_floor(floor)
    for table in tables or []:
        add_floor(table.floor_area)
    return floors


def remember_branch_floor(branch: Branch, floor: str) -> None:
    settings = dict(branch.settings or {})
    floors = branch_table_floors(branch)
    if floor.casefold() not in {item.casefold() for item in floors}:
        floors.append(floor)
    settings["table_floors"] = floors
    branch.settings = settings


def save_branch_floors(branch: Branch, floors: list[str]) -> list[str]:
    settings = dict(branch.settings or {})
    seen: set[str] = set()
    normalized: list[str] = []
    for value in floors:
        floor = normalize_floor_name(value)
        key = floor.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(floor)
    if not normalized:
        normalized = ["Ground Floor"]
    settings["table_floors"] = normalized
    branch.settings = settings
    return normalized


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc


def each_day(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def payroll_period_window(period: str, today: date) -> tuple[date, date]:
    try:
        year, month = (int(part) for part in period.split("-", 1))
        start = date(year, month, 1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid payroll period") from exc
    end = date(year, month, monthrange(year, month)[1])
    current_period_start = date(today.year, today.month, 1)
    if start == current_period_start:
        end = min(end, today)
    elif start > current_period_start:
        end = start - timedelta(days=1)
    return start, end


def payroll_snapshot(db: Session, payroll: Payroll, employee: Employee | None) -> dict:
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    # Freeze the submitted amount while a gateway payout is processing and after it settles.
    if payroll.status in {"processing", "paid"} and payroll.payable_days is not None:
        return {
            "day_salary": money(payroll.base_salary),
            "incentives": money(payroll.incentives),
            "present_days": payroll.present_days or 0,
            "approved_leave_days": payroll.approved_leave_days or 0,
            "payable_days": payroll.payable_days or 0,
            "absent_days": payroll.absent_days or 0,
            "net_salary": money(payroll.net_salary),
        }
        
    tz = business_timezone(db, payroll.tenant_id, payroll.branch_id)
    start, end = payroll_period_window(payroll.salary_period, business_today(tz))
    elapsed_days = 0
    present_dates: set[date] = set()
    leave_dates: set[date] = set()

    if end >= start:
        elapsed_days = (end - start).days + 1
        attendances = db.scalars(
            select(Attendance).where(
                Attendance.tenant_id == payroll.tenant_id,
                Attendance.branch_id == payroll.branch_id,
                Attendance.employee_id == employee.id,
            )
        ).all()
        present_dates = {
            attendance_day
            for row in attendances
            for attendance_day in [local_date(row.check_in, tz)]
            if attendance_day and start <= attendance_day <= end
        }

        leaves = db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.tenant_id == payroll.tenant_id,
                LeaveRequest.branch_id == payroll.branch_id,
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        ).all()
        for leave in leaves:
            leave_start = max(leave.start_date, start)
            leave_end = min(leave.end_date, end)
            leave_dates.update(each_day(leave_start, leave_end))

    payable_dates = present_dates | leave_dates
    day_salary = money(payroll.base_salary)
    live_incentives = sum(
        (
            money(row.incentive_amount)
            for row in db.scalars(
                select(Incentive).where(
                    Incentive.tenant_id == payroll.tenant_id,
                    Incentive.branch_id == payroll.branch_id,
                    Incentive.employee_id == employee.id,
                )
            ).all()
            if start <= local_date(row.incentive_date, tz) <= end
        ),
        Decimal("0.00"),
    )
    total_incentives = money(payroll.incentives) + money(live_incentives)
    
    present_count = len(present_dates)
    leave_count = len(leave_dates)
    payable_count = len(payable_dates)
    absent_count = max(elapsed_days - payable_count, 0)
    
    net_salary = money((day_salary * payable_count) + money(payroll.allowances) + total_incentives - money(payroll.deductions))
    payroll.net_salary = net_salary
    
    # Update the payroll record dynamically so it populates in the database even while pending
    payroll.present_days = present_count
    payroll.approved_leave_days = leave_count
    payroll.payable_days = payable_count
    payroll.absent_days = absent_count
    
    return {
        "day_salary": day_salary,
        "incentives": total_incentives,
        "present_days": present_count,
        "approved_leave_days": leave_count,
        "payable_days": payable_count,
        "absent_days": absent_count,
        "net_salary": net_salary,
    }


def serialize_leave_request(leave: LeaveRequest, employee: Employee | None) -> dict:
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "id": leave.id,
        "employee_id": employee.employee_id,
        "employee_record_id": employee.id,
        "name": employee.name,
        "type": leave.leave_type,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "reason": leave.reason,
        "status": leave.status,
        "applied_on": leave.created_at.strftime("%Y-%m-%d"),
    }


def login_attempt_threshold(db: Session, user: User) -> int:
    settings = db.scalar(select(SecuritySettings).where(SecuritySettings.tenant_id == user.tenant_id))
    threshold = settings.login_attempts_threshold if settings else 5
    return max(1, min(int(threshold or 5), 20))


def security_policy(db: Session, user: User) -> SecuritySettings:
    settings = db.scalar(select(SecuritySettings).where(SecuritySettings.tenant_id == user.tenant_id))
    if settings:
        return settings
    settings = SecuritySettings(tenant_id=user.tenant_id)
    db.add(settings)
    db.flush()
    return settings


def password_policy_min_length(db: Session, user: User) -> int:
    settings = security_policy(db, user)
    return max(8, min(int(settings.password_min_length or 8), 128))


def validate_password_policy(db: Session, user: User, password: str) -> None:
    min_length = password_policy_min_length(db, user)
    if len(password or "") < min_length:
        raise HTTPException(status_code=422, detail=f"Password must be at least {min_length} characters")


def default_role_permissions() -> dict[str, list[str]]:
    return {
        role: sorted(permission for permission in ROLE_PERMISSIONS.get(role, set()) if permission != "*")
        for role in CUSTOMIZABLE_ROLES
    }


def tenant_role_permissions(tenant: Tenant) -> dict[str, list[str]]:
    configured = (tenant.settings or {}).get("role_permissions", {})
    defaults = default_role_permissions()
    if not isinstance(configured, dict):
        return defaults
    return {
        role: sorted(
            permission
            for permission in configured.get(role, defaults.get(role, []))
            if permission in ADMIN_PERMISSION_CODES
        )
        for role in CUSTOMIZABLE_ROLES
    }


def sanitize_role_permissions(payload: dict) -> dict[str, list[str]]:
    sanitized: dict[str, list[str]] = {}
    for role, permissions in payload.items():
        if role not in CUSTOMIZABLE_ROLES:
            raise HTTPException(status_code=400, detail=f"Role {role} cannot be managed here")
        if not isinstance(permissions, list):
            raise HTTPException(status_code=422, detail=f"Permissions for {role} must be a list")
        invalid = [permission for permission in permissions if permission not in ADMIN_PERMISSION_CODES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Unknown permission: {invalid[0]}")
        sanitized[role] = sorted(set(permissions))
    defaults = default_role_permissions()
    return {role: sanitized.get(role, defaults.get(role, [])) for role in CUSTOMIZABLE_ROLES}


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "branch_id": user.branch_id,
        "status": "active" if user.active else "inactive",
        "locked": bool(user.locked_until and user.locked_until > naive_utcnow()),
        "permissions": (user.custom_permissions or {}).get("grants", []),
    }


def ensure_can_manage_user(actor: User, target: User | None = None, role: str | None = None) -> None:
    if actor.role in {"super_admin", "platform_admin"}:
        return
    if target and target.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = role or (target.role if target else None)
    
    is_owner_managing_owner = (actor.role == "tenant_owner" and target_role == "tenant_owner")
    
    if target_role in PROTECTED_USER_ROLES and not is_owner_managing_owner:
        raise HTTPException(status_code=403, detail="Protected user role cannot be managed here")
    if actor.role == "manager" and target_role == "manager":
        raise HTTPException(status_code=403, detail="Managers cannot create or manage manager accounts")
    if target_role and target_role not in TENANT_USER_MANAGED_ROLES and not is_owner_managing_owner:
        raise HTTPException(status_code=403, detail="Role cannot be assigned")


def configured_cors_origins() -> list[str]:
    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if os.getenv("ENVIRONMENT", "development").lower() == "production" and "*" in origins:
        raise RuntimeError("CORS_ORIGINS cannot contain '*' in production")
    return origins

def create_app() -> FastAPI:
    database.reset_engine_from_env()
    if database.engine.dialect.name != "postgresql":
        raise RuntimeError("Korvexa requires PostgreSQL")

    app = FastAPI(title="Korvexa POS API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiV1EnvelopeMiddleware)
    app.middleware("http")(RateLimiter())

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        live_tables = set(inspect(db.get_bind()).get_table_names())
        missing_tables = sorted(set(Base.metadata.tables) - live_tables)
        if missing_tables:
            raise HTTPException(
                status_code=503,
                detail=f"Database schema is incomplete; missing tables: {', '.join(missing_tables)}",
            )
        return {"status": "ready", "database": "ok"}

    @app.get("/integrations/status")
    def integrations_status(branch_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
        if branch_id:
            get_accessible_branch(db, user, branch_id)
        return integration_status_payload(branch_id)

    @app.get("/integrations/razorpay/dashboard")
    def integrations_razorpay_dashboard(
        branch_id: str,
        days: int = 30,
        user: User = Depends(require_permission("report:view")),
        db: Session = Depends(get_db),
    ):
        if days < 1 or days > 90:
            raise HTTPException(status_code=422, detail="Dashboard window must be between 1 and 90 days")
        get_accessible_branch(db, user, branch_id)
        return razorpay_dashboard_snapshot(db, user, branch_id, days)

    @app.post("/integrations/password-reset-mail/test")
    def test_password_reset_mail(
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("settings:manage")),
    ):
        if not integration_status_payload()["password_reset_mail"]["configured"]:
            raise HTTPException(status_code=503, detail="Password reset mail is not configured")
        try:
            email_delivery = send_password_reset_test_email(user.email)
        except smtplib.SMTPAuthenticationError as exc:
            raise HTTPException(status_code=502, detail="SMTP authentication failed") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise HTTPException(status_code=502, detail="SMTP delivery failed") from exc
        if email_delivery != "sent":
            raise HTTPException(status_code=503, detail="Password reset mail is not configured")
        audit(db, "integration.password_reset_mail_tested", "user", user.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"email_delivery": "sent", "recipient": user.email}

    @app.post("/auth/register", status_code=201)
    def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
        payload = payload.model_dump()
        if db.scalar(select(User).where(User.email == payload["email"])):
            raise HTTPException(status_code=409, detail="Email already exists")
        if db.scalar(select(Tenant).where(Tenant.name == payload["tenant_name"])):
            raise HTTPException(status_code=409, detail="Tenant already exists")
        tenant = Tenant(name=payload["tenant_name"], settings=payload.get("tenant_settings") or {})
        db.add(tenant)
        db.flush()
        # Seed security policy for this tenant
        db.add(SecuritySettings(tenant_id=tenant.id))
        for name in ROLE_NAMES:
            db.add(Role(tenant_id=tenant.id, name=name))
        user = User(
            tenant_id=tenant.id,
            name=payload["owner_name"],
            email=payload["email"],
            phone=payload.get("phone"),
            password_hash=hash_password(payload["password"]),
            role="tenant_owner",
        )
        db.add(user)
        db.flush()
        owner_role = db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.name == "tenant_owner"))
        if owner_role:
            db.add(UserRole(tenant_id=tenant.id, user_id=user.id, role_id=owner_role.id))
        audit(db, "tenant.registered", "tenant", tenant.id, user=user, tenant_id=tenant.id)
        auth = issue_auth_pair(db, user, request.headers.get("user-agent"))
        db.commit()
        return {
            "tenant": {"id": tenant.id, "name": tenant.name, "status": tenant.status},
            "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
            **auth,
        }

    @app.post("/auth/login")
    def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
        payload = payload.model_dump()
        user = db.scalar(select(User).where(User.email == payload["email"]))
        now = naive_utcnow()
        locked_until = normalize_lock_time(user.locked_until) if user else None
        if user and locked_until and locked_until > now:
            raise HTTPException(status_code=423, detail="Account temporarily locked")
        if user is None or not verify_password(payload["password"], user.password_hash):
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= login_attempt_threshold(db, user):
                    user.locked_until = now + timedelta(minutes=15)
                audit(db, "auth.login_failed", "user", user.id, user=user, tenant_id=user.tenant_id)
                db.commit()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.active:
            audit(db, "auth.login_blocked_inactive_user", "user", user.id, user=user, tenant_id=user.tenant_id)
            db.commit()
            raise HTTPException(status_code=403, detail="User account is inactive")
        if user.tenant_id:
            tenant = db.get(Tenant, user.tenant_id)
            if tenant is None or tenant.status != "active":
                audit(db, "auth.login_blocked_inactive_tenant", "user", user.id, user=user, tenant_id=user.tenant_id)
                db.commit()
                raise HTTPException(status_code=403, detail="Tenant is not active")
        user.failed_login_attempts = 0
        user.locked_until = None
        audit(db, "auth.login", "user", user.id, user=user, tenant_id=user.tenant_id)
        auth = issue_auth_pair(db, user, request.headers.get("user-agent"))
        db.commit()
        return {**auth, "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}

    @app.post("/auth/refresh")
    def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
        payload = payload.model_dump()
        token_payload = decode_token(payload["refresh_token"], expected_type="refresh")
        user = db.get(User, str(token_payload["sub"]))
        locked_until = normalize_lock_time(user.locked_until) if user else None
        if not user or not user.active or (locked_until and locked_until > naive_utcnow()):
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if user.tenant_id:
            tenant = db.get(Tenant, user.tenant_id)
            if tenant is None or tenant.status != "active":
                raise HTTPException(status_code=401, detail="Invalid refresh token")
        session = db.scalar(
            select(UserSession).where(
                UserSession.refresh_token_hash == hash_token(payload["refresh_token"]),
                UserSession.user_id == user.id,
            )
        )
        now = naive_utcnow()
        if session is None or session.revoked_at is not None or normalize_lock_time(session.expires_at) <= now:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        session.revoked_at = now
        auth = issue_auth_pair(db, user, request.headers.get("user-agent"))
        audit(db, "auth.refresh_rotated", "user_session", session.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return auth

    @app.post("/auth/logout")
    def logout(payload: LogoutRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
        payload = payload.model_dump()
        session = db.scalar(
            select(UserSession).where(
                UserSession.refresh_token_hash == hash_token(payload["refresh_token"]),
                UserSession.user_id == user.id,
            )
        )
        if session and session.revoked_at is None:
            session.revoked_at = naive_utcnow()
            audit(db, "auth.logout", "user_session", session.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"message": "Logged out"}

    @app.post("/auth/password-reset/request")
    def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
        payload = payload.model_dump()
        lookup_email = str(payload["email"]).strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == lookup_email))
        if user:
            reset_token = create_token(str(user.id), user.role, user.tenant_id, "password_reset", 30)
            email_provider = password_reset_email_provider()
            email_delivery = "not_configured"
            invalidate_unused_password_reset_tokens(db, user.id, naive_utcnow())
            db.add(
                PasswordResetToken(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    token_hash=hash_token(reset_token),
                    expires_at=token_expiry(30),
                )
            )
            audit(db, "auth.password_reset_requested", "user", user.id, user=user, tenant_id=user.tenant_id)
            db.commit()
            if email_provider and frontend_reset_url_config():
                try:
                    email_delivery = send_password_reset_email(user.email, password_reset_link(reset_token))
                except Exception:
                    email_delivery = "failed"
            response = {"message": "Password reset requested", "email_delivery": email_delivery}
            response["email_provider"] = email_provider or "not_configured"
            if os.getenv("EXPOSE_DEV_RESET_TOKEN") == "true":
                response["reset_token"] = reset_token
            return response
        return {"message": "Password reset requested"}

    @app.post("/auth/password-reset/confirm")
    def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
        payload = payload.model_dump()
        token_payload = decode_token(payload["token"], expected_type="password_reset")
        reset = db.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_token(payload["token"]),
                PasswordResetToken.used_at.is_(None),
            )
        )
        now = naive_utcnow()
        if reset is None or normalize_lock_time(reset.expires_at) <= now:
            raise HTTPException(status_code=401, detail="Invalid reset token")
        user = db.get(User, str(token_payload["sub"]))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        validate_password_policy(db, user, payload["new_password"])
        user.password_hash = hash_password(payload["new_password"])
        user.failed_login_attempts = 0
        user.locked_until = None
        reset.used_at = now
        invalidate_unused_password_reset_tokens(db, user.id, now)
        revoke_user_sessions(db, user.id)
        audit(db, "auth.password_reset_completed", "user", user.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"message": "Password reset complete"}

    @app.post("/admin/tenants", status_code=201)
    def create_tenant(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("*"))):
        tenant = Tenant(name=payload["name"], subscription_plan=payload.get("subscription_plan", "trial"))
        db.add(tenant)
        db.flush()
        db.add(SecuritySettings(tenant_id=tenant.id))
        audit(db, "tenant.created", "tenant", tenant.id, user=user, tenant_id=tenant.id)
        db.commit()
        return {"id": tenant.id, "name": tenant.name, "status": tenant.status}

    @app.patch("/admin/tenants/{tenant_id}")
    def update_tenant(
        tenant_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("*"))
    ):
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        for key in ("name", "status", "subscription_plan", "settings"):
            if key in payload:
                setattr(tenant, key, payload[key])
        audit(db, "tenant.updated", "tenant", tenant.id, user=user, tenant_id=tenant.id)
        db.commit()
        return {"id": tenant.id, "name": tenant.name, "status": tenant.status}

    @app.get("/admin/tenants")
    def list_tenants(db: Session = Depends(get_db), user: User = Depends(require_permission("*"))):
        return {"items": [{"id": t.id, "name": t.name, "status": t.status} for t in db.scalars(select(Tenant)).all()]}

    @app.post("/branches", status_code=201)
    def create_branch(
        payload: BranchCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("branch:manage"))
    ):
        payload = payload.model_dump()
        branch = Branch(
            tenant_id=user.tenant_id,
            name=payload["name"],
            code=payload.get("code") or payload["name"].upper().replace(" ", "-"),
            address=payload.get("address", ""),
            phone=payload.get("phone"),
            settings=payload.get("settings") or {},
        )
        db.add(branch)
        db.flush()
        audit(db, "branch.created", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {"id": branch.id, "name": branch.name, "code": branch.code, "settings": branch.settings}

    @app.get("/branches")
    def list_branches(db: Session = Depends(get_db), user: User = Depends(current_user)):
        rows = db.scalars(select(Branch).where(Branch.tenant_id == user.tenant_id)).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "code": row.code,
                    "address": row.address,
                    "phone": row.phone,
                    "active": row.active,
                    "status": "active" if row.active else "inactive",
                }
                for row in rows
                if not is_branch_deleted(row)
            ]
        }

    
    @app.delete("/branches/{branch_id}")
    def delete_branch(
        branch_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("branch:manage"))
    ):
        branch = db.get(Branch, branch_id)
        if not branch or branch.tenant_id != user.tenant_id or is_branch_deleted(branch):
            raise HTTPException(status_code=404, detail="Branch not found")
        ensure_branch_access(user, branch_id)
        visible_branches = db.scalars(select(Branch).where(Branch.tenant_id == user.tenant_id)).all()
        remaining_store_count = sum(1 for row in visible_branches if row.id != branch_id and not is_branch_deleted(row))
        if remaining_store_count <= 0:
            raise HTTPException(status_code=400, detail="Cannot delete the only remaining branch")

        branch.active = False
        branch.settings = {**(branch.settings or {}), "deleted": True}
        audit(db, "branch.deleted", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {"success": True}

    @app.patch("/branches/{branch_id}")
    def update_branch(
        branch_id: str,
        payload: BranchUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("branch:manage")),
    ):
        branch = db.get(Branch, branch_id)
        if not branch or branch.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Branch not found")
        ensure_branch_access(user, branch_id)
        payload = payload.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] is not None:
            branch.name = payload["name"]
        if "code" in payload and payload["code"] is not None:
            branch.code = payload["code"] or branch.code
        if "address" in payload and payload["address"] is not None:
            branch.address = payload["address"]
        if "phone" in payload:
            branch.phone = payload["phone"]
        if "settings" in payload and payload["settings"] is not None:
            branch.settings = {**(branch.settings or {}), **payload["settings"]}
        if "status" in payload and payload["status"] is not None:
            branch.active = payload["status"] == "active"
        audit(db, "branch.updated", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {
            "id": branch.id,
            "name": branch.name,
            "code": branch.code,
            "address": branch.address,
            "phone": branch.phone,
            "active": branch.active,
            "status": "active" if branch.active else "inactive",
        }

    @app.post("/users", status_code=201)
    def create_user(
        payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))
    ):
        payload = payload.model_dump()
        ensure_can_manage_user(user, role=payload["role"])
        if payload.get("branch_id"):
            get_accessible_branch(db, user, payload["branch_id"])
        if db.scalar(select(User).where(User.email == payload["email"])):
            raise HTTPException(status_code=409, detail="Email already exists")
        validate_password_policy(db, user, payload["password"])
        new_user = User(
            tenant_id=user.tenant_id,
            branch_id=payload.get("branch_id"),
            name=payload["name"],
            email=payload["email"],
            password_hash=hash_password(payload["password"]),
            role=payload["role"],
            custom_permissions={"grants": sorted(set(payload["permissions"]))} if payload.get("permissions") else {},
        )
        db.add(new_user)
        db.flush()
        role = db.scalar(select(Role).where(Role.tenant_id == user.tenant_id, Role.name == new_user.role))
        if role:
            db.add(UserRole(tenant_id=user.tenant_id, branch_id=new_user.branch_id, user_id=new_user.id, role_id=role.id))
        audit(db, "user.created", "user", new_user.id, user=user, branch_id=new_user.branch_id)
        db.commit()
        return serialize_user(new_user)

    @app.get("/users")
    def list_users(
        branch_id: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("user:manage")),
    ):
        query = select(User)
        if user.role not in {"super_admin", "platform_admin"}:
            if user.role == "tenant_owner":
                query = query.where(User.tenant_id == user.tenant_id, ~User.role.in_({"super_admin", "platform_admin"}))
            else:
                query = query.where(User.tenant_id == user.tenant_id, ~User.role.in_(PROTECTED_USER_ROLES))
        if branch_id:
            get_accessible_branch(db, user, branch_id)
            query = query.where(User.branch_id == branch_id)
        rows = db.scalars(query.order_by(User.created_at.desc())).all()
        return {"items": [serialize_user(row) for row in rows]}

    @app.patch("/users/{user_id}")
    def update_user(
        user_id: str,
        payload: UserUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("user:manage")),
    ):
        target = db.get(User, user_id)
        if not target or (user.role not in {"super_admin", "platform_admin"} and target.tenant_id != user.tenant_id):
            raise HTTPException(status_code=404, detail="User not found")
        ensure_can_manage_user(user, target=target)
        payload = payload.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] is not None:
            target.name = payload["name"]
        if "phone" in payload:
            target.phone = payload["phone"]
        if "branch_id" in payload:
            branch_id = payload["branch_id"] or None
            if branch_id:
                get_accessible_branch(db, user, branch_id)
            target.branch_id = branch_id
        if "role" in payload and payload["role"] is not None and payload["role"] != target.role:
            ensure_can_manage_user(user, role=payload["role"])
            target.role = payload["role"]
            db.query(UserRole).filter(UserRole.user_id == target.id).delete(synchronize_session=False)
            role = db.scalar(select(Role).where(Role.tenant_id == target.tenant_id, Role.name == target.role))
            if role:
                db.add(UserRole(tenant_id=target.tenant_id, branch_id=target.branch_id, user_id=target.id, role_id=role.id))
        if "status" in payload and payload["status"] is not None:
            if target.id == user.id and payload["status"] == "inactive":
                raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
            target.active = payload["status"] == "active"
            if target.active:
                target.locked_until = None
                target.failed_login_attempts = 0
            else:
                revoke_user_sessions(db, target.id)
        if "permissions" in payload and payload["permissions"] is not None:
            target.custom_permissions = {"grants": sorted(set(payload["permissions"]))}
        if "locked" in payload and payload["locked"] is not None:
            if target.id == user.id and payload["locked"]:
                raise HTTPException(status_code=400, detail="You cannot lock your own account")
            if payload["locked"]:
                target.locked_until = naive_utcnow() + timedelta(days=36500)
                revoke_user_sessions(db, target.id)
            else:
                target.locked_until = None
                target.failed_login_attempts = 0
        audit(db, "user.updated", "user", target.id, user=user, branch_id=target.branch_id)
        db.commit()
        return serialize_user(target)

    @app.post("/users/{user_id}/reset-password")
    def reset_user_password(
        user_id: str,
        payload: dict,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("user:manage")),
    ):
        target = db.get(User, user_id)
        if not target or (user.role not in {"super_admin", "platform_admin"} and target.tenant_id != user.tenant_id):
            raise HTTPException(status_code=404, detail="User not found")
        ensure_can_manage_user(user, target=target)
        new_password = str(payload.get("new_password") or "")
        validate_password_policy(db, user, new_password)
        target.password_hash = hash_password(new_password)
        target.failed_login_attempts = 0
        target.locked_until = None
        revoke_user_sessions(db, target.id)
        invalidate_unused_password_reset_tokens(db, target.id, naive_utcnow())
        audit(db, "user.password_reset", "user", target.id, user=user, branch_id=target.branch_id)
        db.commit()
        return {"message": "Password reset successfully"}

    
    @app.get("/categories")
    def list_categories(
        branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
    ):
        get_accessible_branch(db, user, branch_id)
        categories = db.scalars(
            select(Category).where(Category.tenant_id == user.tenant_id, Category.branch_id == branch_id, Category.active == True)
        ).all()
        return {"items": [{"id": c.id, "name": c.name} for c in categories]}

    @app.post("/categories", status_code=201)
    def create_category(
        payload: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("menu:manage"))
    ):
        payload = payload.model_dump()
        get_accessible_branch(db, user, payload["branch_id"])
        category = Category(tenant_id=user.tenant_id, branch_id=payload["branch_id"], name=payload["name"])
        db.add(category)
        db.flush()
        audit(db, "category.created", "category", category.id, user=user, branch_id=category.branch_id)
        db.commit()
        return {"id": category.id, "name": category.name, "branch_id": category.branch_id}

    @app.post("/products", status_code=201)
    def create_product(
        payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("menu:manage"))
    ):
        payload = payload.model_dump()
        get_accessible_branch(db, user, payload["branch_id"])
        if payload.get("category_id"):
            category = db.get(Category, payload["category_id"])
            if not category or category.tenant_id != user.tenant_id or category.branch_id != payload["branch_id"]:
                raise HTTPException(status_code=400, detail="Invalid category")
        product = Product(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            category_id=payload.get("category_id"),
            name=payload["name"],
            description=payload.get("description"),
            sku=payload.get("sku"),
            price=money(payload["price"]),
            tax_rate=money(payload.get("tax_rate", 0)),
            variants=payload.get("variants") or [],
            addons=payload.get("addons") or [],
            combo_items=payload.get("combo_items") or [],
            image_url=payload.get("image_url"),
            available=payload.get("available", True),
        )
        db.add(product)
        db.flush()
        audit(db, "product.created", "product", product.id, user=user, branch_id=product.branch_id)
        db.commit()
        return {"id": product.id, "name": product.name, "price": f"{money(product.price):.2f}", "available": product.available}

    @app.get("/products")
    def list_products(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        get_accessible_branch(db, user, branch_id)
        rows = db.scalars(
            select(Product).where(
                Product.tenant_id == user.tenant_id,
                Product.branch_id == branch_id,
                Product.active.is_(True),
            )
        ).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "price": f"{money(row.price):.2f}",
                    "tax_rate": f"{money(row.tax_rate):.2f}",
                    "available": row.available,
                    "variants": row.variants,
                    "addons": row.addons,
                    "category_id": row.category_id,
                    "sku": row.sku,
                    "description": row.description,
                    "image_url": row.image_url,
                }
                for row in rows
            ]
        }

    @app.get("/products/{product_id}/recipe")
    def get_product_recipe(
        product_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("menu:manage")),
    ):
        product = db.get(Product, product_id)
        if not product or product.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Product not found")
        ensure_branch_access(user, product.branch_id)
        try:
            recipes = list_product_recipe(db, user.tenant_id, product_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [serialize_product_recipe(recipe) for recipe in recipes]}

    @app.put("/products/{product_id}/recipe")
    def update_product_recipe(
        product_id: str,
        payload: ProductRecipeUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("menu:manage")),
    ):
        payload = payload.model_dump()
        product = db.get(Product, product_id)
        if not product or product.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Product not found")
        ensure_branch_access(user, product.branch_id)
        try:
            recipes = replace_product_recipe(db, user.tenant_id, product_id, payload["items"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audit(db, "product.recipe_updated", "product", product.id, user=user, branch_id=product.branch_id)
        db.commit()
        return {"items": [serialize_product_recipe(recipe) for recipe in recipes]}

    @app.post("/tables", status_code=201)
    def create_table(
        payload: TableCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))
    ):
        payload = payload.model_dump()
        branch = get_accessible_branch(db, user, payload["branch_id"])
        floor_area = normalize_floor_name(payload.get("floor_area"))
        remember_branch_floor(branch, floor_area)
        table = RestaurantTable(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            name=payload["name"],
            capacity=payload.get("capacity", 2),
            status=payload.get("status", "available"),
            floor_area=floor_area,
        )
        db.add(table)
        db.flush()
        audit(db, "table.created", "table", table.id, user=user, branch_id=table.branch_id)
        db.commit()
        return {"id": table.id, "name": table.name, "capacity": table.capacity, "status": table.status, "floor_area": table.floor_area}

    @app.patch("/tables/{table_id}")
    def update_table(
        table_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))
    ):
        table = db.get(RestaurantTable, table_id)
        if not table or table.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        ensure_branch_access(user, table.branch_id)
        for key in ("name", "capacity", "status", "floor_area"):
            if key in payload:
                if key == "floor_area":
                    floor_area = normalize_floor_name(payload[key])
                    branch = get_accessible_branch(db, user, table.branch_id)
                    remember_branch_floor(branch, floor_area)
                    table.floor_area = floor_area
                else:
                    setattr(table, key, payload[key])
        audit(db, "table.updated", "table", table.id, user=user, branch_id=table.branch_id)
        db.commit()
        return {"id": table.id, "name": table.name, "capacity": table.capacity, "status": table.status, "floor_area": table.floor_area}

    @app.post("/tables/merge")
    def merge_tables(payload: TableMerge, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))):
        payload = payload.model_dump()
        t1 = db.get(RestaurantTable, payload["table_id_1"])
        t2 = db.get(RestaurantTable, payload["table_id_2"])
        if not t1 or not t2 or t1.tenant_id != user.tenant_id or t2.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="One or both tables not found")
        if t1.id == t2.id:
            raise HTTPException(status_code=400, detail="Select two different tables")
        ensure_branch_access(user, t1.branch_id)
        ensure_branch_access(user, t2.branch_id)
        if t1.branch_id != t2.branch_id:
            raise HTTPException(status_code=400, detail="Tables must belong to the same branch")
        if t1.merged_with or t2.merged_with:
            raise HTTPException(status_code=400, detail="Unmerge existing tables before merging again")
        if t1.order_id and t2.order_id:
            raise HTTPException(status_code=400, detail="Cannot merge two tables that both have active orders")
        if t2.order_id and not t1.order_id:
            t1.order_id = t2.order_id
            t2.order_id = None
        t2.merged_with = t1.id
        t2.status = "occupied"
        t1.status = "occupied"
        db.commit()
        return {"message": "Tables merged successfully", "table_1": t1.id, "table_2": t2.id}

    @app.post("/tables/split")
    def split_table(payload: TableSplit, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))):
        payload = payload.model_dump()
        t = db.get(RestaurantTable, payload["table_id"])
        if not t or t.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        ensure_branch_access(user, t.branch_id)
        merge_parent_id = t.merged_with or t.id
        merge_parent = db.get(RestaurantTable, merge_parent_id)
        merged = db.scalars(
            select(RestaurantTable).where(
                RestaurantTable.tenant_id == user.tenant_id,
                RestaurantTable.branch_id == t.branch_id,
                RestaurantTable.merged_with == merge_parent_id,
            )
        ).all()
        if not t.merged_with and not merged:
            raise HTTPException(status_code=400, detail="Table is not merged")
        for mt in merged:
            mt.merged_with = None
            mt.status = "available"
            mt.order_id = None
        if merge_parent:
            merge_parent.status = "available"
            merge_parent.order_id = None
        t.merged_with = None
        t.status = "available"
        t.order_id = None
        db.commit()
        return {"message": "Table unmerged successfully"}

    @app.post("/tables/transfer")
    def transfer_table_order(payload: TableTransfer, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))):
        payload = payload.model_dump()
        t_from = db.get(RestaurantTable, payload["from_table_id"])
        t_to = db.get(RestaurantTable, payload["to_table_id"])
        if not t_from or not t_to or t_from.tenant_id != user.tenant_id or t_to.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        ensure_branch_access(user, t_from.branch_id)
        ensure_branch_access(user, t_to.branch_id)
        
        # Transfer order reference
        if t_from.order_id:
            t_to.order_id = t_from.order_id
            t_to.status = "occupied"
            t_from.order_id = None
            t_from.status = "available"
        db.commit()
        return {"message": "Order transferred successfully"}

    @app.post("/tables/reserve")
    def reserve_table(payload: TableReserve, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))):
        payload = payload.model_dump()
        t = db.get(RestaurantTable, payload["table_id"])
        if not t or t.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        ensure_branch_access(user, t.branch_id)
        if t.status not in {"available", "reserved"}:
            raise HTTPException(status_code=400, detail="Only available tables can be reserved")
        if t.merged_with or t.order_id:
            raise HTTPException(status_code=400, detail="Merged or active-order tables cannot be reserved")
        t.status = "reserved"
        db.commit()
        return {"message": "Table reserved successfully", "id": t.id, "status": t.status}

    @app.delete("/tables/{table_id}")
    def delete_table(table_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("table:manage"))):
        table = db.get(RestaurantTable, table_id)
        if not table or table.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        ensure_branch_access(user, table.branch_id)
        if table.order_id or table.status == "occupied":
            raise HTTPException(status_code=400, detail="Clear active orders before deleting this table")
        if table.merged_with or db.scalar(select(RestaurantTable).where(RestaurantTable.merged_with == table.id)):
            raise HTTPException(status_code=400, detail="Unmerge this table before deleting it")
        db.delete(table)
        db.commit()
        return {"message": "Table deleted successfully"}

    @app.post("/employees", status_code=201)
    def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        payload = payload.model_dump()
        ensure_can_manage_user(user, role=payload["role"])
        get_accessible_branch(db, user, payload["branch_id"])
        
        u = db.scalar(select(User).where(User.tenant_id == user.tenant_id, User.email == payload["email"]))
        if not u and payload.get("password"):
            validate_password_policy(db, user, payload["password"])
            u = User(
                tenant_id=user.tenant_id,
                branch_id=payload["branch_id"],
                name=payload["name"],
                email=payload["email"],
                phone=payload.get("phone"),
                password_hash=hash_password(payload["password"]),
                role=payload["role"],
            )
            db.add(u)
            db.flush()
            role = db.scalar(select(Role).where(Role.tenant_id == user.tenant_id, Role.name == u.role))
            if role:
                db.add(UserRole(tenant_id=user.tenant_id, branch_id=u.branch_id, user_id=u.id, role_id=role.id))
        employee_code = payload.get("employee_id") or f"EMP-{secrets.token_hex(3).upper()}"
        if db.scalar(select(Employee).where(Employee.tenant_id == user.tenant_id, Employee.employee_id == employee_code)):
            raise HTTPException(status_code=409, detail="Employee ID already exists")
        
        emp = Employee(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            user_id=u.id if u else None,
            employee_id=employee_code,
            name=payload["name"],
            email=payload["email"],
            phone=payload.get("phone"),
            role=payload["role"],
        )
        db.add(emp)
        db.flush()
        
        # Initialize default payroll
        db.add(Payroll(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            employee_id=emp.id,
            salary_period=datetime.now(UTC).strftime("%Y-%m"),
            base_salary=money(payload["base_salary"]),
            net_salary=money(payload["base_salary"]),
        ))
        db.commit()
        return {"id": emp.id, "user_id": emp.user_id, "employee_id": emp.employee_id, "name": emp.name, "email": emp.email, "phone": emp.phone, "role": emp.role, "active": emp.active}

    @app.get("/employees")
    def list_employees(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        ensure_branch_access(user, branch_id)
        rows = db.scalars(select(Employee).where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id)).all()
        return {"items": [{"id": e.id, "user_id": e.user_id, "employee_id": e.employee_id, "name": e.name, "email": e.email, "role": e.role, "phone": e.phone, "joining_date": e.joining_date.strftime("%Y-%m-%d"), "active": e.active} for e in rows]}

    @app.post("/attendance/check-in")
    def check_in(payload: AttendanceAction, db: Session = Depends(get_db), user: User = Depends(current_user)):
        payload = payload.model_dump()
        emp = db.get(Employee, payload["employee_id"])
        if not emp or emp.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Check if already checked in
        existing = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.check_out.is_(None)))
        if existing:
            raise HTTPException(status_code=400, detail="Already checked in")
            
        att = Attendance(
            tenant_id=user.tenant_id,
            branch_id=emp.branch_id,
            employee_id=emp.id,
            shift_type=payload.get("shift_type", "General"),
        )
        db.add(att)
        db.commit()
        return {"id": att.id, "check_in": att.check_in.isoformat(), "shift_type": att.shift_type}

    @app.post("/attendance/check-out")
    def check_out(payload: AttendanceAction, db: Session = Depends(get_db), user: User = Depends(current_user)):
        payload = payload.model_dump()
        emp = db.get(Employee, payload["employee_id"])
        if not emp or emp.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        att = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.check_out.is_(None)))
        if not att:
            raise HTTPException(status_code=400, detail="Not checked in")
            
        att.check_out = naive_utcnow()
        duration_hours = (att.check_out - normalize_lock_time(att.check_in)).total_seconds() / 3600
        if duration_hours > 8:
            att.overtime_minutes = int((duration_hours - 8) * 60)
            
        db.commit()
        return {"id": att.id, "check_out": att.check_out.isoformat(), "overtime_minutes": att.overtime_minutes}

    @app.get("/reports/attendance")
    def get_attendance_report(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        ensure_branch_access(user, branch_id)
        rows = db.execute(
            select(Employee.name, Employee.employee_id, Attendance.id, Attendance.check_in, Attendance.check_out, Attendance.shift_type, Attendance.overtime_minutes, Attendance.overtime_status)
            .join(Attendance, Attendance.employee_id == Employee.id)
            .where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id)
            .order_by(Attendance.check_in.desc())
        ).all()
        return {
            "items": [
                {
                    "name": r[0],
                    "employee_id": r[1],
                    "id": r[2],
                    "check_in": r[3].isoformat(),
                    "check_out": r[4].isoformat() if r[4] else None,
                    "shift_type": r[5],
                    "overtime_minutes": r[6],
                    "overtime_status": r[7],
                }
                for r in rows
            ]
        }

    @app.get("/reports/attendance/current")
    def get_current_attendance(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        ensure_branch_access(user, branch_id)
        tz = business_timezone(db, user.tenant_id, branch_id)
        today = business_today(tz)
        employees = db.scalars(
            select(Employee)
            .where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id, Employee.active.is_(True))
            .order_by(Employee.name)
        ).all()
        attendance_rows = db.scalars(
            select(Attendance)
            .where(Attendance.tenant_id == user.tenant_id, Attendance.branch_id == branch_id)
            .order_by(Attendance.check_in.desc())
        ).all()
        latest_by_employee: dict[str, Attendance] = {}
        for row in attendance_rows:
            if row.employee_id in latest_by_employee:
                continue
            if local_date(row.check_in, tz) == today:
                latest_by_employee[row.employee_id] = row
        return {
            "items": [
                {
                    "id": employee.id,
                    "employee_id": employee.employee_id,
                    "name": employee.name,
                    "role": employee.role,
                    "attendance_id": latest_by_employee[employee.id].id if employee.id in latest_by_employee else None,
                    "check_in": latest_by_employee[employee.id].check_in.isoformat() if employee.id in latest_by_employee else None,
                    "check_out": latest_by_employee[employee.id].check_out.isoformat() if employee.id in latest_by_employee and latest_by_employee[employee.id].check_out else None,
                    "status": (
                        "not_started"
                        if employee.id not in latest_by_employee
                        else "clocked_out"
                        if latest_by_employee[employee.id].check_out
                        else "clocked_in"
                    ),
                }
                for employee in employees
            ]
        }

    @app.post("/leaves", status_code=201)
    def create_leave_request(payload: LeaveCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        get_accessible_branch(db, user, payload.branch_id)
        emp = db.get(Employee, payload.employee_id)
        if not emp or emp.tenant_id != user.tenant_id or emp.branch_id != payload.branch_id:
            raise HTTPException(status_code=404, detail="Employee not found")
        start_date = parse_iso_date(payload.start_date)
        end_date = parse_iso_date(payload.end_date)
        if end_date < start_date:
            raise HTTPException(status_code=400, detail="End date must be after start date")
        leave = LeaveRequest(
            tenant_id=user.tenant_id,
            branch_id=payload.branch_id,
            employee_id=emp.id,
            leave_type=payload.type,
            start_date=start_date,
            end_date=end_date,
            reason=payload.reason,
        )
        db.add(leave)
        db.flush()
        audit(db, "leave.created", "leave", leave.id, user=user, branch_id=payload.branch_id)
        db.commit()
        return serialize_leave_request(leave, emp)

    @app.get("/leaves")
    def list_leave_requests(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:view"))):
        ensure_branch_access(user, branch_id)
        rows = db.execute(
            select(LeaveRequest, Employee)
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .where(LeaveRequest.tenant_id == user.tenant_id, LeaveRequest.branch_id == branch_id)
            .order_by(LeaveRequest.created_at.desc())
        ).all()
        return {"items": [serialize_leave_request(leave, employee) for leave, employee in rows]}

    @app.patch("/leaves/{leave_id}")
    def update_leave_request(leave_id: str, payload: LeaveUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        leave = db.get(LeaveRequest, leave_id)
        if not leave or leave.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Leave request not found")
        ensure_branch_access(user, leave.branch_id)
        updates = payload.model_dump(exclude_unset=True)
        if "type" in updates:
            leave.leave_type = updates["type"]
        if "reason" in updates:
            leave.reason = updates["reason"] or ""
        if "status" in updates:
            leave.status = updates["status"]
        if "start_date" in updates:
            leave.start_date = parse_iso_date(updates["start_date"])
        if "end_date" in updates:
            leave.end_date = parse_iso_date(updates["end_date"])
        if leave.end_date < leave.start_date:
            raise HTTPException(status_code=400, detail="End date must be after start date")
        employee = db.get(Employee, leave.employee_id)
        audit(db, "leave.updated", "leave", leave.id, user=user, branch_id=leave.branch_id)
        db.commit()
        return serialize_leave_request(leave, employee)

    @app.get("/reports/payroll")
    def get_payroll_report(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        ensure_branch_access(user, branch_id)
        # Ensure current month payroll exists for all active employees
        tz = business_timezone(db, user.tenant_id, branch_id)
        current_period = local_date(naive_utcnow(), tz).strftime("%Y-%m")
        active_emps = db.scalars(
            select(Employee).where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id, Employee.active.is_(True))
        ).all()
        for emp in active_emps:
            exists = db.scalar(select(Payroll).where(Payroll.employee_id == emp.id, Payroll.salary_period == current_period))
            if not exists:
                last_payroll = db.scalar(select(Payroll).where(Payroll.employee_id == emp.id).order_by(Payroll.salary_period.desc()))
                base_sal = last_payroll.base_salary if last_payroll else 0
                db.add(Payroll(
                    tenant_id=user.tenant_id,
                    branch_id=branch_id,
                    employee_id=emp.id,
                    salary_period=current_period,
                    base_salary=money(base_sal),
                    net_salary=money(base_sal),
                    status="pending"
                ))
        db.commit()

        rows = db.execute(
            select(Employee, Payroll)
            .join(Payroll, Payroll.employee_id == Employee.id)
            .where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id)
            .order_by(Employee.name, Payroll.salary_period.desc())
        ).all()
        items = []
        for employee, payroll in rows:
            snapshot = payroll_snapshot(db, payroll, employee)
            items.append(
                {
                    "id": payroll.id,
                    "name": employee.name,
                    "employee_id": employee.employee_id,
                    "employee_record_id": employee.id,
                    "period": payroll.salary_period,
                    "day_salary": f"{snapshot['day_salary']:.2f}",
                    "base_salary": f"{snapshot['day_salary']:.2f}",
                    "net_salary": f"{snapshot['net_salary']:.2f}",
                    "incentives": f"{snapshot['incentives']:.2f}",
                    "present_days": snapshot["present_days"],
                    "approved_leave_days": snapshot["approved_leave_days"],
                    "payable_days": snapshot["payable_days"],
                    "absent_days": snapshot["absent_days"],
                    "status": payroll.status,
                    "payment_mode": payroll.payment_mode,
                    "payment_reference": payroll.payment_reference,
                    "payout_provider": payroll.payout_provider,
                    "payout_id": payroll.payout_id,
                    "payout_status": payroll.payout_status,
                }
            )
        db.commit()
        return {
            "items": items
        }

    @app.get("/reports/incentives")
    def get_incentives_report(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        ensure_branch_access(user, branch_id)
        rows = db.execute(
            select(Incentive.id, Employee.name, Employee.employee_id, Employee.id, Incentive.sales_amount, Incentive.incentive_amount, Incentive.incentive_date)
            .join(Incentive, Incentive.employee_id == Employee.id)
            .where(Employee.tenant_id == user.tenant_id, Employee.branch_id == branch_id)
        ).all()
        return {
            "items": [
                {
                    "id": r[0],
                    "name": r[1],
                    "employee_id": r[2],
                    "employee_record_id": r[3],
                    "sales_amount": f"{r[4]:.2f}",
                    "incentive_amount": f"{r[5]:.2f}",
                    "date": r[6].strftime("%Y-%m-%d"),
                }
                for r in rows
            ]
        }

    @app.get("/admin/available-permissions")
    def get_available_permissions(user: User = Depends(current_user)):
        return {"permissions": sorted(list(ADMIN_PERMISSION_CODES))}

    @app.get("/admin/permissions")
    def get_role_permissions(db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        tenant = db.get(Tenant, user.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {"role_permissions": tenant_role_permissions(tenant)}

    @app.patch("/admin/permissions")
    def update_role_permissions(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        tenant = db.get(Tenant, user.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        role_permissions = sanitize_role_permissions(payload)
        tenant.settings = {**(tenant.settings or {}), "role_permissions": role_permissions}
        audit(db, "permissions.updated", "tenant", tenant.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"role_permissions": role_permissions}

    @app.get("/admin/security-settings")
    def get_security_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
        sett = security_policy(db, user)
        db.commit()
        db.refresh(sett)
        return {
            "password_min_length": sett.password_min_length,
            "session_timeout_minutes": sett.session_timeout_minutes,
            "multi_device_login": sett.multi_device_login,
            "two_factor_auth": sett.two_factor_auth,
            "login_attempts_threshold": sett.login_attempts_threshold,
        }

    @app.patch("/admin/security-settings")
    def update_security_settings(payload: SecuritySettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("settings:manage"))):
        payload = payload.model_dump(exclude_unset=True)
        sett = db.scalar(select(SecuritySettings).where(SecuritySettings.tenant_id == user.tenant_id))
        if not sett:
            sett = SecuritySettings(tenant_id=user.tenant_id)
            db.add(sett)
            db.flush()
        for k, v in payload.items():
            if k == "password_min_length" and v is not None:
                v = max(8, min(int(v), 128))
            if k == "session_timeout_minutes" and v is not None:
                v = max(5, min(int(v), 1440))
            if k == "login_attempts_threshold" and v is not None:
                v = max(1, min(int(v), 20))
            setattr(sett, k, v)
        db.commit()
        db.refresh(sett)
        return {
            "password_min_length": sett.password_min_length,
            "session_timeout_minutes": sett.session_timeout_minutes,
            "multi_device_login": sett.multi_device_login,
            "two_factor_auth": sett.two_factor_auth,
            "login_attempts_threshold": sett.login_attempts_threshold,
        }

    @app.post("/admin/users/{user_id}/lock")
    def lock_user(user_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        target = db.get(User, user_id)
        if not target or (user.role not in {"super_admin", "platform_admin"} and target.tenant_id != user.tenant_id):
            raise HTTPException(status_code=404, detail="User not found")
        ensure_can_manage_user(user, target=target)
        if target.id == user.id:
            raise HTTPException(status_code=400, detail="You cannot lock your own account")
        target.locked_until = datetime.max
        revoke_user_sessions(db, target.id)
        db.commit()
        return {"message": "User account locked"}

    @app.post("/admin/users/{user_id}/unlock")
    def unlock_user(user_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        target = db.get(User, user_id)
        if not target or (user.role not in {"super_admin", "platform_admin"} and target.tenant_id != user.tenant_id):
            raise HTTPException(status_code=404, detail="User not found")
        ensure_can_manage_user(user, target=target)
        target.active = True
        target.locked_until = None
        target.failed_login_attempts = 0
        db.commit()
        return {"message": "User account unlocked"}

    @app.get("/inventory/items")
    def list_inventory_items(
        branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("inventory:view"))
    ):
        get_accessible_branch(db, user, branch_id)
        rows = db.scalars(
            select(InventoryItem).where(
                InventoryItem.tenant_id == user.tenant_id,
                InventoryItem.branch_id == branch_id,
                InventoryItem.active.is_(True),
            )
        ).all()
        return {
            "items": [
                {
                    "id": i.id,
                    "name": i.name,
                    "unit": i.unit,
                    "quantity": f"{i.quantity:.2f}",
                    "low_stock_threshold": f"{i.low_stock_threshold:.2f}",
                    "low_stock": i.quantity <= i.low_stock_threshold,
                }
                for i in rows
            ]
        }

    @app.get("/inventory/purchase-orders")
    def list_purchase_orders(
        branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("inventory:view"))
    ):
        get_accessible_branch(db, user, branch_id)
        rows = db.scalars(
            select(PurchaseOrder).where(PurchaseOrder.tenant_id == user.tenant_id, PurchaseOrder.branch_id == branch_id)
        ).all()
        return {
            "items": [
                {
                    "id": po.id,
                    "po_number": po.po_number,
                    "supplier_id": po.supplier_id,
                    "status": po.status,
                    "total_amount": f"{po.total_amount:.2f}",
                    "items": po.items,
                }
                for po in rows
            ]
        }

    @app.post("/inventory/items", status_code=201)
    def create_inventory_item(
        payload: InventoryItemCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("inventory:manage"))
    ):
        payload = payload.model_dump()
        get_accessible_branch(db, user, payload["branch_id"])
        supplier = create_supplier_if_needed(db, user.tenant_id, payload.get("supplier_name"))
        item = InventoryItem(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            supplier_id=supplier.id if supplier else None,
            name=payload["name"],
            unit=payload.get("unit", "unit"),
            quantity=money(payload.get("quantity", 0)),
            low_stock_threshold=money(payload.get("low_stock_threshold", 0)),
        )
        db.add(item)
        db.flush()
        audit(db, "inventory.created", "inventory_item", item.id, user=user, branch_id=item.branch_id)
        db.commit()
        return {
            "id": item.id,
            "name": item.name,
            "quantity": f"{money(item.quantity):.2f}",
            "low_stock": money(item.quantity) <= money(item.low_stock_threshold),
        }

    @app.post("/inventory/items/{item_id}/adjust")
    def adjust_inventory_item(
        item_id: str,
        payload: InventoryItemAdjust,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("inventory:manage")),
    ):
        payload = payload.model_dump()
        item = db.get(InventoryItem, item_id)
        if not item or item.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Inventory item not found")
        ensure_branch_access(user, item.branch_id)

        adjust_qty = money(payload["quantity"])
        new_qty = money(item.quantity) + adjust_qty
        if new_qty < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock (negative inventory blocked)")

        item.quantity = new_qty
        db.add(StockMovement(
            tenant_id=user.tenant_id,
            branch_id=item.branch_id,
            inventory_item_id=item.id,
            quantity=adjust_qty,
            movement_type="adjustment",
            notes=payload.get("notes"),
        ))
        audit(db, "inventory.adjusted", "inventory_item", item.id, user=user, branch_id=item.branch_id)
        db.commit()
        return {
            "id": item.id,
            "name": item.name,
            "quantity": f"{item.quantity:.2f}",
            "low_stock": item.quantity <= item.low_stock_threshold,
        }

    @app.post("/inventory/purchase-orders", status_code=201)
    def create_purchase_order(
        payload: PurchaseOrderCreate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("inventory:manage")),
    ):
        payload = payload.model_dump()
        get_accessible_branch(db, user, payload["branch_id"])

        supplier = create_supplier_if_needed(db, user.tenant_id, payload["supplier_name"])
        po_number = f"PO-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"

        total = Decimal("0.00")
        for item in payload.get("items", []):
            cost = money(item.get("cost_price") or item.get("unit_cost") or 0)
            qty = int(item.get("quantity", 0))
            total += cost * qty

        po = PurchaseOrder(
            tenant_id=user.tenant_id,
            branch_id=payload["branch_id"],
            supplier_id=supplier.id if supplier else None,
            po_number=po_number,
            items=payload["items"],
            total_amount=total,
            status="completed",
        )
        db.add(po)
        db.flush()

        for item in payload.get("items", []):
            inv_item = db.scalar(
                select(InventoryItem).where(
                    InventoryItem.tenant_id == user.tenant_id,
                    InventoryItem.branch_id == payload["branch_id"],
                    InventoryItem.name == item["name"],
                    InventoryItem.active.is_(True),
                )
            )
            if not inv_item:
                inv_item = InventoryItem(
                    tenant_id=user.tenant_id,
                    branch_id=payload["branch_id"],
                    supplier_id=supplier.id if supplier else None,
                    name=item["name"],
                    unit=item.get("unit", "unit"),
                    quantity=0,
                    low_stock_threshold=0,
                )
                db.add(inv_item)
                db.flush()

            inv_item.quantity += Decimal(str(item["quantity"]))
            db.add(StockMovement(
                tenant_id=user.tenant_id,
                branch_id=payload["branch_id"],
                inventory_item_id=inv_item.id,
                quantity=Decimal(str(item["quantity"])),
                movement_type="purchase",
                notes=f"Purchased via {po_number}",
            ))

        audit(db, "purchase_order.created", "purchase_order", po.id, user=user, branch_id=po.branch_id)
        db.commit()
        return {
            "id": po.id,
            "po_number": po.po_number,
            "status": po.status,
            "total_amount": f"{po.total_amount:.2f}",
        }

    @app.get("/online-delivery/orders")
    def list_online_delivery_orders(
        branch_id: str,
        status_filter: str | None = None,
        provider: str | None = None,
        limit: int = 100,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        get_accessible_branch(db, user, branch_id)
        safe_limit = max(1, min(limit, 200))
        query = select(OnlineDeliveryOrder).where(
            OnlineDeliveryOrder.tenant_id == user.tenant_id,
            OnlineDeliveryOrder.branch_id == branch_id,
        )
        if status_filter:
            query = query.where(OnlineDeliveryOrder.status == status_filter)
        if provider:
            query = query.where(OnlineDeliveryOrder.provider == provider)
        rows = db.scalars(query.order_by(OnlineDeliveryOrder.created_at.desc()).limit(safe_limit)).all()
        return {"items": [serialize_online_delivery(row) for row in rows]}

    @app.post("/online-delivery/orders", status_code=201)
    def create_online_delivery_order(
        payload: OnlineDeliveryOrderCreate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("order:manage")),
    ):
        data = payload.model_dump()
        get_accessible_branch(db, user, data["branch_id"])
        existing = db.scalar(select(OnlineDeliveryOrder).where(
            OnlineDeliveryOrder.tenant_id == user.tenant_id,
            OnlineDeliveryOrder.provider == data["provider"],
            OnlineDeliveryOrder.external_order_id == data["external_order_id"],
        ))
        if existing:
            raise HTTPException(status_code=409, detail="Delivery order already exists")
        items, subtotal, total = online_delivery_items_with_totals(db, user.tenant_id, data["branch_id"], data["items"])
        record = OnlineDeliveryOrder(
            tenant_id=user.tenant_id,
            branch_id=data["branch_id"],
            provider=data["provider"],
            external_order_id=data["external_order_id"],
            customer_name=data["customer_name"],
            customer_phone=data["customer_phone"],
            delivery_address=data["delivery_address"],
            rider_name=data["rider_name"],
            rider_phone=data["rider_phone"],
            payment_mode=data["payment_mode"],
            payment_status=data["payment_status"],
            subtotal=subtotal,
            total=total,
            commission_amount=money(data["commission_amount"]),
            items=items,
            notes=data["notes"],
            raw_payload=data["raw_payload"],
        )
        db.add(record)
        audit(db, "online_delivery.created", "online_delivery_order", record.id, user=user, branch_id=record.branch_id)
        db.commit()
        db.refresh(record)
        return serialize_online_delivery(record)

    @app.post("/integrations/{provider}/online-delivery/webhook", status_code=201)
    async def receive_online_delivery_webhook(
        provider: str,
        request: Request,
        branch_id: str,
        db: Session = Depends(get_db),
    ):
        provider = provider.lower()
        if provider not in {"swiggy", "zomato"}:
            raise HTTPException(status_code=404, detail="Unsupported delivery provider")
        branch = db.get(Branch, branch_id)
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")
        body = await request.body()
        headers = {key.lower(): value for key, value in request.headers.items()}
        if not (os.getenv(f"{provider.upper()}_WEBHOOK_SECRET") or "").strip():
            raise HTTPException(status_code=503, detail=f"{provider.title()} webhook is not configured")
        if not delivery_webhook_secret_valid(provider, body, headers):
            raise HTTPException(status_code=401, detail="Invalid delivery webhook signature")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
        normalized = normalize_delivery_webhook_payload(db, branch.tenant_id, branch.id, provider, payload)
        if not normalized["external_order_id"]:
            raise HTTPException(status_code=422, detail="Webhook missing provider order id")

        existing = db.scalar(select(OnlineDeliveryOrder).where(
            OnlineDeliveryOrder.tenant_id == branch.tenant_id,
            OnlineDeliveryOrder.provider == provider,
            OnlineDeliveryOrder.external_order_id == normalized["external_order_id"],
        ))
        if existing:
            if normalized["has_status"] and normalized["known_status"] and should_apply_delivery_webhook_status(existing.status, normalized["status"]):
                existing.status = normalized["status"]
            if normalized["has_customer_name"]:
                existing.customer_name = normalized["customer_name"]
            if normalized["has_customer_phone"]:
                existing.customer_phone = normalized["customer_phone"]
            if normalized["has_delivery_address"]:
                existing.delivery_address = normalized["delivery_address"]
            if normalized["has_rider_name"]:
                existing.rider_name = normalized["rider_name"]
            if normalized["has_rider_phone"]:
                existing.rider_phone = normalized["rider_phone"]
            if normalized["has_payment_mode"]:
                existing.payment_mode = normalized["payment_mode"]
            if normalized["has_payment_status"]:
                existing.payment_status = normalized["payment_status"]
            if normalized["has_subtotal"] or normalized["has_items"]:
                existing.subtotal = normalized["subtotal"]
            if normalized["has_total"] or normalized["has_items"]:
                existing.total = normalized["total"]
            if normalized["has_commission_amount"]:
                existing.commission_amount = normalized["commission_amount"]
            if normalized["has_items"]:
                existing.items = normalized["items"]
            if normalized["has_notes"]:
                existing.notes = normalized["notes"]
            existing.raw_payload = normalized["raw_payload"]
            record = existing
        else:
            record = OnlineDeliveryOrder(
                tenant_id=branch.tenant_id,
                branch_id=branch.id,
                provider=provider,
                external_order_id=normalized["external_order_id"],
                status=normalized["status"],
                customer_name=normalized["customer_name"],
                customer_phone=normalized["customer_phone"],
                delivery_address=normalized["delivery_address"],
                rider_name=normalized["rider_name"],
                rider_phone=normalized["rider_phone"],
                payment_mode=normalized["payment_mode"],
                payment_status=normalized["payment_status"],
                subtotal=normalized["subtotal"],
                total=normalized["total"],
                commission_amount=normalized["commission_amount"],
                items=normalized["items"],
                notes=normalized["notes"],
                raw_payload=normalized["raw_payload"],
            )
            db.add(record)
        sync_delivery_status_to_order(db, record)
        db.commit()
        db.refresh(record)
        serialized = serialize_online_delivery(record)
        return {
            "code": 200,
            "status": "success",
            "message": "Order received successfully",
            "external_order_id": record.id,
            "rejection_message_id": 0,
            "data": serialized,
        }

    @app.post("/integrations/razorpay/webhook")
    @app.post("/integrations/razorpayx/webhook")
    async def receive_razorpay_webhook(request: Request, db: Session = Depends(get_db)):
        body = await request.body()
        is_razorpayx_webhook = request.url.path.rstrip("/").endswith("/integrations/razorpayx/webhook")
        webhook_secret_name = "RAZORPAYX_WEBHOOK_SECRET" if is_razorpayx_webhook else "RAZORPAY_WEBHOOK_SECRET"
        verify_razorpay_webhook_signature(body, request.headers.get("x-razorpay-signature"), webhook_secret_name)
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid Razorpay webhook payload") from exc

        event = str(payload.get("event") or "")
        if is_razorpayx_webhook and not event.startswith("payout."):
            raise HTTPException(status_code=422, detail="RazorpayX webhook only accepts payout events")
        if not is_razorpayx_webhook and event.startswith("payout."):
            raise HTTPException(status_code=422, detail="Razorpay payment webhook does not accept payout events")
        payment_entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
        payout_entity = (((payload.get("payload") or {}).get("payout") or {}).get("entity") or {})
        refund_entity = (((payload.get("payload") or {}).get("refund") or {}).get("entity") or {})

        if event == "payment.captured" and payment_entity:
            gateway_order_id = payment_entity.get("order_id")
            gateway_payment_id = payment_entity.get("id")
            if not gateway_order_id or not gateway_payment_id:
                raise HTTPException(status_code=422, detail="Razorpay payment webhook missing order or payment id")
            payment = db.scalar(
                select(Payment).where(
                    Payment.provider == "razorpay",
                    Payment.gateway_order_id == gateway_order_id,
                )
            )
            if not payment:
                raise HTTPException(status_code=404, detail="Gateway payment not found")
            validate_razorpay_payment_amount(payment, payment_entity)
            order = capture_gateway_payment_record(db, payment, str(gateway_payment_id), request.headers.get("x-razorpay-signature"))
            audit(db, "payment.webhook_captured", "order", order.id, tenant_id=order.tenant_id, branch_id=order.branch_id)
            db.commit()
            return {"success": True, "event": event, "order_id": order.id}

        if event == "payment.failed" and payment_entity:
            gateway_order_id = payment_entity.get("order_id")
            gateway_payment_id = payment_entity.get("id")
            if not gateway_order_id:
                raise HTTPException(status_code=422, detail="Razorpay payment webhook missing order id")
            payment = db.scalar(
                select(Payment).where(
                    Payment.provider == "razorpay",
                    Payment.gateway_order_id == gateway_order_id,
                )
            )
            if not payment:
                raise HTTPException(status_code=404, detail="Gateway payment not found")
            if payment.status in {"pending", "created"}:
                payment.status = "failed"
                payment.gateway_payment_id = str(gateway_payment_id) if gateway_payment_id else payment.gateway_payment_id
                payment.reference = payment_entity.get("error_description") or payment_entity.get("error_reason") or payment.reference
                order = db.get(Order, payment.order_id)
                audit(db, "payment.webhook_failed", "order", payment.order_id, tenant_id=order.tenant_id if order else None, branch_id=order.branch_id if order else None)
                db.commit()
            return {"success": True, "event": event}

        if event.startswith("refund."):
            gateway_refund_id = str(refund_entity.get("id") or "").strip()
            if not gateway_refund_id:
                raise HTTPException(status_code=422, detail="Razorpay refund webhook missing refund id")
            refund = db.scalar(select(Refund).where(Refund.gateway_refund_id == gateway_refund_id))
            if not refund:
                raise HTTPException(status_code=404, detail="Refund record not found")
            payment = db.get(Payment, refund.payment_id)
            order = db.get(Order, refund.order_id)
            if not payment or not order:
                raise HTTPException(status_code=404, detail="Refund payment or order not found")
            validate_razorpay_refund_entity(refund, payment, refund_entity)
            provider_status = str(refund_entity.get("status") or "").strip().lower()
            if event == "refund.processed":
                provider_status = "processed"
            elif event == "refund.failed":
                provider_status = "failed"
            elif event == "refund.created" and not provider_status:
                provider_status = "pending"
            if provider_status:
                refund.status = provider_status
            refresh_order_refund_status(db, order)
            audit(
                db,
                "refund.webhook_updated",
                "refund",
                refund.id,
                tenant_id=refund.tenant_id,
                branch_id=refund.branch_id,
                metadata={"event": event, "status": refund.status},
            )
            db.commit()
            return {"success": True, "event": event, "refund_id": refund.id, "order_id": order.id}

        if event.startswith("payout.") and payout_entity:
            payout_id = payout_entity.get("id")
            if not payout_id:
                raise HTTPException(status_code=422, detail="Razorpay payout webhook missing payout id")
            payroll = db.scalar(select(Payroll).where(Payroll.payout_id == str(payout_id)))
            if not payroll:
                raise HTTPException(status_code=404, detail="Payout record not found")
            validate_razorpay_payout_amount(payroll, payout_entity)
            payout_status = str(payout_entity.get("status") or event.removeprefix("payout.")).lower()
            payroll.payout_status = payout_status
            if payout_status in {"failed", "reversed", "rejected", "cancelled", "canceled"}:
                payroll.status = "pending"
                failure_reason = (
                    payout_entity.get("failure_reason")
                    or payout_entity.get("error_description")
                    or payout_entity.get("status_details")
                )
                if failure_reason:
                    payroll.payment_reference = str(failure_reason)
            elif payout_status in {"processed", "completed", "settled"}:
                payroll.status = "paid"
            if payout_entity.get("utr"):
                payroll.payment_reference = payout_entity.get("utr")
            audit(db, "payout.webhook_updated", "payroll", payroll.id, tenant_id=payroll.tenant_id, branch_id=payroll.branch_id)
            db.commit()
            return {"success": True, "event": event, "payroll_id": payroll.id}

        return {"success": True, "event": event or "ignored", "ignored": True}

    @app.post("/online-delivery/orders/{delivery_id}/accept")
    def accept_online_delivery_order(
        delivery_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("order:manage")),
    ):
        record = db.get(OnlineDeliveryOrder, delivery_id)
        if not record or record.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Delivery order not found")
        ensure_branch_access(user, record.branch_id)
        if record.status not in {"new", "accepted"}:
            raise HTTPException(status_code=409, detail="Delivery order cannot be accepted")
        if any(item.get("unmapped") or not item.get("product_id") for item in (record.items or [])):
            raise HTTPException(status_code=422, detail="Map all provider items to menu SKUs before accepting")
        if record.order_id:
            linked_order = db.get(Order, record.order_id)
            return {"delivery_order": serialize_online_delivery(record), "order": serialize_order(linked_order) if linked_order else None}

        try:
            order = build_order(db, user.tenant_id, {
                "branch_id": record.branch_id,
                "table_id": None,
                "customer": {"name": record.customer_name, "phone": record.customer_phone},
                "order_type": "delivery",
                "discount_amount": "0.00",
                "items": [{"product_id": item["product_id"], "quantity": item["quantity"], "notes": item.get("notes")} for item in (record.items or [])],
            })
            fulfill_order_inventory(db, order)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        order.status = "active"
        order.kds_status = "new"
        record.status = "accepted"
        record.order_id = order.id
        if record.payment_status == "paid":
            db.add(Payment(
                order_id=order.id,
                method=record.provider,
                amount=order.total,
                reference=record.external_order_id,
                status="captured",
                provider=record.provider,
            ))
            order.payment_status = "paid"
        notify_online_delivery_provider(record, "accepted")
        audit(db, "online_delivery.accepted", "online_delivery_order", record.id, user=user, branch_id=record.branch_id)
        audit(db, "order.sent_to_kitchen", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        db.refresh(record)
        db.refresh(order)
        return {"delivery_order": serialize_online_delivery(record), "order": serialize_order(order)}

    @app.patch("/online-delivery/orders/{delivery_id}")
    def update_online_delivery_status(
        delivery_id: str,
        payload: OnlineDeliveryStatusUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("order:manage")),
    ):
        record = db.get(OnlineDeliveryOrder, delivery_id)
        if not record or record.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Delivery order not found")
        ensure_branch_access(user, record.branch_id)
        data = payload.model_dump()
        provider_action = {
            "ready": "ready",
            "rejected": "rejected",
            "cancelled": "rejected",
            "picked_up": "picked_up",
            "delivered": "delivered",
        }.get(data["status"])
        if provider_action:
            notify_online_delivery_provider(record, provider_action)
        record.status = data["status"]
        sync_delivery_status_to_order(db, record)
        audit(db, "online_delivery.status_updated", "online_delivery_order", record.id, user=user, branch_id=record.branch_id)
        db.commit()
        db.refresh(record)
        return serialize_online_delivery(record)

    @app.get("/qr/menu")
    def qr_menu(branch_id: str, table_id: str, db: Session = Depends(get_db)):
        branch = db.get(Branch, branch_id)
        table = db.get(RestaurantTable, table_id)
        if not branch or is_branch_deleted(branch) or not branch.active:
            raise HTTPException(status_code=404, detail="Branch not found")
        if not table or table.branch_id != branch.id or table.tenant_id != branch.tenant_id:
            raise HTTPException(status_code=404, detail="Table not found")
        categories = db.scalars(
            select(Category).where(Category.tenant_id == branch.tenant_id, Category.branch_id == branch.id, Category.active.is_(True)).order_by(Category.name)
        ).all()
        products = db.scalars(
            select(Product).where(
                Product.tenant_id == branch.tenant_id,
                Product.branch_id == branch.id,
                Product.active.is_(True),
                Product.available.is_(True),
            ).order_by(Product.name)
        ).all()
        return {
            "branch": {"id": branch.id, "name": branch.name, "address": branch.address, "phone": branch.phone},
            "table": {"id": table.id, "name": table.name, "status": table.status, "floor_area": table.floor_area},
            "categories": [{"id": row.id, "name": row.name} for row in categories],
            "products": [
                {
                    "id": row.id,
                    "category_id": row.category_id,
                    "name": row.name,
                    "description": row.description,
                    "price": f"{money(row.price):.2f}",
                    "tax_rate": f"{money(row.tax_rate):.2f}",
                    "image_url": row.image_url,
                    "variants": row.variants or [],
                    "addons": row.addons or [],
                }
                for row in products
            ],
        }

    @app.post("/qr/orders", status_code=201)
    def create_qr_order(payload: QrOrderCreate, db: Session = Depends(get_db)):
        data = payload.model_dump()
        branch = db.get(Branch, data["branch_id"])
        table = db.get(RestaurantTable, data["table_id"])
        if not branch or is_branch_deleted(branch) or not branch.active:
            raise HTTPException(status_code=404, detail="Branch not found")
        if not table or table.tenant_id != branch.tenant_id or table.branch_id != branch.id:
            raise HTTPException(status_code=404, detail="Table not found")
        trusted_items = []
        for item in data["items"]:
            product = db.get(Product, item["product_id"])
            if (
                not product
                or product.tenant_id != branch.tenant_id
                or product.branch_id != branch.id
                or not product.active
                or not product.available
            ):
                raise HTTPException(status_code=400, detail="Menu item is not available")

            variant_name = item.get("variant_name")
            if variant_name and not any(variant.get("name") == variant_name for variant in product.variants or []):
                raise HTTPException(status_code=400, detail="Menu item variant is not available")

            available_addons = {
                addon.get("name"): addon
                for addon in product.addons or []
                if addon.get("name")
            }
            selected_addons = []
            selected_names = set()
            for selection in item.get("addons") or []:
                addon_name = selection["name"]
                addon = available_addons.get(addon_name)
                if not addon or addon_name in selected_names:
                    raise HTTPException(status_code=400, detail="Menu item add-on is not available")
                selected_names.add(addon_name)
                selected_addons.append({"name": addon_name, "price": f"{money(addon.get('price', 0)):.2f}"})

            trusted_items.append({
                "product_id": product.id,
                "quantity": item["quantity"],
                "variant_name": variant_name,
                "addons": selected_addons,
                "notes": item.get("notes"),
            })
        try:
            order = build_order(db, branch.tenant_id, {
                "branch_id": branch.id,
                "table_id": table.id,
                "customer": {"name": data["customer_name"], "phone": data["customer_phone"]},
                "order_type": "dine_in",
                "discount_amount": "0.00",
                "items": trusted_items,
            })
            fulfill_order_inventory(db, order)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        order.status = "active"
        order.kds_status = "new"
        table.status = "occupied"
        table.order_id = order.id
        audit(db, "qr.order_created", "order", order.id, branch_id=branch.id, tenant_id=branch.tenant_id)
        db.commit()
        db.refresh(order)
        return serialize_order(order)

    @app.post("/qr/orders/{order_id}/payments/gateway", status_code=201)
    def create_qr_gateway_payment(order_id: str, db: Session = Depends(get_db)):
        order = db.get(Order, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        due_amount = money(order.total) - captured_payment_total(order)
        if due_amount <= 0:
            raise HTTPException(status_code=400, detail="Order is already paid")
        key_id, _ = razorpay_credentials("RAZORPAY")
        existing_payment = reusable_gateway_payment(db, order, due_amount)
        if existing_payment:
            return gateway_payment_response(order, existing_payment, key_id, money(existing_payment.amount), reused=True)
        gateway_order = razorpay_request(
            "POST",
            "/orders",
            {
                "amount": amount_to_paise(due_amount),
                "currency": "INR",
                "receipt": order.id,
                "notes": {"order_id": order.id, "source": "qr_order"},
            },
            "RAZORPAY",
        )
        pending_payment = Payment(
            order_id=order.id,
            method="razorpay",
            amount=due_amount,
            reference=gateway_order["id"],
            status="pending",
            provider="razorpay",
            gateway_order_id=gateway_order["id"],
        )
        db.add(pending_payment)
        audit(db, "qr.payment.gateway_created", "order", order.id, branch_id=order.branch_id, tenant_id=order.tenant_id)
        db.commit()
        return gateway_payment_response(order, pending_payment, key_id, due_amount, gateway_order.get("currency", "INR"))

    @app.post("/qr/orders/{order_id}/payments/gateway/verify")
    def verify_qr_gateway_payment(order_id: str, payload: PaymentGatewayVerify, db: Session = Depends(get_db)):
        order = db.get(Order, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        data = payload.model_dump()
        payment = db.scalar(
            select(Payment).where(
                Payment.order_id == order.id,
                Payment.provider == "razorpay",
                Payment.gateway_order_id == data["gateway_order_id"],
            )
        )
        if not payment:
            raise HTTPException(status_code=404, detail="Gateway payment not found")
        verify_razorpay_signature(str(payment.gateway_order_id), data["gateway_payment_id"], data["gateway_signature"])
        if payment.status == "captured" and payment.gateway_payment_id == data["gateway_payment_id"]:
            order = capture_gateway_payment_record(db, payment, data["gateway_payment_id"], data["gateway_signature"])
            return serialize_order(order)
        if payment.status not in {"pending", "created"}:
            raise HTTPException(status_code=409, detail="Gateway payment is not pending")
        confirm_razorpay_payment_capture(payment, data["gateway_payment_id"])
        order = capture_gateway_payment_record(db, payment, data["gateway_payment_id"], data["gateway_signature"])
        audit(db, "qr.payment.gateway_captured", "order", order.id, branch_id=order.branch_id, tenant_id=order.tenant_id)
        db.commit()
        db.refresh(order)
        return serialize_order(order)

    @app.get("/orders")
    def list_orders(
        branch_id: str,
        limit: int = 100,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        get_accessible_branch(db, user, branch_id)
        safe_limit = max(1, min(limit, 200))
        rows = db.scalars(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payments))
            .where(Order.tenant_id == user.tenant_id, Order.branch_id == branch_id)
            .order_by(Order.created_at.desc())
            .limit(safe_limit)
        ).all()
        return {"items": [serialize_order(order) for order in rows]}

    @app.post("/orders", status_code=201)
    def create_order(
        payload: OrderCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("order:manage"))
    ):
        payload = payload.model_dump()
        get_accessible_branch(db, user, payload["branch_id"])
        try:
            order = build_order(db, user.tenant_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if order.table_id:
            table = db.get(RestaurantTable, order.table_id)
            if not table or table.tenant_id != user.tenant_id or table.branch_id != order.branch_id:
                raise HTTPException(status_code=400, detail="Invalid table")
            table.status = "occupied"
            table.order_id = order.id
        audit(db, "order.created", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        db.refresh(order)
        return serialize_order(order)

    @app.patch("/orders/{order_id}")
    def update_order(
        order_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("order:manage"))
    ):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        if "status" in payload:
            previous_status = order.status
            order.status = payload["status"]
            if payload["status"] in {"completed", "void", "cancelled"}:
                if payload["status"] in {"void", "cancelled"} and previous_status != payload["status"]:
                    reverse_order_inventory(db, order, payload["status"])
                # Free the table
                table = db.scalar(select(RestaurantTable).where(RestaurantTable.order_id == order.id))
                if table:
                    table.status = "available"
                    table.order_id = None
        audit(db, "order.updated", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        return serialize_order(order)

    @app.post("/orders/{order_id}/send-to-kitchen")
    def send_to_kitchen(
        order_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("order:manage"))
    ):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        try:
            fulfill_order_inventory(db, order)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        order.status = "active"
        order.kds_status = "new"
        audit(db, "order.sent_to_kitchen", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        return serialize_order(order)

    @app.patch("/kds/orders/{order_id}")
    def update_kds(
        order_id: str, payload: KdsUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("kds:manage"))
    ):
        payload = payload.model_dump()
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        order.kds_status = payload["kds_status"]
        if order.kds_status == "ready":
            delivery_record = db.scalar(select(OnlineDeliveryOrder).where(OnlineDeliveryOrder.order_id == order.id))
            if delivery_record:
                notify_online_delivery_provider(delivery_record, "ready")
                delivery_record.status = "ready"
        audit(db, "kds.updated", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        return serialize_order(order)

    @app.get("/kds/orders")
    def list_kds_orders(
        branch_id: str,
        limit: int = 100,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("kds:view")),
    ):
        get_accessible_branch(db, user, branch_id)
        safe_limit = max(1, min(limit, 200))
        kds_statuses = {"new", "accepted", "preparing", "ready", "served"}
        rows = db.scalars(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payments))
            .where(
                Order.tenant_id == user.tenant_id,
                Order.branch_id == branch_id,
                Order.kds_status.in_(kds_statuses),
            )
            .order_by(Order.created_at.desc())
            .limit(safe_limit)
        ).all()
        return {"items": [serialize_order(order) for order in rows]}

    @app.post("/orders/{order_id}/payments", status_code=201)
    def pay_order(
        order_id: str, payload: PaymentsCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("payment:manage"))
    ):
        payload = payload.model_dump()
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        try:
            apply_payments(db, order, payload.get("payments", []))
            if order.status == "completed":
                fulfill_order_inventory(db, order)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if order.status == "completed":
            table = db.scalar(select(RestaurantTable).where(RestaurantTable.order_id == order.id))
            if table:
                table.status = "available"
                table.order_id = None
        audit(db, "order.paid", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        return serialize_order(order)

    @app.post("/orders/{order_id}/payments/gateway", status_code=201)
    def create_order_gateway_payment(
        order_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("payment:manage")),
    ):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        due_amount = money(order.total) - captured_payment_total(order)
        if due_amount <= 0:
            raise HTTPException(status_code=400, detail="Order is already paid")
        key_id, _ = razorpay_credentials("RAZORPAY")
        existing_payment = reusable_gateway_payment(db, order, due_amount)
        if existing_payment:
            return gateway_payment_response(order, existing_payment, key_id, money(existing_payment.amount), reused=True)
        gateway_order = razorpay_request(
            "POST",
            "/orders",
            {
                "amount": amount_to_paise(due_amount),
                "currency": "INR",
                "receipt": f"order_{order.id[:32]}",
                "notes": {"order_id": order.id, "tenant_id": order.tenant_id, "branch_id": order.branch_id},
            },
        )
        pending_payment = Payment(
            order_id=order.id,
            method="razorpay",
            amount=due_amount,
            reference=gateway_order["id"],
            status="created",
            provider="razorpay",
            gateway_order_id=gateway_order["id"],
        )
        db.add(pending_payment)
        audit(db, "payment.gateway_created", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        return gateway_payment_response(order, pending_payment, key_id, due_amount)

    @app.post("/orders/{order_id}/payments/gateway/verify")
    def verify_order_gateway_payment(
        order_id: str,
        payload: PaymentGatewayVerify,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("payment:manage")),
    ):
        payload = payload.model_dump()
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        payment = db.scalar(
            select(Payment).where(
                Payment.order_id == order.id,
                Payment.provider == "razorpay",
                Payment.gateway_order_id == payload["gateway_order_id"],
            )
        )
        if not payment:
            raise HTTPException(status_code=404, detail="Gateway payment not found")
        verify_razorpay_signature(str(payment.gateway_order_id), payload["gateway_payment_id"], payload["gateway_signature"])
        if payment.status == "captured" and payment.gateway_payment_id == payload["gateway_payment_id"]:
            order = capture_gateway_payment_record(db, payment, payload["gateway_payment_id"], payload["gateway_signature"])
            return serialize_order(order)
        if payment.status not in {"pending", "created"}:
            raise HTTPException(status_code=409, detail="Gateway payment is not pending")
        confirm_razorpay_payment_capture(payment, payload["gateway_payment_id"])
        order = capture_gateway_payment_record(db, payment, payload["gateway_payment_id"], payload["gateway_signature"])
        audit(db, "payment.gateway_captured", "order", order.id, user=user, branch_id=order.branch_id)
        db.commit()
        db.refresh(order)
        return serialize_order(order)

    @app.post("/orders/{order_id}/refunds", status_code=201)
    def refund_order(
        order_id: str,
        payload: RefundCreate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("refund:manage")),
    ):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        data = payload.model_dump()
        payment_query = select(Payment).where(
            Payment.order_id == order.id,
            func.lower(func.trim(Payment.status)).in_(CAPTURED_PAYMENT_STATUSES),
        )
        if data["payment_id"]:
            payment_query = payment_query.where(Payment.id == data["payment_id"])
        payments = db.scalars(payment_query.with_for_update()).all()
        if not payments:
            raise HTTPException(status_code=404, detail="Captured payment not found")
        if len(payments) != 1:
            raise HTTPException(status_code=422, detail="payment_id is required when an order has multiple captured payments")
        payment = payments[0]

        active_refund = db.scalar(
            select(Refund)
            .where(Refund.payment_id == payment.id, Refund.status.in_(REFUND_ACTIVE_STATUSES))
            .order_by(Refund.created_at.desc())
        )
        if active_refund:
            refresh_order_refund_status(db, order)
            return {"refund": serialize_refund(active_refund), "order": serialize_order(order), "reused": True}

        prior_refunds = db.scalars(
            select(Refund).where(
                Refund.payment_id == payment.id,
                Refund.status.in_(REFUND_PROCESSED_STATUSES),
            )
        ).all()
        previously_refunded = sum((money(refund.amount) for refund in prior_refunds), Decimal("0.00"))
        refundable_amount = money(payment.amount) - previously_refunded
        refund_amount = money(data["amount"]) if data["amount"] is not None else refundable_amount
        if refundable_amount <= 0:
            raise HTTPException(status_code=409, detail="Payment is already fully refunded")
        if refund_amount <= 0 or refund_amount > refundable_amount:
            raise HTTPException(status_code=422, detail="Refund amount exceeds the refundable payment amount")

        latest_failed_refund = db.scalar(
            select(Refund)
            .where(Refund.payment_id == payment.id, Refund.status.in_(REFUND_FAILED_STATUSES))
            .order_by(Refund.created_at.desc())
        )
        retry_source = (
            str(latest_failed_refund.gateway_refund_id or latest_failed_refund.id)
            if latest_failed_refund
            else None
        )
        receipt = razorpay_refund_receipt(
            payment.id,
            amount_to_paise(refund_amount),
            amount_to_paise(previously_refunded),
            retry_source,
        )
        is_razorpay = str(payment.provider or payment.method or "").strip().lower() == "razorpay"
        refund = Refund(
            tenant_id=order.tenant_id,
            branch_id=order.branch_id,
            order_id=order.id,
            payment_id=payment.id,
            provider="razorpay" if is_razorpay else "manual",
            amount=refund_amount,
            currency="INR",
            status="created" if is_razorpay else "processed",
            reason=data["reason"],
            receipt=receipt,
        )
        db.add(refund)
        db.flush()

        if is_razorpay:
            gateway_payment_id = str(payment.gateway_payment_id or "").strip()
            if not gateway_payment_id:
                raise HTTPException(status_code=409, detail="Razorpay payment id is missing")
            provider_refund = razorpay_request(
                "POST",
                f"/payments/{quote(gateway_payment_id, safe='')}/refund",
                {
                    "amount": amount_to_paise(refund_amount),
                    "speed": data["speed"],
                    "receipt": receipt,
                    "notes": {
                        "order_id": order.id,
                        "payment_id": payment.id,
                        "reason": data["reason"] or "customer_request",
                    },
                },
                idempotency_key=receipt,
            )
            validate_razorpay_refund_entity(refund, payment, provider_refund)
            refund.gateway_refund_id = str(provider_refund["id"])
            refund.status = str(provider_refund.get("status") or "").strip().lower()
            if not refund.status:
                raise HTTPException(status_code=502, detail="Razorpay refund response missing status")

        refresh_order_refund_status(db, order)
        audit(
            db,
            "order.refund_submitted" if refund.status in REFUND_ACTIVE_STATUSES else "order.refunded",
            "refund",
            refund.id,
            user=user,
            branch_id=order.branch_id,
            metadata={
                "order_id": order.id,
                "payment_id": payment.id,
                "amount": f"{refund_amount:.2f}",
                "provider": refund.provider,
                "status": refund.status,
            },
        )
        db.commit()
        db.refresh(refund)
        db.refresh(order)
        return {"refund": serialize_refund(refund), "order": serialize_order(order), "reused": False}

    @app.get("/orders/{order_id}/receipt")
    def receipt(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        return Response(build_receipt_print_data(db, order, user)["text"], media_type="text/plain")

    @app.get("/orders/{order_id}/receipt-print")
    def receipt_print(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        order = db.get(Order, order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Order not found")
        ensure_branch_access(user, order.branch_id)
        return build_receipt_print_data(db, order, user)

    @app.get("/reports/dashboard")
    def dashboard(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        get_accessible_branch(db, user, branch_id)
        return dashboard_metrics(db, user.tenant_id, branch_id)

    @app.get("/reports/store-dashboard")
    def store_dashboard(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        get_accessible_branch(db, user, branch_id)
        return manager_dashboard_metrics(db, user.tenant_id, branch_id)

    @app.get("/reports/manager-dashboard")
    def manager_dashboard(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        get_accessible_branch(db, user, branch_id)
        return manager_dashboard_metrics(db, user.tenant_id, branch_id)

    @app.get("/reports/tenant-analytics")
    def tenant_analytics(db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        # Analytics metrics for the tenantowner across all stores
        revenue = db.scalar(
            select(func.sum(Order.total)).where(
                Order.tenant_id == user.tenant_id,
                Order.status == "completed"
            )
        ) or 0
        orders_count = db.scalar(
            select(func.count(Order.id)).where(
                Order.tenant_id == user.tenant_id
            )
        ) or 0
        customers_count = db.scalar(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == user.tenant_id
            )
        ) or 0
        return {
            "revenue": f"{revenue:.2f}",
            "profit": f"{float(revenue) * 0.38:.2f}",  # Mock margins
            "orders": int(orders_count),
            "customers": int(customers_count),
            "loyalty_usage": "2.4%",
            "inventory_health": "94%",
            "staff_performance": "91%",
        }

    @app.get("/reports/platform-dashboard")
    def platform_dashboard(db: Session = Depends(get_db), user: User = Depends(require_permission("*"))):
        # Platform owner metrics
        total_revenue = db.scalar(select(func.sum(Order.total)).where(Order.status == "completed")) or 0
        active_tenants = db.scalar(select(func.count(Tenant.id)).where(Tenant.status == "active")) or 0
        total_users = db.scalar(select(func.count(User.id))) or 0
        total_stores = db.scalar(select(func.count(Branch.id))) or 0
        return {
            "total_revenue": f"{total_revenue:.2f}",
            "active_tenants": int(active_tenants),
            "total_users": int(total_users),
            "total_stores": int(total_stores),
            "active_subscriptions": int(active_tenants),
            "system_health": "Healthy",
            "api_usage": "14,821 requests/day",
            "storage_usage": "14.2 MB",
            "database_usage": "2.4 MB",
        }

    @app.get("/admin/inactive-monitoring")
    def inactive_monitoring(db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        # Mock alerts for users/stores/tenants inactive for 7, 15, or 30 days
        return {
            "alerts": [
                {"type": "user", "name": "Rohan (Waiter)", "days": 8, "severity": "low"},
                {"type": "store", "name": "Koramangala Branch", "days": 16, "severity": "medium"},
                {"type": "user", "name": "Seema (Accountant)", "days": 31, "severity": "high"},
            ]
        }

    @app.get("/reports/sales")
    def sales_report(branch_id: str, period: str = "daily", db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        get_accessible_branch(db, user, branch_id)
        metrics = dashboard_metrics(db, user.tenant_id, branch_id)
        return {"period": period, "sales": metrics["today_sales"] if period == "daily" else metrics["revenue"]}

    @app.get("/reports/inventory")
    def get_inventory_report(
        branch_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("report:view")),
    ):
        ensure_branch_access(user, branch_id)
        items = db.scalars(
            select(InventoryItem).where(
                InventoryItem.tenant_id == user.tenant_id,
                InventoryItem.branch_id == branch_id,
                InventoryItem.active.is_(True),
            )
        ).all()
        return {
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "quantity": f"{item.quantity:.2f}",
                    "unit": item.unit,
                    "low_stock": item.quantity <= item.low_stock_threshold,
                }
                for item in items
            ]
        }

    @app.get("/reports/sales/export")
    def export_sales_report(
        branch_id: str,
        format: str = "csv",
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("report:view")),
    ):
        ensure_branch_access(user, branch_id)
        metrics = dashboard_metrics(db, user.tenant_id, branch_id)

        if format == "csv":
            content = f"Metric,Value\nToday's Sales,{metrics['today_sales']}\nRevenue,{metrics['revenue']}\nActive Orders,{metrics['active_orders']}\nActive Tables,{metrics['active_tables']}\n"
            return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sales_report.csv"})
        elif format == "pdf":
            content = f"--- Korvexa POS Sales Report ---\nToday's Sales: {metrics['today_sales']}\nRevenue: {metrics['revenue']}\nActive Orders: {metrics['active_orders']}\nActive Tables: {metrics['active_tables']}\n"
            return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=sales_report.pdf"})
        elif format == "excel":
            content = f"<table><tr><th>Metric</th><th>Value</th></tr><tr><td>Today's Sales</td><td>{metrics['today_sales']}</td></tr><tr><td>Revenue</td><td>{metrics['revenue']}</td></tr></table>"
            return Response(content, media_type="application/vnd.ms-excel", headers={"Content-Disposition": "attachment; filename=sales_report.xls"})

        raise HTTPException(status_code=400, detail="Invalid format")

    @app.get("/reports/inventory/export")
    def export_inventory_report(
        branch_id: str,
        format: str = "csv",
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("report:view")),
    ):
        ensure_branch_access(user, branch_id)
        items = db.scalars(
            select(InventoryItem).where(
                InventoryItem.tenant_id == user.tenant_id,
                InventoryItem.branch_id == branch_id,
                InventoryItem.active.is_(True),
            )
        ).all()

        if format == "csv":
            content = "ID,Name,Quantity,Unit,Low Stock Alert\n"
            for item in items:
                content += f"{item.id},{item.name},{item.quantity:.2f},{item.unit},{item.quantity <= item.low_stock_threshold}\n"
            return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=inventory_report.csv"})
        elif format == "pdf":
            content = "--- Korvexa POS Inventory Report ---\n"
            for item in items:
                content += f"{item.name}: {item.quantity:.2f} {item.unit} (Alert: {item.quantity <= item.low_stock_threshold})\n"
            return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=inventory_report.pdf"})
        elif format == "excel":
            content = "<table><tr><th>Name</th><th>Quantity</th><th>Unit</th></tr>"
            for item in items:
                content += f"<tr><td>{item.name}</td><td>{item.quantity:.2f}</td><td>{item.unit}</td></tr>"
            content += "</table>"
            return Response(content, media_type="application/vnd.ms-excel", headers={"Content-Disposition": "attachment; filename=inventory_report.xls"})

        raise HTTPException(status_code=400, detail="Invalid format")

    @app.get("/audit-logs")
    def audit_logs(db: Session = Depends(get_db), user: User = Depends(require_permission("audit:view"))):
        rows = db.scalars(select(AuditLog).where(AuditLog.tenant_id == user.tenant_id).order_by(AuditLog.id.desc())).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "action": row.action,
                    "entity": row.entity,
                    "entity_id": row.entity_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
        }

    @app.get("/tables")
    def list_tables(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        get_accessible_branch(db, user, branch_id)
        rows = db.scalars(
            select(RestaurantTable)
            .where(RestaurantTable.tenant_id == user.tenant_id, RestaurantTable.branch_id == branch_id)
            .order_by(RestaurantTable.floor_area, RestaurantTable.name)
        ).all()
        return {"items": [{"id": row.id, "name": row.name, "capacity": row.capacity, "status": row.status, "floor_area": row.floor_area, "merged_with": row.merged_with, "order_id": row.order_id} for row in rows]}

    @app.get("/table-floors")
    def list_table_floors(branch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        branch = get_accessible_branch(db, user, branch_id)
        rows = db.scalars(
            select(RestaurantTable).where(RestaurantTable.tenant_id == user.tenant_id, RestaurantTable.branch_id == branch_id)
        ).all()
        return {"items": branch_table_floors(branch, rows)}

    @app.post("/table-floors", status_code=201)
    def create_table_floor(
        payload: TableFloorCreate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("table:manage")),
    ):
        branch = get_accessible_branch(db, user, payload.branch_id)
        floor = normalize_floor_name(payload.name)
        remember_branch_floor(branch, floor)
        audit(db, "table_floor.created", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {"items": branch_table_floors(branch), "name": floor}

    @app.patch("/table-floors")
    def update_table_floor(
        payload: TableFloorUpdate,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("table:manage")),
    ):
        branch = get_accessible_branch(db, user, payload.branch_id)
        current_floor = normalize_floor_name(payload.current_name)
        new_floor = normalize_floor_name(payload.name)
        rows = db.scalars(
            select(RestaurantTable).where(RestaurantTable.tenant_id == user.tenant_id, RestaurantTable.branch_id == branch.id)
        ).all()
        floors = branch_table_floors(branch, rows)
        if current_floor.casefold() not in {floor.casefold() for floor in floors}:
            raise HTTPException(status_code=404, detail="Floor not found")
        updated_floors = [new_floor if floor.casefold() == current_floor.casefold() else floor for floor in floors]
        save_branch_floors(branch, updated_floors)
        for table in rows:
            if (table.floor_area or "").casefold() == current_floor.casefold():
                table.floor_area = new_floor
        audit(db, "table_floor.updated", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {"items": branch_table_floors(branch, rows), "name": new_floor}

    @app.delete("/table-floors")
    def delete_table_floor(
        branch_id: str,
        name: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_permission("table:manage")),
    ):
        branch = get_accessible_branch(db, user, branch_id)
        floor = normalize_floor_name(name)
        rows = db.scalars(
            select(RestaurantTable).where(RestaurantTable.tenant_id == user.tenant_id, RestaurantTable.branch_id == branch.id)
        ).all()
        if any((table.floor_area or "").casefold() == floor.casefold() for table in rows):
            raise HTTPException(status_code=400, detail="Move or delete tables before deleting this floor")
        floors = branch_table_floors(branch, rows)
        updated_floors = [item for item in floors if item.casefold() != floor.casefold()]
        if len(updated_floors) == len(floors):
            raise HTTPException(status_code=404, detail="Floor not found")
        save_branch_floors(branch, updated_floors)
        audit(db, "table_floor.deleted", "branch", branch.id, user=user, branch_id=branch.id)
        db.commit()
        return {"items": branch_table_floors(branch, rows)}

    @app.delete("/users/{user_id}")
    def delete_user(user_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("user:manage"))):
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if target.id == user.id:
            raise HTTPException(status_code=400, detail="You cannot delete your own account")
        ensure_can_manage_user(user, target)
        
        # 1. Clean up user_roles, user_sessions, password_reset_tokens
        db.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": target.id})
        db.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": target.id})
        db.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :uid"), {"uid": target.id})
        
        # 2. Cascading delete discount requests and nullify audit logs
        db.execute(text("DELETE FROM discount_requests WHERE requested_by_id = :uid"), {"uid": target.id})
        db.execute(text("UPDATE audit_logs SET user_id = NULL WHERE user_id = :uid"), {"uid": target.id})

        # 3. Cascading delete on associated employee records
        employees = db.scalars(select(Employee).where(Employee.user_id == target.id)).all()
        for emp in employees:
            db.execute(text("DELETE FROM attendances WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM leave_requests WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM payrolls WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM incentives WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM employees WHERE id = :eid"), {"eid": emp.id})
            
        # 4. Finally delete the user
        db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": target.id})
        
        audit(db, "user.deleted", "user", target.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"message": "User deleted successfully"}

    @app.get("/staff/login-sessions")
    def list_login_sessions(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:view"))):
        ensure_branch_access(user, branch_id)
        sessions = db.scalars(select(UserSession).where(UserSession.tenant_id == user.tenant_id, UserSession.branch_id == branch_id).order_by(UserSession.created_at.desc()).limit(100)).all()
        return {"items": [{"id": s.id, "user_id": s.user_id, "user_agent": s.user_agent, "created_at": s.created_at.isoformat(), "revoked": s.revoked_at is not None} for s in sessions]}

    @app.patch("/attendance/{attendance_id}")
    def edit_attendance(attendance_id: str, payload: AttendanceUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        record = db.get(Attendance, attendance_id)
        if not record or record.tenant_id != user.tenant_id:
            raise HTTPException(404, "Not found")
        ensure_branch_access(user, record.branch_id)
        if payload.check_in: record.check_in = datetime.fromisoformat(payload.check_in.replace('Z', '+00:00'))
        if payload.check_out: record.check_out = datetime.fromisoformat(payload.check_out.replace('Z', '+00:00'))
        if payload.overtime_minutes is not None: record.overtime_minutes = payload.overtime_minutes
        if payload.overtime_status is not None: record.overtime_status = payload.overtime_status
        audit(db, "attendance.edited", "attendance", record.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.delete("/attendance/cleanup")
    def cleanup_attendance(db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        cutoff = datetime.now(UTC) - timedelta(days=60)
        stmt = text("DELETE FROM attendances WHERE tenant_id = :tid AND check_in < :cutoff")
        db.execute(stmt, {"tid": user.tenant_id, "cutoff": cutoff})
        audit(db, "attendance.cleanup", "attendance", "", user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.delete("/attendance/{attendance_id}")
    def delete_attendance(attendance_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        record = db.get(Attendance, attendance_id)
        if record and record.tenant_id == user.tenant_id:
            ensure_branch_access(user, record.branch_id)
            db.delete(record)
            audit(db, "attendance.deleted", "attendance", record.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.patch("/payroll/{payroll_id}")
    def update_payroll(payroll_id: str, payload: PayrollUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        record = db.get(Payroll, payroll_id)
        if not record or record.tenant_id != user.tenant_id:
            raise HTTPException(404, "Not found")
        ensure_branch_access(user, record.branch_id)
        updates = payload.model_dump(exclude_unset=True)
        day_salary = updates.get("day_salary", updates.get("base_salary"))
        if day_salary is not None:
            record.base_salary = money(day_salary)
        if updates.get("allowances") is not None:
            record.allowances = money(updates["allowances"])
        if updates.get("deductions") is not None:
            record.deductions = money(updates["deductions"])
        if updates.get("incentives") is not None:
            record.incentives = money(updates["incentives"])
        employee = db.get(Employee, record.employee_id)
        snapshot = payroll_snapshot(db, record, employee)
        audit(db, "payroll.updated", "payroll", record.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True, "net_salary": f"{snapshot['net_salary']:.2f}"}
        
    @app.patch("/employees/{employee_id}")
    def update_employee(employee_id: str, payload: EmployeeUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        emp = db.get(Employee, employee_id)
        if not emp or emp.tenant_id != user.tenant_id:
            raise HTTPException(404, "Not found")
        ensure_branch_access(user, emp.branch_id)
        updates = payload.model_dump(exclude_unset=True)
        if "role" in updates and updates["role"] is not None:
            ensure_can_manage_user(user, role=updates["role"])
        if "email" in updates and updates["email"] and updates["email"] != emp.email:
            if db.scalar(select(Employee).where(Employee.tenant_id == user.tenant_id, Employee.email == updates["email"], Employee.id != emp.id)):
                raise HTTPException(status_code=409, detail="Email already exists")
            if db.scalar(select(User).where(User.email == updates["email"], User.id != emp.user_id)):
                raise HTTPException(status_code=409, detail="Email already exists")
            emp.email = updates["email"]
        if "active" in updates and updates["active"] is not None:
            emp.active = updates["active"]
        if "name" in updates and updates["name"] is not None:
            emp.name = updates["name"]
        if "phone" in updates:
            emp.phone = updates["phone"]
        if "role" in updates and updates["role"] is not None:
            emp.role = updates["role"]
        if "base_salary" in updates and updates["base_salary"] is not None:
            payroll = db.scalar(select(Payroll).where(Payroll.employee_id == emp.id).order_by(Payroll.created_at.desc()))
            if payroll:
                payroll.base_salary = money(updates["base_salary"])
        if emp.user_id:
            linked_user = db.get(User, emp.user_id)
            if linked_user and linked_user.tenant_id == emp.tenant_id:
                if "name" in updates and updates["name"] is not None:
                    linked_user.name = updates["name"]
                if "email" in updates and updates["email"]:
                    linked_user.email = updates["email"]
                if "phone" in updates:
                    linked_user.phone = updates["phone"]
                if "role" in updates and updates["role"] is not None:
                    linked_user.role = updates["role"]
                if "active" in updates and updates["active"] is not None:
                    linked_user.active = updates["active"]
                if updates.get("password"):
                    validate_password_policy(db, user, updates["password"])
                    linked_user.password_hash = hash_password(updates["password"])
        audit(db, "employee.updated", "employee", emp.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.delete("/employees/{employee_id}")
    def delete_employee(employee_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        emp = db.get(Employee, employee_id)
        if emp and emp.tenant_id == user.tenant_id:
            ensure_branch_access(user, emp.branch_id)
            db.execute(text("DELETE FROM attendances WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM leave_requests WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM payrolls WHERE employee_id = :eid"), {"eid": emp.id})
            db.execute(text("DELETE FROM incentives WHERE employee_id = :eid"), {"eid": emp.id})
            db.delete(emp)
            audit(db, "employee.deleted", "employee", emp.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.post("/payroll/{payroll_id}/pay")
    def pay_payroll(payroll_id: str, payload: PayrollPay, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        record = db.get(Payroll, payroll_id)
        if not record or record.tenant_id != user.tenant_id:
            raise HTTPException(404, "Not found")
        ensure_branch_access(user, record.branch_id)
        current_payout_status = str(record.payout_status or "").strip().lower()
        if (
            record.payout_provider == "razorpayx"
            and record.payout_id
            and current_payout_status in {"queued", "pending", "processing"}
        ):
            return {
                "success": True,
                "status": "processing",
                "payout_status": current_payout_status,
                "payout_id": record.payout_id,
                "reused": True,
            }
        employee = db.get(Employee, record.employee_id)
        payroll_snapshot(db, record, employee)
        payment_reference = (payload.payment_reference or "").strip()
        if payload.payment_mode == "upi" and not payment_reference and payload.gateway_provider != "razorpayx":
            raise HTTPException(status_code=422, detail="UPI transaction reference is required")
        if payload.gateway_provider == "razorpayx":
            recipient_upi = (payload.recipient_upi or "").strip()
            if payload.payment_mode != "upi":
                raise HTTPException(status_code=422, detail="RazorpayX payouts currently require UPI payment mode")
            if not recipient_upi:
                raise HTTPException(status_code=422, detail="Recipient UPI ID is required")
            account_number = (os.getenv("RAZORPAYX_ACCOUNT_NUMBER") or "").strip()
            if not account_number or looks_like_placeholder(account_number):
                raise HTTPException(status_code=503, detail="RAZORPAYX_ACCOUNT_NUMBER is not configured")
            payout_reference_id = record.id[:40]
            payout = razorpay_request(
                "POST",
                "/payouts",
                {
                    "account_number": account_number,
                    "amount": amount_to_paise(record.net_salary),
                    "currency": "INR",
                    "mode": "UPI",
                    "purpose": "salary",
                    "queue_if_low_balance": True,
                    "reference_id": payout_reference_id,
                    "narration": "Payroll",
                    "fund_account": {
                        "account_type": "vpa",
                        "vpa": {"address": recipient_upi},
                        "contact": {
                            "name": payload.recipient_name or employee.name if employee else "Payroll Staff",
                            "email": str(payload.recipient_email or (employee.email if employee else "")) or None,
                            "contact": payload.recipient_phone or (employee.phone if employee else None),
                            "type": "employee",
                        },
                    },
                    "notes": {
                        "payroll_id": record.id,
                        "employee_id": record.employee_id,
                        "branch_id": record.branch_id,
                    },
                },
                prefix="RAZORPAYX",
                idempotency_key=razorpayx_payout_idempotency_key(record),
            )
            record.payout_provider = "razorpayx"
            record.payout_id = payout.get("id")
            record.payout_status = str(payout.get("status") or "processing").strip().lower()
            payment_reference = payout.get("utr") or payout.get("reference_id") or payout.get("id") or payment_reference
            if record.payout_status in {"processed", "completed", "settled"}:
                record.status = "paid"
            elif record.payout_status in {"failed", "reversed", "rejected", "cancelled", "canceled"}:
                record.status = "pending"
            else:
                record.status = "processing"
        else:
            record.status = "paid"
        record.payment_mode = payload.payment_mode
        record.payment_reference = payment_reference or None
        audit_action = "payroll.payout_submitted" if payload.gateway_provider == "razorpayx" and record.status == "processing" else "payroll.paid"
        audit(db, audit_action, "payroll", record.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {
            "success": True,
            "status": record.status,
            "payout_status": record.payout_status,
            "payout_id": record.payout_id,
            "reused": False,
        }

    @app.delete("/payroll/{payroll_id}")
    def delete_payroll(payroll_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        record = db.get(Payroll, payroll_id)
        if record and record.tenant_id == user.tenant_id:
            ensure_branch_access(user, record.branch_id)
            db.delete(record)
            audit(db, "payroll.deleted", "payroll", record.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.post("/incentives")
    def create_incentive(payload: IncentiveCreate, branch_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        target_branch_id = branch_id or payload.branch_id
        if not target_branch_id:
            raise HTTPException(status_code=400, detail="Branch is required")
        ensure_branch_access(user, target_branch_id)
        employee_ids = [payload.employee_id] if payload.employee_id else [e.id for e in db.scalars(select(Employee).where(Employee.tenant_id == user.tenant_id, Employee.branch_id == target_branch_id, Employee.active.is_(True)))]
        created = []
        for eid in employee_ids:
            emp = db.get(Employee, eid)
            if not emp or emp.tenant_id != user.tenant_id or emp.branch_id != target_branch_id:
                raise HTTPException(status_code=404, detail="Employee not found")
            inc = Incentive(tenant_id=user.tenant_id, branch_id=target_branch_id, employee_id=eid, sales_amount=Decimal(str(payload.sales_amount)), incentive_amount=Decimal(str(payload.incentive_amount)))
            db.add(inc)
            created.append(inc)
        audit(db, "incentives.created", "incentive", "", user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"count": len(created)}

    @app.patch("/incentives/{incentive_id}")
    def update_incentive(incentive_id: str, payload: IncentiveUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        inc = db.get(Incentive, incentive_id)
        if not inc or inc.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Incentive not found")
        ensure_branch_access(user, inc.branch_id)
        updates = payload.model_dump(exclude_unset=True)
        if updates.get("employee_id"):
            emp = db.get(Employee, updates["employee_id"])
            if not emp or emp.tenant_id != user.tenant_id or emp.branch_id != inc.branch_id:
                raise HTTPException(status_code=404, detail="Employee not found")
            inc.employee_id = emp.id
        if updates.get("sales_amount") is not None:
            inc.sales_amount = money(updates["sales_amount"])
        if updates.get("incentive_amount") is not None:
            inc.incentive_amount = money(updates["incentive_amount"])
        audit(db, "incentive.updated", "incentive", inc.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.delete("/incentives/{incentive_id}")
    def delete_incentive(incentive_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        inc = db.get(Incentive, incentive_id)
        if inc and inc.tenant_id == user.tenant_id:
            ensure_branch_access(user, inc.branch_id)
            db.delete(inc)
            audit(db, "incentive.deleted", "incentive", inc.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.post("/incentives/{incentive_id}/payout")
    def payout_incentive(incentive_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("employee:manage"))):
        inc = db.get(Incentive, incentive_id)
        if not inc or inc.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Incentive not found")
        ensure_branch_access(user, inc.branch_id)
        period = datetime.now(UTC).strftime("%Y-%m")
        payroll = db.scalar(select(Payroll).where(Payroll.employee_id == inc.employee_id, Payroll.salary_period == period))
        if not payroll:
            emp = db.get(Employee, inc.employee_id)
            if not emp:
                raise HTTPException(status_code=404, detail="Employee not found")
            payroll = Payroll(
                tenant_id=inc.tenant_id,
                branch_id=inc.branch_id,
                employee_id=inc.employee_id,
                salary_period=period,
                base_salary=money(0),
                incentives=money(0),
                net_salary=money(0),
            )
            db.add(payroll)
            db.flush()
        payroll.incentives = money(payroll.incentives) + money(inc.incentive_amount)
        db.delete(inc)
        employee = db.get(Employee, payroll.employee_id)
        payroll_snapshot(db, payroll, employee)
        audit(db, "incentive.paid_out", "incentive", incentive_id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.delete("/products/{product_id}")
    def delete_product(product_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("menu:manage"))):
        p = db.get(Product, product_id)
        if p and p.tenant_id == user.tenant_id:
            ensure_branch_access(user, p.branch_id)
            p.active = False
            p.available = False
            audit(db, "product.deleted", "product", p.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.patch("/products/{product_id}")
    def update_product(product_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("menu:manage"))):
        p = db.get(Product, product_id)
        if p and p.tenant_id == user.tenant_id:
            ensure_branch_access(user, p.branch_id)
            if "available" in payload:
                p.available = payload["available"]
            audit(db, "product.updated", "product", p.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.delete("/inventory/items/{item_id}")
    def delete_inventory_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("inventory:manage"))):
        item = db.get(InventoryItem, item_id)
        if item and item.tenant_id == user.tenant_id:
            ensure_branch_access(user, item.branch_id)
            item.active = False
            db.query(ProductRecipe).filter(
                ProductRecipe.tenant_id == user.tenant_id,
                ProductRecipe.branch_id == item.branch_id,
                ProductRecipe.inventory_item_id == item.id,
                ProductRecipe.active.is_(True),
            ).update({"active": False}, synchronize_session=False)
            audit(db, "inventory.deleted", "item", item.id, user=user, tenant_id=user.tenant_id)
            db.commit()
        return {"success": True}

    @app.post("/discounts/request")
    def request_discount(payload: DiscountRequestCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
        order = db.get(Order, payload.order_id)
        if not order or order.tenant_id != user.tenant_id:
            raise HTTPException(404, "Order not found")
        ensure_branch_access(user, order.branch_id)
        req = DiscountRequest(tenant_id=user.tenant_id, branch_id=order.branch_id, order_id=order.id, requested_by_id=user.id, amount_or_percentage=Decimal(payload.amount_or_percentage), is_percentage=payload.is_percentage)
        db.add(req)
        audit(db, "discount.requested", "discount_request", req.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"id": req.id}

    @app.patch("/discounts/requests/{req_id}/approve")
    def approve_discount(req_id: str, payload: DiscountRequestApprove, db: Session = Depends(get_db), user: User = Depends(require_permission("order:manage"))):
        req = db.get(DiscountRequest, req_id)
        if not req or req.tenant_id != user.tenant_id:
            raise HTTPException(404, "Not found")
        ensure_branch_access(user, req.branch_id)
        req.status = payload.status
        req.resolved_at = naive_utcnow()
        if payload.status == "approved":
            order = db.get(Order, req.order_id)
            if not order or order.tenant_id != user.tenant_id:
                raise HTTPException(404, "Order not found")
            gross_total = money(order.subtotal) + money(order.tax_amount)
            amt = money(req.amount_or_percentage)
            if gross_total <= 0:
                raise HTTPException(400, "Order has no billable total")
            if req.is_percentage:
                if amt <= 0 or amt > Decimal("100"):
                    raise HTTPException(400, "Percentage discount must be between 0 and 100")
                discount_amount = money(gross_total * (amt / Decimal("100")))
            else:
                if amt <= 0:
                    raise HTTPException(400, "Discount amount must be greater than zero")
                discount_amount = money(amt)
            if discount_amount > gross_total:
                raise HTTPException(400, "Discount cannot exceed bill total")
            order.discount_amount = discount_amount
            order.total = money(gross_total - discount_amount)
            captured = captured_payment_total(order)
            if captured >= money(order.total):
                order.payment_status = "paid"
                order.status = "completed"
            elif captured > 0:
                order.payment_status = "partial"
            else:
                order.payment_status = "unpaid"
        audit(db, f"discount.{payload.status}", "discount_request", req.id, user=user, tenant_id=user.tenant_id)
        db.commit()
        return {"success": True}

    @app.get("/discounts/requests/pending")
    def pending_discounts(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("order:manage"))):
        ensure_branch_access(user, branch_id)
        reqs = db.scalars(select(DiscountRequest).where(DiscountRequest.tenant_id == user.tenant_id, DiscountRequest.branch_id == branch_id, DiscountRequest.status == "pending")).all()
        items = []
        for r in reqs:
            order = db.get(Order, r.order_id)
            requested_by = db.get(User, r.requested_by_id)
            gross_total = money(order.subtotal) + money(order.tax_amount) if order else Decimal("0.00")
            requested_value = money(r.amount_or_percentage)
            discount_amount = (
                money(gross_total * (requested_value / Decimal("100"))) if r.is_percentage else requested_value
            )
            if discount_amount > gross_total:
                discount_amount = gross_total
            proposed_total = money(gross_total - discount_amount)
            items.append({
                "id": r.id,
                "order_id": r.order_id,
                "requested_by_id": r.requested_by_id,
                "requested_by_name": requested_by.name if requested_by else "Unknown user",
                "amount_or_percentage": float(r.amount_or_percentage),
                "is_percentage": r.is_percentage,
                "bill_total": f"{gross_total:.2f}",
                "discount_amount": f"{discount_amount:.2f}",
                "proposed_total": f"{proposed_total:.2f}",
                "created_at": r.created_at.isoformat(),
            })
        return {"items": items}

    @app.get("/settings/tax")
    def get_tax_settings(branch_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        ensure_branch_access(user, branch_id)
        branch = db.get(Branch, branch_id)
        tenant = db.get(Tenant, user.tenant_id)
        branch_settings = branch.settings or {}
        tenant_settings = tenant.settings or {}
        return {
            "receipt_name": branch_settings.get("receipt_name", tenant_settings.get("receipt_name", branch.name)),
            "gst_number": branch_settings.get("gst_number", tenant_settings.get("gst_number", "")),
            "food_gst_rate": branch_settings.get("food_gst_rate", tenant_settings.get("food_gst_rate", 5.0)),
            "beverage_gst_rate": branch_settings.get("beverage_gst_rate", tenant_settings.get("beverage_gst_rate", 18.0)),
            "upi_id": branch_settings.get("upi_id", tenant_settings.get("upi_id", "")),
            "upi_qr_url": branch_settings.get("upi_qr_url", tenant_settings.get("upi_qr_url", "")),
            "receipt_footer": branch_settings.get("receipt_footer", tenant_settings.get("receipt_footer", "Thank you! Visit again.")),
        }

    @app.patch("/settings/tax")
    def set_tax_settings(branch_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_permission("report:view"))):
        ensure_branch_access(user, branch_id)
        branch = db.get(Branch, branch_id)
        settings = dict(branch.settings or {})
        if "receipt_name" in payload: settings["receipt_name"] = str(payload["receipt_name"])
        if "gst_number" in payload: settings["gst_number"] = payload["gst_number"]
        if "food_gst_rate" in payload: settings["food_gst_rate"] = float(payload["food_gst_rate"])
        if "beverage_gst_rate" in payload: settings["beverage_gst_rate"] = float(payload["beverage_gst_rate"])
        if "upi_id" in payload: settings["upi_id"] = str(payload["upi_id"])
        if "upi_qr_url" in payload: settings["upi_qr_url"] = str(payload["upi_qr_url"])
        if "receipt_footer" in payload: settings["receipt_footer"] = str(payload["receipt_footer"])
        branch.settings = settings
        updated_products = 0
        if payload.get("apply_to_menu", True) and "food_gst_rate" in payload:
            updated_products = db.query(Product).filter(
                Product.tenant_id == user.tenant_id,
                Product.branch_id == branch_id,
            ).update({Product.tax_rate: Decimal(str(payload["food_gst_rate"]))}, synchronize_session=False)
        db.add(branch)
        audit(db, "settings.tax.updated", "branch", branch.id, user=user, tenant_id=user.tenant_id, metadata={"updated_products": updated_products})
        db.commit()
        return {**settings, "updated_products": updated_products}

    return app


app = create_app()
