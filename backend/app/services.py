import os
import datetime as datetime_module
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import (
    AuditLog, Branch, Customer, Attendance, DiscountRequest, Employee,
    InventoryItem, Order, OrderItem, Payment, Payroll, Product, Refund,
    ProductRecipe, PurchaseOrder, RestaurantTable, StockMovement,
    Supplier, Tenant, User
)

CAPTURED_PAYMENT_STATUSES = {"captured", "completed", "paid"}


def normalize_payment_status(status: object) -> str:
    return str(status or "captured").strip().lower()


def _system_timezone():
    return datetime_module.datetime.now().astimezone().tzinfo or ZoneInfo("UTC")

def _load_timezone(tz_str):
    if not tz_str:
        return _system_timezone()
    try:
        return ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        return _system_timezone()

def business_timezone(db: Session, tenant_id: str, branch_id: str = None) -> ZoneInfo:
    if branch_id:
        branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant_id))
        if branch and branch.settings and branch.settings.get("timezone"):
            return _load_timezone(branch.settings.get("timezone"))
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant and tenant.settings and tenant.settings.get("timezone"):
        return _load_timezone(tenant.settings.get("timezone"))
    return _system_timezone()

def business_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()

def local_date(dt: datetime | date | None, tz: ZoneInfo) -> date | None:
    if not dt:
        return None
    if isinstance(dt, datetime_module.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(tz).date()
    if isinstance(dt, datetime_module.date):
        return dt
    return None

def money(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def audit(
    db: Session,
    action: str,
    entity: str,
    entity_id: str,
    user=None,
    branch_id: str = None,
    tenant_id: str = None,
    metadata: dict | None = None,
):
    t_id = tenant_id
    if not t_id and user:
        t_id = user.tenant_id
    
    log = AuditLog(
        tenant_id=t_id,
        branch_id=branch_id,
        user_id=user.id if user else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        metadata_json=metadata or {},
    )
    db.add(log)

def get_or_create_customer(db: Session, tenant_id: str, payload: dict | None) -> Customer | None:
    if not payload or not payload.get("phone"):
        return None
    phone = payload["phone"]
    customer = db.scalar(select(Customer).where(Customer.tenant_id == tenant_id, Customer.phone == phone))
    if customer:
        if payload.get("name"):
            customer.name = payload["name"]
        return customer
    customer = Customer(tenant_id=tenant_id, phone=phone, name=payload.get("name") or phone)
    db.add(customer)
    db.flush()
    return customer

def create_supplier_if_needed(db: Session, tenant_id: str, name: str) -> Supplier | None:
    if not name:
        return None
    supplier = db.scalar(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.name == name))
    if not supplier:
        supplier = Supplier(tenant_id=tenant_id, name=name)
        db.add(supplier)
        db.flush()
    return supplier

def build_order(db: Session, tenant_id: str, payload: dict) -> Order:
    customer = get_or_create_customer(db, tenant_id, payload.get("customer"))
    branch_id = payload["branch_id"]
    branch = db.get(Branch, branch_id)
    tenant = db.get(Tenant, tenant_id)
    default_tax_rate = Decimal("0.00")
    if branch and branch.settings and "tax_rate" in branch.settings:
        default_tax_rate = money(branch.settings["tax_rate"])
    elif tenant and tenant.settings and "tax_rate" in tenant.settings:
        default_tax_rate = money(tenant.settings["tax_rate"])

    order = Order(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=payload.get("table_id"),
        customer_id=customer.id if customer else None,
        order_type=payload.get("order_type", "dine_in"),
        discount_amount=money(payload.get("discount_amount", 0)),
    )
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")

    for item in payload.get("items", []):
        product = db.get(Product, item["product_id"])
        if product is None or product.tenant_id != tenant_id or product.branch_id != branch_id:
            raise ValueError("Invalid product")

        variant_name = item.get("variant_name")
        variant_delta = Decimal("0.00")
        if variant_name:
            for variant in product.variants or []:
                if variant.get("name") == variant_name:
                    variant_delta = money(variant.get("price_delta", 0))
                    break

        addons = item.get("addons") or []
        addons_total = sum((money(addon.get("price", 0)) for addon in addons), Decimal("0.00"))
        unit_price = money(product.price) + variant_delta + addons_total
        quantity = int(item.get("quantity", 1))
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        line_subtotal = money(unit_price * quantity)
        applied_tax_rate = money(product.tax_rate) if money(product.tax_rate) > 0 else default_tax_rate
        line_tax = money(line_subtotal * applied_tax_rate / Decimal("100"))
        line_total = line_subtotal + line_tax
        subtotal += line_subtotal
        tax_total += line_tax
        order.items.append(OrderItem(
            product_id=product.id,
            name=product.name,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=applied_tax_rate,
            tax_amount=line_tax,
            line_total=line_total,
            variant_name=variant_name,
            addons=addons,
            notes=item.get("notes"),
        ))

    if not order.items:
        raise ValueError("Order must include at least one item")

    order.subtotal = money(subtotal)
    order.tax_amount = money(tax_total)
    order.total = money(subtotal + tax_total - money(order.discount_amount))
    if order.total < 0:
        raise ValueError("Order total cannot be negative")
    db.add(order)
    db.flush()
    return order

def serialize_product_recipe(recipe: ProductRecipe) -> dict:
    return {
        "id": recipe.id,
        "inventory_item_id": recipe.inventory_item_id,
        "quantity_per_unit": f"{money(recipe.quantity_per_unit):.2f}",
        "wastage_percent": f"{money(recipe.wastage_percent):.2f}",
        "active": recipe.active,
    }

def replace_product_recipe(db: Session, tenant_id: str, product_id: str, items: list) -> list[ProductRecipe]:
    product = db.get(Product, product_id)
    if not product or product.tenant_id != tenant_id:
        raise ValueError("Product not found")
    db.execute(ProductRecipe.__table__.delete().where(ProductRecipe.product_id == product_id))
    recipes = []
    for item in items:
        inventory_item = db.get(InventoryItem, item["inventory_item_id"])
        if not inventory_item or inventory_item.tenant_id != tenant_id or inventory_item.branch_id != product.branch_id:
            raise ValueError("Invalid recipe inventory item")
        recipe = ProductRecipe(
            tenant_id=tenant_id,
            branch_id=product.branch_id,
            product_id=product_id,
            inventory_item_id=item["inventory_item_id"],
            quantity_per_unit=money(item["quantity_per_unit"]),
            wastage_percent=money(item.get("wastage_percent", 0)),
            active=item.get("active", True),
        )
        db.add(recipe)
        recipes.append(recipe)
    db.flush()
    return recipes

def list_product_recipe(db: Session, tenant_id: str, product_id: str) -> list[ProductRecipe]:
    product = db.get(Product, product_id)
    if not product or product.tenant_id != tenant_id:
        raise ValueError("Product not found")
    return db.scalars(select(ProductRecipe).where(ProductRecipe.product_id == product_id)).all()

def _order_inventory_requirements(db: Session, order: Order) -> dict:
    reqs = {}
    items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    for item in items:
        recipes = db.scalars(
            select(ProductRecipe).where(ProductRecipe.product_id == item.product_id, ProductRecipe.active == True)
        ).all()
        for recipe in recipes:
            base_qty = money(recipe.quantity_per_unit) * item.quantity
            wastage_qty = base_qty * money(recipe.wastage_percent) / Decimal("100")
            reqs[recipe.inventory_item_id] = reqs.get(recipe.inventory_item_id, Decimal("0.00")) + money(base_qty + wastage_qty)
    return reqs

def fulfill_order_inventory(db: Session, order: Order) -> None:
    existing = db.scalar(
        select(StockMovement).where(
            StockMovement.order_id == order.id,
            StockMovement.movement_type == "order_fulfillment",
        )
    )
    if existing:
        return
    reqs = _order_inventory_requirements(db, order)
    for inv_id, qty in reqs.items():
        inv = db.scalar(select(InventoryItem).where(InventoryItem.id == inv_id))
        if not inv or inv.tenant_id != order.tenant_id or inv.branch_id != order.branch_id or not inv.active:
            raise ValueError("Invalid recipe inventory item")
        if money(inv.quantity) < qty:
            raise ValueError("Insufficient stock")
    for inv_id, qty in reqs.items():
        inv = db.scalar(select(InventoryItem).where(InventoryItem.id == inv_id))
        inv.quantity = money(inv.quantity) - qty
        db.add(StockMovement(
            tenant_id=order.tenant_id, branch_id=order.branch_id,
            inventory_item_id=inv_id, order_id=order.id, quantity=-qty,
            movement_type="order_fulfillment", notes=f"Order {order.id}"
        ))

def reverse_order_inventory(db: Session, order: Order, reason: str = "cancelled") -> None:
    existing_reversal = db.scalar(
        select(StockMovement).where(
            StockMovement.order_id == order.id,
            StockMovement.movement_type == "reversal",
        )
    )
    if existing_reversal:
        return
    fulfilled = db.scalar(
        select(StockMovement).where(
            StockMovement.order_id == order.id,
            StockMovement.movement_type == "order_fulfillment",
        )
    )
    if not fulfilled:
        return
    reqs = _order_inventory_requirements(db, order)
    for inv_id, qty in reqs.items():
        inv = db.scalar(select(InventoryItem).where(InventoryItem.id == inv_id))
        if inv:
            inv.quantity = money(inv.quantity) + qty
            db.add(StockMovement(
                tenant_id=order.tenant_id, branch_id=order.branch_id,
                inventory_item_id=inv_id, order_id=order.id, quantity=qty,
                movement_type="reversal", notes=f"Order {order.id} {reason}"
            ))

def serialize_order(order: Order, items: list[OrderItem] = None, payments: list[Payment] = None) -> dict:
    _items = items if items is not None else getattr(order, "items", [])
    _payments = payments if payments is not None else getattr(order, "payments", [])
    return {
        "id": order.id,
        "branch_id": order.branch_id,
        "table_id": order.table_id,
        "order_type": order.order_type,
        "status": order.status,
        "kds_status": order.kds_status,
        "subtotal": f"{money(order.subtotal):.2f}",
        "tax_amount": f"{money(order.tax_amount):.2f}",
        "discount_amount": f"{money(order.discount_amount):.2f}",
        "payment_status": order.payment_status,
        "total": f"{money(order.total):.2f}",
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "id": i.id, "product_id": i.product_id, "name": i.name,
                "quantity": i.quantity,
                "unit_price": f"{money(i.unit_price):.2f}",
                "tax_rate": f"{money(i.tax_rate):.2f}",
                "tax_amount": f"{money(i.tax_amount):.2f}",
                "line_total": f"{money(i.line_total):.2f}",
                "variant_name": i.variant_name,
                "addons": i.addons or [],
                "notes": i.notes,
            } for i in _items
        ],
        "payments": [
            {
                "id": p.id, "amount": f"{money(p.amount):.2f}", "method": p.method,
                "reference": p.reference, "status": p.status, "created_at": p.created_at.isoformat(),
                "provider": p.provider,
                "gateway_order_id": p.gateway_order_id,
                "gateway_payment_id": p.gateway_payment_id,
            } for p in _payments
        ]
    }

