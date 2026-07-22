from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest


def test_restaurant_can_complete_phase1_order_lifecycle(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={
            "name": "Indiranagar",
            "code": "BLR-IND",
            "address": "100 Feet Road",
            "phone": "+918888000001",
            "settings": {"receipt_footer": "Thank you"},
        },
    )
    assert branch.status_code == 201
    branch_id = branch.json()["id"]

    category = client.post(
        "/categories",
        headers=headers,
        json={"branch_id": branch_id, "name": "Mains"},
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    product = client.post(
        "/products",
        headers=headers,
        json={
            "branch_id": branch_id,
            "category_id": category_id,
            "name": "Paneer Tikka Bowl",
            "sku": "PTB-001",
            "price": "240.00",
            "tax_rate": "5.00",
            "variants": [{"name": "Large", "price_delta": "40.00"}],
            "addons": [{"name": "Extra Chutney", "price": "20.00"}],
            "image_url": "https://example.test/paneer.jpg",
            "available": True,
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    table = client.post(
        "/tables",
        headers=headers,
        json={"branch_id": branch_id, "name": "T1", "capacity": 4, "status": "available"},
    )
    assert table.status_code == 201
    table_id = table.json()["id"]

    inventory = client.post(
        "/inventory/items",
        headers=headers,
        json={
            "branch_id": branch_id,
            "name": "Paneer",
            "unit": "kg",
            "quantity": "4.00",
            "low_stock_threshold": "5.00",
            "supplier_name": "Fresh Dairy Co",
        },
    )
    assert inventory.status_code == 201
    inventory_data = inventory.json()
    assert inventory_data["low_stock"] is True
    inventory_id = inventory_data["id"]

    # 1. Test Stock Adjustment (Valid)
    adjust = client.post(
        f"/inventory/items/{inventory_id}/adjust",
        headers=headers,
        json={"quantity": "2.00", "notes": "found extra box"},
    )
    assert adjust.status_code == 200
    assert Decimal(adjust.json()["quantity"]) == Decimal("6.00")

    # 2. Test Stock Adjustment (Invalid Negative Stock)
    adjust_neg = client.post(
        f"/inventory/items/{inventory_id}/adjust",
        headers=headers,
        json={"quantity": "-10.00", "notes": "wasted"},
    )
    assert adjust_neg.status_code == 400
    assert "Insufficient stock" in adjust_neg.json()["detail"]

    # 3. Test Purchase Order Creation
    po = client.post(
        "/inventory/purchase-orders",
        headers=headers,
        json={
            "branch_id": branch_id,
            "supplier_name": "Fresh Dairy Co",
            "items": [
                {"name": "Paneer", "quantity": 10, "unit": "kg", "unit_cost": "200.00"}
            ],
        },
    )
    assert po.status_code == 201
    assert po.json()["status"] == "completed"

    # Verify inventory was updated by PO
    inventory_check = client.get(
        f"/reports/inventory?branch_id={branch_id}",
        headers=headers
    )
    assert inventory_check.status_code == 200
    paneer_item = next(item for item in inventory_check.json()["items"] if item["name"] == "Paneer")
    assert Decimal(paneer_item["quantity"]) == Decimal("16.00")

    recipe = client.put(
        f"/products/{product_id}/recipe",
        headers=headers,
        json={
            "items": [
                {
                    "inventory_item_id": inventory_id,
                    "quantity_per_unit": "0.50",
                    "wastage_percent": "0.00",
                }
            ]
        },
    )
    assert recipe.status_code == 200
    assert recipe.json()["items"][0]["inventory_item_id"] == inventory_id

    # Create Order Flow
    order = client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": branch_id,
            "table_id": table_id,
            "customer": {"name": "Ravi", "phone": "+917777000001"},
            "order_type": "dine_in",
            "discount_amount": "10.00",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 2,
                    "variant_name": "Large",
                    "addons": [{"name": "Extra Chutney", "price": "20.00"}],
                    "notes": "Less spicy",
                }
            ],
        },
    )
    assert order.status_code == 201
    order_data = order.json()
    assert order_data["status"] == "held"
    assert Decimal(order_data["total"]) == Decimal("620.00")

    sent = client.post(f"/orders/{order_data['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200
    assert sent.json()["kds_status"] == "new"

    inventory_after_kds = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers)
    paneer_after_kds = next(item for item in inventory_after_kds.json()["items"] if item["name"] == "Paneer")
    assert Decimal(paneer_after_kds["quantity"]) == Decimal("15.00")

    repeated_send = client.post(f"/orders/{order_data['id']}/send-to-kitchen", headers=headers)
    assert repeated_send.status_code == 200
    inventory_after_repeat = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers)
    paneer_after_repeat = next(item for item in inventory_after_repeat.json()["items"] if item["name"] == "Paneer")
    assert Decimal(paneer_after_repeat["quantity"]) == Decimal("15.00")

    ready = client.patch(
        f"/kds/orders/{order_data['id']}",
        headers=headers,
        json={"kds_status": "ready"},
    )
    assert ready.status_code == 200
    assert ready.json()["kds_status"] == "ready"

    payment = client.post(
        f"/orders/{order_data['id']}/payments",
        headers=headers,
        json={
            "payments": [
                {"method": "cash", "amount": "300.00"},
                {"method": "upi", "amount": "320.00", "reference": "upi-123"},
            ]
        },
    )
    assert payment.status_code == 201
    paid = payment.json()
    assert paid["payment_status"] == "paid"
    assert paid["status"] == "completed"

    receipt = client.get(f"/orders/{order_data['id']}/receipt", headers=headers)
    assert receipt.status_code == 200
    assert "Paneer Tikka Bowl" in receipt.text

    dashboard = client.get(f"/reports/dashboard?branch_id={branch_id}", headers=headers)
    assert dashboard.status_code == 200
    metrics = dashboard.json()
    assert metrics["today_sales"] == "620.00"
    assert metrics["active_orders"] == 0
    assert metrics["low_stock_alerts"] == 0  # Paneer has 15 kg now (threshold is 5)

    manager_dashboard = client.get(f"/reports/manager-dashboard?branch_id={branch_id}", headers=headers)
    assert manager_dashboard.status_code == 200
    manager_metrics = manager_dashboard.json()
    assert manager_metrics["today_sales"] == "620.00"
    assert manager_metrics["today_collection"] == "620.00"
    assert manager_metrics["today_orders"] == 1
    assert manager_metrics["total_orders"] == 1
    assert manager_metrics["completed_orders"] == 1
    assert manager_metrics["pending_orders"] == 0
    assert manager_metrics["active_tables"] == 0
    assert manager_metrics["available_tables"] == 1
    assert manager_metrics["active_staff_details"] == []
    assert manager_metrics["total_stock_items"] == 1
    assert manager_metrics["low_stock_alerts"] == 0
    assert manager_metrics["purchase_orders_today"] == 1
    assert manager_metrics["pending_discount_requests"] == 0
    assert manager_metrics["today_order_types"]["dine_in"]["orders"] == 1
    assert manager_metrics["today_order_types"]["dine_in"]["sales"] == "620.00"
    assert len(manager_metrics["sales_charts"]["daily"]) == 7
    assert manager_metrics["sales_charts"]["daily_labels"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert "hourly" not in manager_metrics["sales_charts"]
    assert manager_metrics["last_month_sales"] == "0.00"
    assert "cash" in manager_metrics["payment_method_totals"]
    assert "upi" in manager_metrics["payment_method_totals"]

    # 4. Test Reporting & Exports
    sales_rep = client.get(f"/reports/sales?branch_id={branch_id}&period=monthly", headers=headers)
    assert sales_rep.status_code == 200
    assert sales_rep.json()["period"] == "monthly"

    inv_rep = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers)
    assert inv_rep.status_code == 200
    assert len(inv_rep.json()["items"]) >= 1

    export_sales = client.get(f"/reports/sales/export?branch_id={branch_id}&format=csv", headers=headers)
    assert export_sales.status_code == 200
    assert "Today's Sales" in export_sales.text

    export_inv = client.get(f"/reports/inventory/export?branch_id={branch_id}&format=excel", headers=headers)
    assert export_inv.status_code == 200
    assert "<table>" in export_inv.text

    audits = client.get("/audit-logs", headers=headers)
    assert audits.status_code == 200
    actions = {entry["action"] for entry in audits.json()["items"]}
    assert {"tenant.registered", "order.created", "order.paid"}.issubset(actions)


def test_super_admin_can_accept_kds_order_from_api_v1(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "KDS Branch", "code": "KDS"},
    ).json()
    category = client.post(
        "/categories",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Kitchen"},
    ).json()
    product = client.post(
        "/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "category_id": category["id"],
            "name": "Kitchen Ticket",
            "price": "100.00",
            "tax_rate": "0.00",
        },
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    ).json()
    sent = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200

    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, owner_auth["user_id"])
        user.role = "super_admin"
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    super_admin_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    accepted = client.patch(
        f"/api/v1/kds/orders/{order['id']}",
        headers=super_admin_headers,
        json={"kds_status": "accepted"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["data"]["kds_status"] == "accepted"


def test_api_v1_kds_orders_lists_incoming_kitchen_tickets(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "KDS Incoming", "code": "KDS-IN"}).json()
    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Incoming KDS Item", "price": "100.00", "tax_rate": "0.00"},
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()
    sent = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200

    response = client.get(f"/api/v1/kds/orders?branch_id={branch['id']}", headers=headers)

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [order["id"]]
    assert items[0]["kds_status"] == "new"
    assert items[0]["items"][0]["name"] == "Incoming KDS Item"


def test_recipe_inventory_blocks_and_reverses_order_fulfillment(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post("/branches", headers=headers, json={"name": "Jayanagar", "code": "BLR-JAY"}).json()
    branch_id = branch["id"]
    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch_id, "name": "Masala Dosa", "price": "120.00", "tax_rate": "0.00"},
    ).json()
    batter = client.post(
        "/inventory/items",
        headers=headers,
        json={
            "branch_id": branch_id,
            "name": "Dosa Batter",
            "unit": "kg",
            "quantity": "1.00",
            "low_stock_threshold": "0.50",
        },
    ).json()

    recipe = client.put(
        f"/products/{product['id']}/recipe",
        headers=headers,
        json={"items": [{"inventory_item_id": batter["id"], "quantity_per_unit": "0.75"}]},
    )
    assert recipe.status_code == 200

    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch_id, "items": [{"product_id": product["id"], "quantity": 2}]},
    ).json()

    blocked = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert blocked.status_code == 400
    assert "Insufficient stock" in blocked.json()["detail"]

    adjust = client.post(
        f"/inventory/items/{batter['id']}/adjust",
        headers=headers,
        json={"quantity": "1.00", "notes": "prep batch completed"},
    )
    assert adjust.status_code == 200

    sent = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200
    stock_after_send = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers).json()["items"][0]
    assert Decimal(stock_after_send["quantity"]) == Decimal("0.50")

    repeated_send = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert repeated_send.status_code == 200
    stock_after_repeat = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers).json()["items"][0]
    assert Decimal(stock_after_repeat["quantity"]) == Decimal("0.50")

    cancelled = client.patch(f"/orders/{order['id']}", headers=headers, json={"status": "cancelled"})
    assert cancelled.status_code == 200
    stock_after_cancel = client.get(f"/reports/inventory?branch_id={branch_id}", headers=headers).json()["items"][0]
    assert Decimal(stock_after_cancel["quantity"]) == Decimal("2.00")