def apply_payments(db: Session, order: Order, payments: list[dict]) -> None:
    incoming_captured_total = sum(
        (
            money(payment.get("amount", 0))
            for payment in payments
            if normalize_payment_status(payment.get("status", "captured")) in CAPTURED_PAYMENT_STATUSES
        ),
        Decimal("0.00"),
    )
    existing_total = sum((money(p.amount) for p in order.payments if normalize_payment_status(p.status) in CAPTURED_PAYMENT_STATUSES), Decimal("0.00"))
    if existing_total + incoming_captured_total > money(order.total):
        raise ValueError("Payment amount exceeds order total")
    for payment in payments:
        amount = money(payment.get("amount", 0))
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")
        db.add(Payment(
            order_id=order.id,
            method=payment.get("method", "cash"),
            amount=amount,
            reference=payment.get("reference"),
            status=normalize_payment_status(payment.get("status", "captured")),
        ))
    total_paid = existing_total + incoming_captured_total
    order.payment_status = "paid" if total_paid >= money(order.total) else ("partial" if total_paid > 0 else "unpaid")
    if order.payment_status == "paid":
        order.status = "completed"

def dashboard_metrics(db: Session, tenant_id: str, branch_id: str = None) -> dict:
    return manager_dashboard_metrics(db, tenant_id, branch_id)