def test_inventory_delete_hides_item_without_removing_stock_history(client, owner_auth):
    from app.database import SessionLocal
    from app.models import InventoryItem, StockMovement

    headers = owner_auth["headers"]

    branch = client.post("/branches", headers=headers, json={"name": "HSR", "code": "BLR-HSR"}).json()
    item = client.post(
        "/inventory/items",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Tomato",
            "unit": "kg",
            "quantity": "5.00",
            "low_stock_threshold": "1.00",
        },
    ).json()

    adjusted = client.post(
        f"/inventory/items/{item['id']}/adjust",
        headers=headers,
        json={"quantity": "1.00", "notes": "opening correction"},
    )
    assert adjusted.status_code == 200

    deleted = client.delete(f"/inventory/items/{item['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True

    inventory = client.get(f"/inventory/items?branch_id={branch['id']}", headers=headers)
    assert inventory.status_code == 200
    assert item["id"] not in {row["id"] for row in inventory.json()["items"]}

    with SessionLocal() as db:
        stored_item = db.get(InventoryItem, item["id"])
        assert stored_item is not None
        assert stored_item.active is False
        movement_count = db.query(StockMovement).filter(StockMovement.inventory_item_id == item["id"]).count()
        assert movement_count == 1


def test_manager_dashboard_uses_branch_business_timezone_for_today(client, owner_auth, monkeypatch):
    from app import services
    from app.database import SessionLocal
    from app.models import Order

    class FrozenServerNow:
        def __init__(self, value):
            self.value = value

        def astimezone(self, tz=None):
            return self.value.astimezone(tz) if tz else self.value

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            current_utc = datetime(2026, 7, 7, 19, 0, tzinfo=UTC)
            return current_utc.astimezone(tz) if tz else FrozenServerNow(current_utc)

    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={
            "name": "Koramangala",
            "code": "BLR-KOR",
            "settings": {"timezone": "Asia/Kolkata"},
        },
    )
    assert branch.status_code == 201
    branch_id = branch.json()["id"]

    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch_id, "name": "Idli Plate", "price": "100.00", "tax_rate": "0.00"},
    )
    assert product.status_code == 201

    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch_id, "items": [{"product_id": product.json()["id"], "quantity": 1}]},
    )
    assert order.status_code == 201
    order_id = order.json()["id"]

    payment = client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"payments": [{"method": "cash", "amount": "100.00"}]},
    )
    assert payment.status_code == 201

    with SessionLocal() as db:
        db_order = db.get(Order, order_id)
        db_order.created_at = datetime(2026, 7, 7, 18, 0, tzinfo=UTC)
        db_order.updated_at = db_order.created_at
        db.commit()

    monkeypatch.setattr(services, "datetime", FrozenDateTime)

    manager_dashboard = client.get(f"/reports/manager-dashboard?branch_id={branch_id}", headers=headers)
    assert manager_dashboard.status_code == 200
    manager_metrics = manager_dashboard.json()
    assert manager_metrics["today_sales"] == "0.00"
    assert manager_metrics["today_collection"] == "0.00"
    assert manager_metrics["today_orders"] == 0
    assert manager_metrics["today_order_types"]["dine_in"]["orders"] == 0
    assert manager_metrics["today_order_types"]["dine_in"]["sales"] == "0.00"


def test_business_timezone_defaults_to_system_timezone(client, owner_auth, monkeypatch):
    from datetime import timezone, timedelta

    from app import services
    from app.database import SessionLocal

    system_tz = timezone(timedelta(hours=3), "System Local")
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "No Timezone Branch", "code": "NO-TZ"},
    )
    assert branch.status_code == 201
    branch_id = branch.json()["id"]

    monkeypatch.delenv("BUSINESS_TIMEZONE", raising=False)
    monkeypatch.setattr(services, "_system_timezone", lambda: system_tz)

    with SessionLocal() as db:
        assert services.business_timezone(db, owner_auth["tenant_id"], branch_id) is system_tz


def test_rbac_blocks_kitchen_staff_from_super_admin_tenant_actions(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Whitefield", "code": "BLR-WF", "address": "Main Road"},
    ).json()

    staff = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Kitchen User",
            "email": "kitchen@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "kitchen_staff",
        },
    )
    assert staff.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "kitchen@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = client.post(
        "/admin/tenants",
        headers=staff_headers,
        json={"name": "Blocked Tenant", "subscription_plan": "trial"},
    )
    assert denied.status_code == 403


def test_manager_can_manage_operational_users_and_branch_status(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "MG Road", "code": "BLR-MG", "address": "Metro Station Road"},
    ).json()

    manager = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Ops Manager",
            "email": "manager@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "manager",
        },
    )
    assert manager.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "manager@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    cashier = client.post(
        "/users",
        headers=manager_headers,
        json={
            "branch_id": branch["id"],
            "name": "Front Cashier",
            "email": "cashier@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "cashier",
        },
    )
    assert cashier.status_code == 201
    cashier_id = cashier.json()["id"]

    peer_manager = client.post(
        "/users",
        headers=manager_headers,
        json={
            "branch_id": branch["id"],
            "name": "Peer Manager",
            "email": "peer.manager@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "manager",
        },
    )
    assert peer_manager.status_code == 403

    protected = client.post(
        "/users",
        headers=manager_headers,
        json={
            "branch_id": branch["id"],
            "name": "Protected Owner",
            "email": "protected@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "tenant_owner",
        },
    )
    assert protected.status_code == 403

    users = client.get("/users", headers=manager_headers)
    assert users.status_code == 200
    roles = {row["role"] for row in users.json()["items"]}
    assert "cashier" in roles
    assert "tenant_owner" not in roles

    disabled = client.patch(
        f"/users/{cashier_id}",
        headers=manager_headers,
        json={"status": "inactive", "phone": "+918888000002"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "inactive"

    relabelled = client.patch(
        f"/branches/{branch['id']}",
        headers=manager_headers,
        json={"name": "MG Road Flagship", "status": "inactive"},
    )
    assert relabelled.status_code == 200
    assert relabelled.json()["name"] == "MG Road Flagship"
    assert relabelled.json()["status"] == "inactive"


def test_role_permissions_can_be_saved_loaded_and_enforced(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Role Store", "code": "ROLE"},
    ).json()

    saved = client.patch(
        "/admin/permissions",
        headers=headers,
        json={
            "cashier": ["order:manage"],
            "waiter": ["order:manage"],
            "manager": ["user:manage", "branch:manage"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["role_permissions"]["cashier"] == ["order:manage"]

    loaded = client.get("/admin/permissions", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["role_permissions"]["cashier"] == ["order:manage"]

    cashier = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Limited Cashier",
            "email": "limited.cashier@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "cashier",
        },
    )
    assert cashier.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "limited.cashier@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    cashier_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = client.get(f"/reports/manager-dashboard?branch_id={branch['id']}", headers=cashier_headers)
    assert denied.status_code == 403


def test_user_management_permission_allows_user_delete_without_staff_permission(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "User Admin Store", "code": "USR-ADM"},
    ).json()

    client.patch(
        "/admin/permissions",
        headers=headers,
        json={"cashier": ["user:manage"]},
    )

    admin_user = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "User Admin Cashier",
            "email": "user.admin.cashier@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "cashier",
        },
    )
    assert admin_user.status_code == 201

    target = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Delete Target",
            "email": "delete.target@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "waiter",
        },
    )
    assert target.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "user.admin.cashier@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    user_admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    deleted = client.delete(f"/users/{target.json()['id']}", headers=user_admin_headers)
    assert deleted.status_code == 200

    users = client.get("/users", headers=headers)
    assert target.json()["id"] not in {row["id"] for row in users.json()["items"]}