def manager_dashboard_metrics(db: Session, tenant_id: str, branch_id: str) -> dict:
    tz = business_timezone(db, tenant_id, branch_id)
    today = business_today(tz)
    month_key = today.strftime("%Y-%m")
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]
    this_month_start = today.replace(day=1)
    month_days = [this_month_start + timedelta(days=offset) for offset in range((today - this_month_start).days + 1)]
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    order_q = select(Order).where(Order.tenant_id == tenant_id)
    table_q = select(RestaurantTable).where(RestaurantTable.tenant_id == tenant_id)
    inv_q = select(InventoryItem).where(InventoryItem.tenant_id == tenant_id)
    emp_q = select(Employee).where(Employee.tenant_id == tenant_id)
    user_q = select(User).where(User.tenant_id == tenant_id)
    att_q = select(Attendance).where(Attendance.tenant_id == tenant_id)
    po_q = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    pay_q = select(Payroll).where(Payroll.tenant_id == tenant_id)
    disc_q = select(func.count()).select_from(DiscountRequest).where(DiscountRequest.tenant_id == tenant_id, DiscountRequest.status == "pending")

    if branch_id:
        order_q = order_q.where(Order.branch_id == branch_id)
        table_q = table_q.where(RestaurantTable.branch_id == branch_id)
        inv_q = inv_q.where(InventoryItem.branch_id == branch_id)
        emp_q = emp_q.where(Employee.branch_id == branch_id)
        att_q = att_q.where(Attendance.branch_id == branch_id)
        po_q = po_q.where(PurchaseOrder.branch_id == branch_id)
        pay_q = pay_q.where(Payroll.branch_id == branch_id)
        disc_q = disc_q.where(DiscountRequest.branch_id == branch_id)

    orders = db.scalars(order_q).all()
    tables = db.scalars(table_q).all()
    inventory_items = db.scalars(inv_q).all()
    employees = db.scalars(emp_q).all()
    users = db.scalars(user_q).all()
    attendance_rows = db.scalars(att_q).all()
    purchase_orders = db.scalars(po_q).all()
    payrolls = db.scalars(pay_q).all()
    pending_discount_count = db.scalar(disc_q)

    employee_by_id = {e.id: e for e in employees}
    employee_by_user_id = {e.user_id: e for e in employees if e.user_id}
    employee_by_email = {e.email.lower(): e for e in employees if e.email}

    completed_orders = [o for o in orders if o.status == "completed"]
    completed_today = [o for o in completed_orders if local_date(o.created_at, tz) == today]
    orders_today = [o for o in orders if local_date(o.created_at, tz) == today]
    active_orders = [o for o in orders if o.status in {"held", "active"}]
    pending_orders = [o for o in orders if o.status not in {"completed", "cancelled", "voided"}]
    last_month_orders = [o for o in completed_orders if last_month_start <= local_date(o.created_at, tz) <= last_month_end]

    table_counts = {"available": 0, "occupied": 0, "reserved": 0, "cleaning": 0, "out_of_service": 0}
    for t in tables:
        table_counts[t.status] = table_counts.get(t.status, 0) + 1

    low_stock = [i for i in inventory_items if money(i.quantity) <= money(i.low_stock_threshold)]
    attendance_today = [r for r in attendance_rows if local_date(r.check_in, tz) == today]
    active_staff = [r for r in attendance_rows if r.check_out is None]
    purchase_orders_today = [po for po in purchase_orders if local_date(po.created_at, tz) == today]
    purchase_orders_month = [po for po in purchase_orders if local_date(po.created_at, tz).strftime("%Y-%m") == month_key]
    pending_payrolls = [p for p in payrolls if p.status != "paid"]

    item_q = select(OrderItem.name, func.sum(OrderItem.quantity).label("quantity")).join(Order, Order.id == OrderItem.order_id).where(Order.tenant_id == tenant_id, Order.status == "completed")
    payment_q = (
        select(Payment.method, func.sum(Payment.amount).label("amount"))
        .join(Order, Order.id == Payment.order_id)
        .where(
            Order.tenant_id == tenant_id,
            Order.status == "completed",
            func.lower(func.trim(Payment.status)).in_(CAPTURED_PAYMENT_STATUSES),
        )
    )
    if branch_id:
        item_q = item_q.where(Order.branch_id == branch_id)
        payment_q = payment_q.where(Order.branch_id == branch_id)
    item_rows = db.execute(item_q.group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(5)).all()
    payment_rows = db.execute(payment_q.group_by(Payment.method)).all()
    refund_method_q = (
        select(Payment.method, func.sum(Refund.amount).label("amount"))
        .join(Payment, Payment.id == Refund.payment_id)
        .join(Order, Order.id == Refund.order_id)
        .where(
            Order.tenant_id == tenant_id,
            Refund.status.in_({"processed", "completed", "refunded"}),
        )
    )
    if branch_id:
        refund_method_q = refund_method_q.where(Order.branch_id == branch_id)
    refund_method_rows = db.execute(refund_method_q.group_by(Payment.method)).all()
    gateway_payment_q = (
        select(Payment.provider, func.sum(Payment.amount).label("amount"))
        .join(Order, Order.id == Payment.order_id)
        .where(
            Order.tenant_id == tenant_id,
            Order.status == "completed",
            Payment.provider.is_not(None),
            func.lower(func.trim(Payment.status)).in_(CAPTURED_PAYMENT_STATUSES),
        )
    )
    if branch_id:
        gateway_payment_q = gateway_payment_q.where(Order.branch_id == branch_id)
    gateway_payment_rows = db.execute(gateway_payment_q.group_by(Payment.provider)).all()
    refund_gateway_q = (
        select(Payment.provider, func.sum(Refund.amount).label("amount"))
        .join(Payment, Payment.id == Refund.payment_id)
        .join(Order, Order.id == Refund.order_id)
        .where(
            Order.tenant_id == tenant_id,
            Payment.provider.is_not(None),
            Refund.status.in_({"processed", "completed", "refunded"}),
        )
    )
    if branch_id:
        refund_gateway_q = refund_gateway_q.where(Order.branch_id == branch_id)
    refund_gateway_rows = db.execute(refund_gateway_q.group_by(Payment.provider)).all()
    refund_by_method = {method: money(amount) for method, amount in refund_method_rows}
    refund_by_gateway = {provider: money(amount) for provider, amount in refund_gateway_rows}
    net_payment_methods = {
        method: max(Decimal("0.00"), money(amount) - refund_by_method.get(method, Decimal("0.00")))
        for method, amount in payment_rows
    }
    net_payment_gateways = {
        provider: max(Decimal("0.00"), money(amount) - refund_by_gateway.get(provider, Decimal("0.00")))
        for provider, amount in gateway_payment_rows
    }

    order_status_counts = {}
    for o in orders:
        order_status_counts[o.status] = order_status_counts.get(o.status, 0) + 1

    daily_sales_by_date = {day: Decimal("0.00") for day in week_days}
    today_order_types = {
        "dine_in": {"orders": 0, "sales": "0.00"},
        "takeaway": {"orders": 0, "sales": "0.00"},
        "delivery": {"orders": 0, "sales": "0.00"}
    }
    today_sales_by_type = {k: Decimal("0.00") for k in today_order_types}
    for o in completed_orders:
        order_date = local_date(o.created_at, tz)
        if order_date in daily_sales_by_date:
            daily_sales_by_date[order_date] += money(o.total)
        if order_date == today and o.order_type in today_order_types:
            today_sales_by_type[o.order_type] += money(o.total)
    
    for o in orders_today:
        if o.order_type in today_order_types:
            today_order_types[o.order_type]["orders"] += 1
    for ot, tot in today_sales_by_type.items():
        today_order_types[ot]["sales"] = f"{tot:.2f}"

    payout_method_totals: dict[str, Decimal] = {}
    payout_gateway_totals: dict[str, Decimal] = {}
    settled_payout_statuses = {"processed", "completed", "settled"}
    for payroll in payrolls:
        if payroll.status != "paid":
            continue
        payment_mode = payroll.payment_mode or "unknown"
        payout_method_totals[payment_mode] = payout_method_totals.get(payment_mode, Decimal("0.00")) + money(payroll.net_salary)
        payout_status = (payroll.payout_status or "").lower()
        if payroll.payout_provider and (not payout_status or payout_status in settled_payout_statuses):
            payout_gateway_totals[payroll.payout_provider] = payout_gateway_totals.get(payroll.payout_provider, Decimal("0.00")) + money(payroll.net_salary)

    active_staff_details = []
    for r in active_staff:
        e = employee_by_id.get(r.employee_id)
        active_staff_details.append({
            "id": r.id, "employee_id": e.employee_id if e else r.employee_id,
            "name": e.name if e else "Unknown Staff", "role": e.role if e else "",
            "check_in": r.check_in.isoformat(), "check_in_time": r.check_in.strftime("%H:%M")
        })

    weekly_attendance_people = {}
    for u in users:
        e = employee_by_user_id.get(u.id) or employee_by_email.get(u.email.lower())
        key = e.id if e else f"user:{u.id}"
        weekly_attendance_people[key] = {"id": key, "employee": e, "name": e.name if e else u.name, "role": e.role if e else u.role}
    for e in employees:
        weekly_attendance_people.setdefault(e.id, {"id": e.id, "employee": e, "name": e.name, "role": e.role})

    attendance_by_employee_day = {}
    for r in attendance_rows:
        r_date = local_date(r.check_in, tz)
        if r_date in week_days:
            attendance_by_employee_day.setdefault((r.employee_id, r_date), []).append(r)

    weekly_attendance = []
    monthly_attendance = []
    for person in sorted(weekly_attendance_people.values(), key=lambda item: (item["role"] or "", item["name"] or "")):
        employee = person["employee"]
        day_statuses = []
        for day in week_days:
            rows = attendance_by_employee_day.get((employee.id, day), []) if employee else []
            if any(r.check_out is None for r in rows): status = "active"
            elif rows: status = "present"
            else: status = "absent"
            day_statuses.append(status)
        weekly_attendance.append({
            "id": person["id"], "name": person["name"], "role": person["role"],
            "days": day_statuses,
            "present_days": len([s for s in day_statuses if s in {"present", "active"}]),
            "active_today": day_statuses[today.weekday()] == "active"
        })
        month_statuses = []
        for day in month_days:
            rows = [r for r in attendance_rows if employee and r.employee_id == employee.id and local_date(r.check_in, tz) == day]
            if any(r.check_out is None for r in rows): status = "active"
            elif rows: status = "present"
            else: status = "absent"
            month_statuses.append(status)
        present_days = len([s for s in month_statuses if s in {"present", "active"}])
        total_days = len(month_days)
        monthly_attendance.append({
            "id": person["id"], "name": person["name"], "role": person["role"],
            "present_days": present_days, "absent_days": total_days - present_days,
            "total_days": total_days,
            "attendance_percent": round((present_days / total_days) * 100, 1) if total_days else 0,
            "active_today": month_statuses[-1] == "active" if month_statuses else False
        })

    import calendar
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day
    notifications = []
    if pending_discount_count:
        notifications.append({
            "type": "warning",
            "message": f"{int(pending_discount_count)} discount approval request{'s' if int(pending_discount_count) != 1 else ''} pending.",
        })
    if days_left <= 3 and len(pending_payrolls) > 0:
        notifications.append({
            "type": "warning",
            "message": f"Month end approaches. You have {len(pending_payrolls)} pending payroll records to finalize and pay.",
        })

    return {
        "today_sales": f"{sum((money(o.total) for o in completed_today), Decimal('0.00')):.2f}",
        "today_collection": f"{sum((money(o.total) for o in completed_today), Decimal('0.00')):.2f}",
        "revenue": f"{sum((money(o.total) for o in completed_orders), Decimal('0.00')):.2f}",
        "last_month_sales": f"{sum((money(o.total) for o in last_month_orders), Decimal('0.00')):.2f}",
        "today_orders": len(orders_today),
        "total_orders": len(orders),
        "completed_orders": len(completed_orders),
        "pending_orders": len(pending_orders),
        "active_orders": len(active_orders),
        "active_tables": table_counts.get("occupied", 0),
        "available_tables": table_counts.get("available", 0),
        "occupied_tables": table_counts.get("occupied", 0),
        "reserved_tables": table_counts.get("reserved", 0),
        "cleaning_tables": table_counts.get("cleaning", 0),
        "active_staff": len(active_staff),
        "active_staff_details": active_staff_details,
        "attendance_today": len(attendance_today),
        "low_stock_alerts": len(low_stock),
        "total_stock_items": len(inventory_items),
        "purchase_orders_today": len(purchase_orders_today),
        "purchase_orders_month": len(purchase_orders_month),
        "pending_discount_requests": int(pending_discount_count or 0),
        "pending_payroll_count": len(pending_payrolls),
        "notifications": notifications,
        "pending_payments": len([o for o in orders if o.payment_status in {"unpaid", "partial"}]),
        "top_selling_products": [{"name": name, "quantity": int(quantity or 0)} for name, quantity in item_rows],
        "sales_charts": {
            "daily": [round(float(daily_sales_by_date[d]), 2) for d in week_days],
            "daily_labels": [d.strftime("%a") for d in week_days],
            "monthly": [round(float(money(o.total)), 2) for o in completed_orders[-6:]],
            "last_month_sales": round(float(sum((money(o.total) for o in last_month_orders), Decimal("0.00"))), 2),
        },
        "weekly_attendance": {
            "labels": [d.strftime("%a") for d in week_days],
            "users": weekly_attendance,
        },
        "monthly_attendance": {
            "month": today.strftime("%b %Y"),
            "users": monthly_attendance,
        },
        "today_order_types": today_order_types,
        "order_status_counts": order_status_counts,
        "payment_method_totals": {method: f"{amount:.2f}" for method, amount in net_payment_methods.items() if amount > 0},
        "payment_gateway_totals": {provider: f"{amount:.2f}" for provider, amount in net_payment_gateways.items() if amount > 0},
        "payout_method_totals": {method: f"{amount:.2f}" for method, amount in payout_method_totals.items()},
        "payout_gateway_totals": {provider: f"{amount:.2f}" for provider, amount in payout_gateway_totals.items()},
    }