def test_kds_updates_follow_saved_kds_manage_permission(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "KDS Permission Store", "code": "KDS-PERM"},
    ).json()
    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "KDS Test Idli", "price": "80.00", "tax_rate": "0.00"},
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "order_type": "takeaway",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    ).json()
    sent = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200

    kitchen_user = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "KDS Permission Staff",
            "email": "kds.permission@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "kitchen_staff",
        },
    )
    assert kitchen_user.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "kds.permission@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    kitchen_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    client.patch(
        "/admin/permissions",
        headers=headers,
        json={"kitchen_staff": ["kds:view"]},
    )
    denied = client.patch(
        f"/kds/orders/{order['id']}",
        headers=kitchen_headers,
        json={"kds_status": "accepted"},
    )
    assert denied.status_code == 403

    client.patch(
        "/admin/permissions",
        headers=headers,
        json={"kitchen_staff": ["kds:view", "kds:manage"]},
    )
    accepted = client.patch(
        f"/kds/orders/{order['id']}",
        headers=kitchen_headers,
        json={"kds_status": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["kds_status"] == "accepted"


def test_waiter_default_permissions_can_accept_visible_kds_order(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post("/branches", headers=headers, json={"name": "Waiter KDS Store", "code": "WT-KDS"}).json()
    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Waiter KDS Item", "price": "80.00", "tax_rate": "0.00"},
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()
    sent = client.post(f"/orders/{order['id']}/send-to-kitchen", headers=headers)
    assert sent.status_code == 200

    waiter_user = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Waiter KDS Staff",
            "email": "waiter.kds@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "waiter",
        },
    )
    assert waiter_user.status_code == 201
    login = client.post("/auth/login", json={"email": "waiter.kds@saffron.example.com", "password": "ChangeMe123!"})
    assert login.status_code == 200
    waiter_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    visible = client.get(f"/api/v1/kds/orders?branch_id={branch['id']}", headers=waiter_headers)
    assert visible.status_code == 200
    assert visible.json()["data"]["items"][0]["id"] == order["id"]

    accepted = client.patch(
        f"/api/v1/kds/orders/{order['id']}",
        headers=waiter_headers,
        json={"kds_status": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["kds_status"] == "accepted"


def test_delete_store_hides_it_from_store_management_without_hiding_disabled_stores(client, owner_auth):
    headers = owner_auth["headers"]

    main = client.post("/branches", headers=headers, json={"name": "Main Store", "code": "MAIN"}).json()
    disabled_store = client.post("/branches", headers=headers, json={"name": "Disabled Store", "code": "DIS"}).json()
    deleted_store = client.post("/branches", headers=headers, json={"name": "Deleted Store", "code": "DEL"}).json()

    disabled = client.patch(f"/branches/{disabled_store['id']}", headers=headers, json={"status": "inactive"})
    assert disabled.status_code == 200

    deleted = client.delete(f"/branches/{deleted_store['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True

    stores = client.get("/branches", headers=headers)
    assert stores.status_code == 200
    store_ids = {store["id"] for store in stores.json()["items"]}
    assert main["id"] in store_ids
    assert disabled_store["id"] in store_ids
    assert deleted_store["id"] not in store_ids

    disabled_row = next(store for store in stores.json()["items"] if store["id"] == disabled_store["id"])
    assert disabled_row["status"] == "inactive"

    delete_disabled = client.delete(f"/branches/{disabled_store['id']}", headers=headers)
    assert delete_disabled.status_code == 200
    stores_after_disabled_delete = client.get("/branches", headers=headers)
    assert disabled_store["id"] not in {store["id"] for store in stores_after_disabled_delete.json()["items"]}


def test_manager_can_add_waiter_staff_member(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Richmond Road", "code": "BLR-RCH", "address": "Main Road"},
    ).json()

    manager = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Floor Manager",
            "email": "floor.manager@saffron.example.com",
            "password": "ChangeMe123!",
            "role": "manager",
        },
    )
    assert manager.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "floor.manager@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    employee = client.post(
        "/employees",
        headers=manager_headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-WAIT-01",
            "name": "Service Waiter",
            "email": "service.waiter@saffron.example.com",
            "phone": "+918888000003",
            "role": "waiter",
            "base_salary": 12000,
        },
    )
    assert employee.status_code == 201
    assert employee.json()["role"] == "waiter"


def test_payroll_uses_day_salary_and_approved_leave(client, owner_auth):
    from app.database import SessionLocal
    from app.models import Attendance

    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Lavelle Road", "code": "BLR-LVL", "address": "Main Road"},
    ).json()

    employee = client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-DAY-01",
            "name": "Daily Staff",
            "email": "daily.staff@saffron.example.com",
            "role": "cashier",
            "base_salary": 500,
        },
    )
    assert employee.status_code == 201
    employee_id = employee.json()["id"]

    today = datetime.now(UTC).date()
    present_day = today.replace(day=1)
    leave_day = present_day + timedelta(days=1)

    attendance = client.post(
        "/attendance/check-in",
        headers=headers,
        json={"employee_id": employee_id, "shift_type": "General"},
    )
    assert attendance.status_code == 200
    with SessionLocal() as db:
        row = db.get(Attendance, attendance.json()["id"])
        row.check_in = datetime.combine(present_day, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        row.check_out = datetime.combine(present_day, datetime.min.time(), tzinfo=UTC).replace(hour=18)
        db.commit()

    leave = client.post(
        "/leaves",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": employee_id,
            "type": "sick",
            "start_date": leave_day.isoformat(),
            "end_date": leave_day.isoformat(),
            "reason": "Approved sick leave",
        },
    )
    assert leave.status_code == 201

    approved = client.patch(
        f"/leaves/{leave.json()['id']}",
        headers=headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200

    payroll = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    assert payroll.status_code == 200
    row = payroll.json()["items"][0]
    assert row["day_salary"] == "500.00"
    assert row["present_days"] == 1
    assert row["approved_leave_days"] == 1
    assert row["payable_days"] == 2
    assert row["net_salary"] == "1000.00"


def test_clock_in_populates_live_payroll_salary(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "St Marks Road", "code": "BLR-STK", "address": "Main Road"},
    ).json()

    employee = client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-LIVE-01",
            "name": "Live Payroll Staff",
            "email": "live.payroll@saffron.example.com",
            "role": "cashier",
            "base_salary": 650,
        },
    ).json()

    before = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    assert before.status_code == 200
    assert before.json()["items"][0]["net_salary"] == "0.00"

    clock_in = client.post(
        "/attendance/check-in",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_in.status_code == 200

    after = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    assert after.status_code == 200
    row = after.json()["items"][0]
    assert row["present_days"] == 1
    assert row["payable_days"] == 1
    assert row["net_salary"] == "650.00"


def test_add_staff_with_password_creates_login_and_delete_user_removes_staff(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "MG Road", "code": "BLR-MG", "address": "Main Road"},
    ).json()

    employee = client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-LOGIN-01",
            "name": "Login Cashier",
            "email": "login.cashier@saffron.example.com",
            "phone": "+918888000004",
            "role": "cashier",
            "base_salary": 600,
            "password": "CashierPass123!",
        },
    )
    assert employee.status_code == 201
    created = employee.json()
    assert created["user_id"]

    login = client.post(
        "/auth/login",
        json={"email": "login.cashier@saffron.example.com", "password": "CashierPass123!"},
    )
    assert login.status_code == 200

    directory = client.get(f"/employees?branch_id={branch['id']}", headers=headers)
    assert directory.status_code == 200
    staff_row = next(item for item in directory.json()["items"] if item["employee_id"] == "EMP-LOGIN-01")
    assert staff_row["user_id"] == created["user_id"]

    deleted = client.delete(f"/users/{created['user_id']}", headers=headers)
    assert deleted.status_code == 200

    directory_after_delete = client.get(f"/employees?branch_id={branch['id']}", headers=headers)
    assert directory_after_delete.status_code == 200
    assert all(item["employee_id"] != "EMP-LOGIN-01" for item in directory_after_delete.json()["items"])


def test_current_attendance_lists_all_staff_with_clock_state(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Church Street", "code": "BLR-CHR", "address": "Main Road"},
    ).json()

    first = client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-CUR-01",
            "name": "Current Cashier",
            "email": "current.cashier@saffron.example.com",
            "role": "cashier",
            "base_salary": 500,
        },
    ).json()
    client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-CUR-02",
            "name": "Current Waiter",
            "email": "current.waiter@saffron.example.com",
            "role": "waiter",
            "base_salary": 450,
        },
    )

    empty = client.get(f"/reports/attendance/current?branch_id={branch['id']}", headers=headers)
    assert empty.status_code == 200
    assert len(empty.json()["items"]) == 2
    assert {row["status"] for row in empty.json()["items"]} == {"not_started"}

    clock_in = client.post(
        "/attendance/check-in",
        headers=headers,
        json={"employee_id": first["id"], "shift_type": "General"},
    )
    assert clock_in.status_code == 200

    current = client.get(f"/reports/attendance/current?branch_id={branch['id']}", headers=headers)
    assert current.status_code == 200
    rows = {row["employee_id"]: row for row in current.json()["items"]}
    assert rows["EMP-CUR-01"]["status"] == "clocked_in"
    assert rows["EMP-CUR-01"]["check_in"]
    assert rows["EMP-CUR-01"]["check_out"] is None
    assert rows["EMP-CUR-02"]["status"] == "not_started"


def test_staff_edit_incentive_payout_and_payroll_delete_flow(client, owner_auth):
    headers = owner_auth["headers"]

    branch = client.post(
        "/branches",
        headers=headers,
        json={"name": "Residency Road", "code": "BLR-RES", "address": "Main Road"},
    ).json()

    employee = client.post(
        "/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-PAY-01",
            "name": "Payroll Staff",
            "email": "payroll.staff@saffron.example.com",
            "phone": "+918888000005",
            "role": "cashier",
            "base_salary": 500,
        },
    ).json()

    edited = client.patch(
        f"/employees/{employee['id']}",
        headers=headers,
        json={"name": "Payroll Lead", "phone": "+918888000006", "role": "waiter", "base_salary": 700},
    )
    assert edited.status_code == 200

    directory = client.get(f"/employees?branch_id={branch['id']}", headers=headers)
    staff_row = next(item for item in directory.json()["items"] if item["id"] == employee["id"])
    assert staff_row["name"] == "Payroll Lead"
    assert staff_row["phone"] == "+918888000006"
    assert staff_row["role"] == "waiter"

    payroll = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    payroll_row = payroll.json()["items"][0]
    assert payroll_row["day_salary"] == "700.00"

    incentive = client.post(
        "/incentives",
        headers=headers,
        json={"branch_id": branch["id"], "employee_id": employee["id"], "sales_amount": "0.00", "incentive_amount": "250.00"},
    )
    assert incentive.status_code == 200
    assert incentive.json()["count"] == 1

    incentive_report = client.get(f"/reports/incentives?branch_id={branch['id']}", headers=headers)
    assert incentive_report.status_code == 200
    incentive_row = incentive_report.json()["items"][0]
    assert incentive_row["id"]
    assert incentive_row["employee_record_id"] == employee["id"]

    payroll_with_incentive = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    payroll_row = payroll_with_incentive.json()["items"][0]
    assert payroll_row["incentives"] == "250.00"
    assert payroll_row["net_salary"] == "250.00"

    payout = client.post(f"/incentives/{incentive_row['id']}/payout", headers=headers)
    assert payout.status_code == 200

    after_payout = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    paid_row = after_payout.json()["items"][0]
    assert paid_row["incentives"] == "250.00"
    assert paid_row["net_salary"] == "250.00"

    delete_payroll = client.delete(f"/payroll/{paid_row['id']}", headers=headers)
    assert delete_payroll.status_code == 200
    after_delete = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    # Since the employee is active, deleting their payroll record will trigger auto-generation of a new one
    # with default values (0 base_salary) on the next payroll report fetch.
    auto_generated_payroll = after_delete.json()["items"]
    assert len(auto_generated_payroll) == 1
    assert auto_generated_payroll[0]["base_salary"] == "0.00"

    clock_in = client.post(
        "/attendance/check-in",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_in.status_code == 200

    clock_out = client.post(
        "/attendance/check-out",
        headers=headers,
        json={"employee_id": employee["id"]},
    )
    assert clock_out.status_code == 200

    leave = client.post(
        "/leaves",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": employee["id"],
            "type": "sick",
            "start_date": "2026-07-08",
            "end_date": "2026-07-08",
            "reason": "Fever",
        },
    )
    assert leave.status_code == 201

    delete_employee = client.delete(f"/employees/{employee['id']}", headers=headers)
    assert delete_employee.status_code == 200

    directory_after_employee_delete = client.get(f"/employees?branch_id={branch['id']}", headers=headers)
    assert employee["id"] not in {row["id"] for row in directory_after_employee_delete.json()["items"]}

    payroll_after_employee_delete = client.get(f"/reports/payroll?branch_id={branch['id']}", headers=headers)
    assert payroll_after_employee_delete.json()["items"] == []

    incentives_after_employee_delete = client.get(f"/reports/incentives?branch_id={branch['id']}", headers=headers)
    assert incentives_after_employee_delete.json()["items"] == []
