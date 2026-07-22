import hmac
import hashlib
import json
from datetime import UTC, datetime, timedelta


def test_receipt_rows_fit_thermal_print_width():
    from app.main import (
        RECEIPT_WIDTH,
        receipt_center,
        receipt_item_lines,
        receipt_kv,
        receipt_rule,
    )

    assert RECEIPT_WIDTH == 42

    rows = [
        receipt_center("Very Long Restaurant Name Gajuwaka Branch"),
        receipt_rule(),
        f"{'Item':<21}{'Qty':>4}{'Rate':>8}{'Amt':>9}",
        *receipt_item_lines(
            "Extra Large Paneer Tikka Bowl With Chutney",
            12,
            "1234.50",
            "14814.00",
        ),
        receipt_kv("Grand Total", "14814.00"),
    ]

    assert all(len(row) <= RECEIPT_WIDTH for row in rows)
    assert rows[2] == "Item                  Qty    Rate      Amt"
    assert rows[3].endswith("  12 1234.50 14814.00")
    assert rows[-1].endswith("          14814.00")


def test_delivery_provider_body_code_detects_errors_without_false_positives():
    from app.main import provider_failure_message

    assert provider_failure_message({"code": 400, "message": "outlet is offline"}) == "outlet is offline"
    assert provider_failure_message({"code": "503", "error": "provider unavailable"}) == "provider unavailable"
    assert provider_failure_message({"code": 200, "status": "success"}) is None


def test_razorpay_refund_idempotency_changes_only_after_a_confirmed_failure():
    from app.main import razorpay_refund_receipt

    first = razorpay_refund_receipt("payment-1", 10000, 0)
    network_retry = razorpay_refund_receipt("payment-1", 10000, 0)
    failed_retry = razorpay_refund_receipt("payment-1", 10000, 0, "rfnd_failed_1")

    assert first == network_retry
    assert failed_retry != first
    assert first.startswith("refund-")
    assert len(first) <= 80


def test_razorpay_captured_payment_validation_requires_amount_and_currency():
    from decimal import Decimal
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.main import validate_razorpay_payment_amount

    payment = SimpleNamespace(amount=Decimal("100.00"))
    for entity, expected_detail in [
        ({"currency": "INR"}, "Razorpay payment amount is missing"),
        ({"amount": 10000}, "Razorpay payment currency is missing"),
    ]:
        try:
            validate_razorpay_payment_amount(payment, entity)
        except HTTPException as exc:
            assert exc.status_code == 422
            assert exc.detail == expected_detail
        else:
            raise AssertionError("Incomplete captured payment data must be rejected")


def test_razorpay_payout_validation_requires_amount_and_currency():
    from decimal import Decimal
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.main import validate_razorpay_payout_amount

    payroll = SimpleNamespace(net_salary=Decimal("100.00"))
    for entity, expected_detail in [
        ({"currency": "INR"}, "Razorpay payout amount is missing"),
        ({"amount": 10000}, "Razorpay payout currency is missing"),
    ]:
        try:
            validate_razorpay_payout_amount(payroll, entity)
        except HTTPException as exc:
            assert exc.status_code == 422
            assert exc.detail == expected_detail
        else:
            raise AssertionError("Incomplete payout data must be rejected")


def test_api_v1_wraps_success_responses(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok"},
        "message": "",
        "errors": [],
    }


def test_ready_checks_database_through_api_v1(client):
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ready", "database": "ok"}


def test_refresh_token_rotation_revokes_previous_refresh_token(client, owner_auth):
    refresh = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "ChangeMe123!"},
    ).json()["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != refresh

    replay = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401


def test_password_reset_request_does_not_expose_token_by_default(client, owner_auth):
    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Password reset requested"
    assert "reset_token" not in response.json()


def test_integrations_status_reports_missing_configuration_without_secret_values(client, owner_auth, monkeypatch):
    for key in [
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "FRONTEND_RESET_URL",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_WEBHOOK_SECRET",
        "RAZORPAYX_KEY_ID",
        "RAZORPAYX_KEY_SECRET",
        "RAZORPAYX_ACCOUNT_NUMBER",
        "RAZORPAYX_WEBHOOK_SECRET",
        "SWIGGY_API_BASE_URL",
        "SWIGGY_API_TOKEN",
        "SWIGGY_OUTLET_ID",
        "SWIGGY_WEBHOOK_SECRET",
        "ZOMATO_API_BASE_URL",
        "ZOMATO_API_TOKEN",
        "ZOMATO_OUTLET_ID",
        "ZOMATO_WEBHOOK_SECRET",
    ]:
        monkeypatch.delenv(key, raising=False)

    response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["password_reset_mail"]["configured"] is False
    assert "SMTP_HOST" in payload["password_reset_mail"]["missing"]
    assert payload["razorpay"]["configured"] is False
    assert payload["razorpay"]["webhook_url"] == "/api/v1/integrations/razorpay/webhook"
    assert payload["razorpayx"]["configured"] is False
    assert "RAZORPAYX_WEBHOOK_SECRET" in payload["razorpayx"]["missing"]
    assert payload["razorpayx"]["webhook_url"] == "/api/v1/integrations/razorpayx/webhook"
    assert payload["swiggy"]["configured"] is False
    assert payload["swiggy"]["webhook_url"] == "/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch_id}"
    assert payload["zomato"]["configured"] is False
    assert "gmail-app-password" not in str(payload)
    assert "swiggy-token" not in str(payload)
    assert "zomato-token" not in str(payload)


def test_razorpay_dashboard_fetches_live_branch_scoped_provider_metrics(client, owner_auth, monkeypatch):
    from app import database
    from app.models import Employee, Payment, Payroll, Refund

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_secret")
    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_live_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_live_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")

    headers = owner_auth["headers"]

    def create_branch_order(name, code):
        branch = client.post(
            "/api/v1/branches",
            headers=headers,
            json={"name": name, "code": code},
        ).json()["data"]
        product = client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "branch_id": branch["id"],
                "name": f"{name} Meal",
                "price": "100.00",
                "tax_rate": "0.00",
            },
        ).json()["data"]
        order = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
        ).json()["data"]
        return branch, order

    branch, order = create_branch_order("Provider Branch", "PVB")
    other_branch, other_order = create_branch_order("Other Provider Branch", "OPB")

    with database.SessionLocal() as db:
        payment = Payment(
            order_id=order["id"],
            method="razorpay",
            amount="100.00",
            status="captured",
            provider="razorpay",
            gateway_order_id="order_branch",
            gateway_payment_id="pay_branch",
        )
        other_payment = Payment(
            order_id=other_order["id"],
            method="razorpay",
            amount="900.00",
            status="captured",
            provider="razorpay",
            gateway_order_id="order_other",
            gateway_payment_id="pay_other",
        )
        db.add_all([payment, other_payment])
        db.flush()
        db.add_all([
            Refund(
                tenant_id=owner_auth["tenant_id"],
                branch_id=branch["id"],
                order_id=order["id"],
                payment_id=payment.id,
                provider="razorpay",
                gateway_refund_id="rfnd_branch",
                amount="20.00",
                currency="INR",
                status="processed",
                receipt="refund-branch",
            ),
            Refund(
                tenant_id=owner_auth["tenant_id"],
                branch_id=other_branch["id"],
                order_id=other_order["id"],
                payment_id=other_payment.id,
                provider="razorpay",
                gateway_refund_id="rfnd_other",
                amount="100.00",
                currency="INR",
                status="processed",
                receipt="refund-other",
            ),
        ])
        employee = Employee(
            tenant_id=owner_auth["tenant_id"],
            branch_id=branch["id"],
            employee_id="EMP-PROVIDER-1",
            name="Provider Staff",
            email="provider.staff@example.com",
            role="cashier",
        )
        other_employee = Employee(
            tenant_id=owner_auth["tenant_id"],
            branch_id=other_branch["id"],
            employee_id="EMP-PROVIDER-2",
            name="Other Provider Staff",
            email="other.provider.staff@example.com",
            role="cashier",
        )
        db.add_all([employee, other_employee])
        db.flush()
        db.add_all([
            Payroll(
                tenant_id=owner_auth["tenant_id"],
                branch_id=branch["id"],
                employee_id=employee.id,
                salary_period="2026-07",
                base_salary="30.00",
                net_salary="30.00",
                status="paid",
                payout_provider="razorpayx",
                payout_id="pout_branch",
                payout_status="processed",
            ),
            Payroll(
                tenant_id=owner_auth["tenant_id"],
                branch_id=other_branch["id"],
                employee_id=other_employee.id,
                salary_period="2026-07",
                base_salary="500.00",
                net_salary="500.00",
                status="paid",
                payout_provider="razorpayx",
                payout_id="pout_other",
                payout_status="processed",
            ),
        ])
        db.commit()

    provider_calls = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_request(method, url, **kwargs):
        provider_calls.append({"method": method, "url": url, **kwargs})
        assert method == "GET"
        assert kwargs["params"]["count"] == 100
        assert kwargs["params"]["skip"] == 0
        assert isinstance(kwargs["params"]["from"], int)
        assert isinstance(kwargs["params"]["to"], int)
        if url.endswith("/v1/payments"):
            assert kwargs["auth"] == ("rzp_live_key", "rzp_live_secret")
            return FakeResponse({
                "entity": "collection",
                "count": 2,
                "items": [
                    {
                        "id": "pay_branch",
                        "order_id": "order_branch",
                        "amount": 10000,
                        "amount_refunded": 2000,
                        "currency": "INR",
                        "status": "captured",
                        "captured": True,
                        "method": "upi",
                        "email": "must-not-reach-browser@example.com",
                        "contact": "+919999999999",
                        "created_at": 1784360000,
                    },
                    {
                        "id": "pay_other",
                        "order_id": "order_other",
                        "amount": 90000,
                        "amount_refunded": 10000,
                        "currency": "INR",
                        "status": "captured",
                        "captured": True,
                        "method": "card",
                        "created_at": 1784360001,
                    },
                ],
            })
        if url.endswith("/v1/refunds"):
            return FakeResponse({
                "entity": "collection",
                "count": 2,
                "items": [
                    {
                        "id": "rfnd_branch",
                        "payment_id": "pay_branch",
                        "amount": 2000,
                        "currency": "INR",
                        "status": "processed",
                        "created_at": 1784360100,
                    },
                    {
                        "id": "rfnd_other",
                        "payment_id": "pay_other",
                        "amount": 10000,
                        "currency": "INR",
                        "status": "processed",
                        "created_at": 1784360101,
                    },
                ],
            })
        if url.endswith("/v1/payouts"):
            assert kwargs["auth"] == ("rzpx_live_key", "rzpx_live_secret")
            assert kwargs["params"]["account_number"] == "2323230066666666"
            return FakeResponse({
                "entity": "collection",
                "count": 2,
                "items": [
                    {
                        "id": "pout_branch",
                        "amount": 3000,
                        "currency": "INR",
                        "status": "processed",
                        "mode": "UPI",
                        "purpose": "salary",
                        "utr": "UTR-BRANCH",
                        "fund_account_id": "fa_must_not_reach_browser",
                        "created_at": 1784360200,
                    },
                    {
                        "id": "pout_other",
                        "amount": 50000,
                        "currency": "INR",
                        "status": "processed",
                        "mode": "UPI",
                        "purpose": "salary",
                        "created_at": 1784360201,
                    },
                ],
            })
        raise AssertionError(f"Unexpected Razorpay URL: {url}")

    monkeypatch.setattr("httpx.request", fake_request)

    response = client.get(
        f"/api/v1/integrations/razorpay/dashboard?branch_id={branch['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "razorpay_api"
    assert payload["status"] == "live"
    assert payload["modes"] == {"payments": "live", "payouts": "live"}
    assert payload["payments"]["counts"]["captured"] == 1
    assert payload["payments"]["amounts"]["captured"] == "100.00"
    assert payload["refunds"]["counts"]["processed"] == 1
    assert payload["refunds"]["amounts"]["processed"] == "20.00"
    assert payload["payouts"]["counts"]["processed"] == 1
    assert payload["payouts"]["amounts"]["processed"] == "30.00"
    assert payload["totals"] == {
        "captured": "100.00",
        "refunded": "20.00",
        "payouts": "30.00",
        "net_flow": "50.00",
        "complete": True,
    }
    assert payload["payments"]["items"][0]["local_order_id"] == order["id"]
    assert payload["payouts"]["items"][0]["local_payroll_id"]
    serialized = json.dumps(payload)
    assert "must-not-reach-browser" not in serialized
    assert "2323230066666666" not in serialized
    assert "rzp_live_secret" not in serialized
    assert len(provider_calls) == 3


def test_razorpay_dashboard_keeps_payments_live_when_razorpayx_is_not_configured(
    client,
    owner_auth,
    monkeypatch,
):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_secret")
    monkeypatch.delenv("RAZORPAYX_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAYX_KEY_SECRET", raising=False)
    monkeypatch.delenv("RAZORPAYX_ACCOUNT_NUMBER", raising=False)

    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"entity": "collection", "count": 0, "items": []}

    provider_calls = []

    def fake_request(method, url, **kwargs):
        provider_calls.append(url)
        return FakeResponse()

    monkeypatch.setattr("httpx.request", fake_request)
    branch = client.post(
        "/api/v1/branches",
        headers=owner_auth["headers"],
        json={"name": "Partial Provider", "code": "PRP"},
    ).json()["data"]

    response = client.get(
        f"/api/v1/integrations/razorpay/dashboard?branch_id={branch['id']}",
        headers=owner_auth["headers"],
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "partial"
    assert payload["payments"]["status"] == "live"
    assert payload["refunds"]["status"] == "live"
    assert payload["payouts"]["status"] == "not_configured"
    assert payload["payouts"]["error"] == "RazorpayX account is not configured"
    assert payload["totals"]["complete"] is False
    assert payload["totals"]["net_flow"] is None
    assert provider_calls == [
        "https://api.razorpay.com/v1/payments",
        "https://api.razorpay.com/v1/refunds",
    ]


def test_razorpay_dashboard_degrades_malformed_provider_data_without_leaking_details(
    client,
    owner_auth,
    monkeypatch,
):
    from app import database
    from app.models import Payment

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret_value")
    monkeypatch.delenv("RAZORPAYX_ACCOUNT_NUMBER", raising=False)
    headers = owner_auth["headers"]
    branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={"name": "Malformed Provider", "code": "MFP"},
    ).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Malformed Provider Meal",
            "price": "100.00",
            "tax_rate": "0.00",
        },
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    with database.SessionLocal() as db:
        db.add(Payment(
            order_id=order["id"],
            method="razorpay",
            amount="100.00",
            status="captured",
            provider="razorpay",
            gateway_order_id="order_malformed",
            gateway_payment_id="pay_malformed",
        ))
        db.commit()

    class FakeResponse:
        status_code = 200
        text = "contains-provider-internal-detail"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_request(method, url, **kwargs):
        if url.endswith("/v1/payments"):
            return FakeResponse({
                "entity": "collection",
                "count": 1,
                "items": [{
                    "id": "pay_malformed",
                    "order_id": "order_malformed",
                    "amount": 10000,
                    "amount_refunded": "not-an-amount",
                    "currency": "INR",
                    "status": "captured",
                    "captured": True,
                }],
            })
        return FakeResponse({"entity": "collection", "count": 0, "items": []})

    monkeypatch.setattr("httpx.request", fake_request)

    response = client.get(
        f"/api/v1/integrations/razorpay/dashboard?branch_id={branch['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["modes"]["payments"] == "test"
    assert payload["payments"]["status"] == "unavailable"
    assert payload["payments"]["error"] == "Razorpay API is unavailable"
    serialized = json.dumps(payload)
    assert "not-an-amount" not in serialized
    assert "contains-provider-internal-detail" not in serialized
    assert "rzp_secret_value" not in serialized


def test_integrations_status_requires_separate_razorpayx_webhook_secret(client, owner_auth, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.pos.example.com")
    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_live_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_live_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "payment-webhook-secret")
    monkeypatch.delenv("RAZORPAYX_WEBHOOK_SECRET", raising=False)

    response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

    assert response.status_code == 200
    razorpayx = response.json()["data"]["razorpayx"]
    assert razorpayx["configured"] is False
    assert razorpayx["missing"] == ["RAZORPAYX_WEBHOOK_SECRET"]
    assert razorpayx["webhook_url"] == "https://api.pos.example.com/api/v1/integrations/razorpayx/webhook"


def test_integrations_status_requires_public_url_for_webhook_services(client, owner_auth, monkeypatch):
    monkeypatch.delenv("PUBLIC_API_BASE_URL", raising=False)
    monkeypatch.delenv("API_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_hook_secret")
    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_live_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_live_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "rzpx_hook_secret")
    for provider in ("SWIGGY", "ZOMATO"):
        monkeypatch.setenv(f"{provider}_API_BASE_URL", f"https://{provider.lower()}.partner.test")
        monkeypatch.setenv(f"{provider}_API_TOKEN", f"{provider.lower()}-token")
        monkeypatch.setenv(f"{provider}_OUTLET_ID", f"{provider.lower()}-outlet")
        monkeypatch.setenv(f"{provider}_WEBHOOK_SECRET", f"{provider.lower()}-hook-secret")

    response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

    assert response.status_code == 200
    payload = response.json()["data"]
    for service_name in ("razorpay", "razorpayx", "swiggy", "zomato"):
        assert payload[service_name]["configured"] is False
        assert "PUBLIC_API_BASE_URL" in payload[service_name]["missing"]


def test_integrations_status_rejects_non_public_webhook_base_urls(client, owner_auth, monkeypatch):
    monkeypatch.delenv("API_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_hook_secret")

    for invalid_url in (
        "http://localhost:8000",
        "https://127.0.0.1:8000",
        "https://10.0.0.25",
        "http://api.pos.example.com",
        "not-a-url",
    ):
        monkeypatch.setenv("PUBLIC_API_BASE_URL", invalid_url)
        response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

        assert response.status_code == 200
        razorpay = response.json()["data"]["razorpay"]
        assert razorpay["configured"] is False
        assert "PUBLIC_API_BASE_URL" in razorpay["missing"]
        assert razorpay["webhook_url"] == "/api/v1/integrations/razorpay/webhook"


def test_integrations_status_rejects_non_public_password_reset_urls(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "gmail-app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")

    for invalid_url in (
        "http://localhost:5173/reset-password",
        "https://127.0.0.1/reset-password",
        "https://10.0.0.25/reset-password",
        "http://pos.example.com/reset-password",
        "javascript:alert(1)",
    ):
        monkeypatch.setenv("FRONTEND_RESET_URL", invalid_url)
        response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

        assert response.status_code == 200
        mail = response.json()["data"]["password_reset_mail"]
        assert mail["configured"] is False
        assert mail["reset_url_configured"] is False
        assert "FRONTEND_RESET_URL" in mail["missing"]


def test_integrations_status_rejects_non_public_delivery_api_urls(client, owner_auth, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.pos.example.com")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "swiggy-hook-secret")

    for invalid_url in (
        "http://localhost:9000",
        "https://127.0.0.1",
        "https://10.0.0.25",
        "http://partner.swiggy.com",
        "not-a-url",
    ):
        monkeypatch.setenv("SWIGGY_API_BASE_URL", invalid_url)
        response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

        assert response.status_code == 200
        swiggy = response.json()["data"]["swiggy"]
        assert swiggy["configured"] is False
        assert "SWIGGY_API_BASE_URL" in swiggy["missing"]


def test_integrations_status_treats_example_placeholders_as_missing(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "your-google-email@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "your-google-app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <your-google-email@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "http://localhost:5173/reset-password")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_or_test_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_or_test_key_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "your_razorpay_webhook_signing_secret")
    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_live_or_test_key_id")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_live_or_test_key_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "your_razorpayx_customer_identifier")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "your_razorpayx_webhook_signing_secret")
    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://partner-api.swiggy.com")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "your_swiggy_pos_integration_token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "your_swiggy_outlet_id")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "your_swiggy_webhook_secret")
    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://partner-api.zomato.com")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "your_zomato_pos_integration_token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "your_zomato_outlet_id")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "your_zomato_webhook_secret")

    response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["password_reset_mail"]["configured"] is False
    assert "SMTP_USERNAME" in payload["password_reset_mail"]["missing"]
    assert "SMTP_PASSWORD" in payload["password_reset_mail"]["missing"]
    assert payload["razorpay"]["configured"] is False
    assert "RAZORPAY_KEY_ID" in payload["razorpay"]["missing"]
    assert "RAZORPAY_KEY_SECRET" in payload["razorpay"]["missing"]
    assert payload["razorpayx"]["configured"] is False
    assert "RAZORPAYX_ACCOUNT_NUMBER" in payload["razorpayx"]["missing"]
    assert "RAZORPAYX_WEBHOOK_SECRET" in payload["razorpayx"]["missing"]
    assert payload["swiggy"]["configured"] is False
    assert "SWIGGY_API_TOKEN" in payload["swiggy"]["missing"]
    assert payload["zomato"]["configured"] is False
    assert "ZOMATO_API_TOKEN" in payload["zomato"]["missing"]
    assert "your-google-app-password" not in str(payload)
    assert "your_zomato_pos_integration_token" not in str(payload)


def test_integrations_status_reports_ready_when_live_credentials_are_configured(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "gmail-app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.pos.example.com")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_hook_secret")
    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_live_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_live_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "rzpx_hook_secret")
    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.partner.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "swiggy-hook-secret")
    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.partner.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "zomato-hook-secret")

    response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["password_reset_mail"]["configured"] is True
    assert payload["password_reset_mail"]["provider"] == "google_smtp"
    assert payload["razorpay"]["configured"] is True
    assert payload["razorpay"]["webhook_url"] == "https://api.pos.example.com/api/v1/integrations/razorpay/webhook"
    assert payload["razorpayx"]["configured"] is True
    assert payload["razorpayx"]["webhook_url"] == "https://api.pos.example.com/api/v1/integrations/razorpayx/webhook"
    assert payload["swiggy"]["configured"] is True
    assert payload["swiggy"]["webhook_url"] == "https://api.pos.example.com/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch_id}"
    assert payload["zomato"]["configured"] is True
    assert "gmail-app-password" not in str(payload)
    assert "rzp_live_secret" not in str(payload)
    assert "rzpx_live_secret" not in str(payload)
    assert "rzpx_hook_secret" not in str(payload)
    assert "swiggy-token" not in str(payload)
    assert "zomato-token" not in str(payload)


def test_password_reset_mail_treats_whitespace_smtp_settings_as_not_configured(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "   ")
    monkeypatch.setenv("SMTP_FROM", "   ")
    monkeypatch.setenv("SMTP_USERNAME", "   ")
    monkeypatch.setenv("SMTP_PASSWORD", "   ")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")

    status_response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])
    assert status_response.status_code == 200
    status = status_response.json()["data"]["password_reset_mail"]
    assert status["configured"] is False
    assert status["provider"] == "not_configured"
    assert status["smtp_host_configured"] is False
    assert "SMTP_HOST" in status["missing"]
    assert "SMTP_FROM" in status["missing"]

    reset_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["email_delivery"] == "not_configured"


def test_password_reset_request_treats_placeholder_smtp_credentials_as_not_configured(client, owner_auth, monkeypatch):
    class FailIfCalledSMTP:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("SMTP must not be called with placeholder credentials")

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "your-google-email@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "your-google-app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <your-google-email@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FailIfCalledSMTP)

    reset_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert reset_response.status_code == 200
    payload = reset_response.json()["data"]
    assert payload["email_delivery"] == "not_configured"
    assert payload["email_provider"] == "google_smtp"


def test_password_reset_mail_reports_invalid_smtp_port_as_not_configured(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "not-a-port")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")

    status_response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])
    assert status_response.status_code == 200
    status = status_response.json()["data"]["password_reset_mail"]
    assert status["configured"] is False
    assert "SMTP_PORT" in status["missing"]

    reset_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["email_delivery"] == "not_configured"


def test_password_reset_request_does_not_send_mail_without_configured_reset_url(client, owner_auth, monkeypatch):
    class FailIfCalledSMTP:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("SMTP must not be called without FRONTEND_RESET_URL")

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.delenv("FRONTEND_RESET_URL", raising=False)
    monkeypatch.setattr("smtplib.SMTP", FailIfCalledSMTP)

    status_response = client.get("/api/v1/integrations/status", headers=owner_auth["headers"])
    assert status_response.status_code == 200
    status = status_response.json()["data"]["password_reset_mail"]
    assert status["configured"] is False
    assert "FRONTEND_RESET_URL" in status["missing"]

    reset_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["email_delivery"] == "not_configured"


def test_integrations_status_returns_selected_branch_webhook_urls(client, owner_auth, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.pos.example.com")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook URL Branch", "code": "WHB"}).json()["data"]

    response = client.get(f"/api/v1/integrations/status?branch_id={branch['id']}", headers=headers)

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["swiggy"]["webhook_url"] == f"https://api.pos.example.com/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}"
    assert payload["zomato"]["webhook_url"] == f"https://api.pos.example.com/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}"
    assert "{branch_id}" not in payload["swiggy"]["webhook_url"]


def test_integrations_status_trims_public_api_base_url_for_webhook_urls(client, owner_auth, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", " https://api.pos.example.com/ ")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Trimmed Webhook Branch", "code": "TWB"}).json()["data"]

    response = client.get(f"/api/v1/integrations/status?branch_id={branch['id']}", headers=headers)

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["razorpay"]["webhook_url"] == "https://api.pos.example.com/api/v1/integrations/razorpay/webhook"
    assert payload["swiggy"]["webhook_url"] == f"https://api.pos.example.com/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}"
    assert payload["zomato"]["webhook_url"] == f"https://api.pos.example.com/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}"


def test_password_reset_request_sends_google_smtp_email_without_exposing_token(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            self.started_tls = True

        def login(self, username, password):
            self.username = username
            self.password = password

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Password reset requested"
    assert payload["email_delivery"] == "sent"
    assert payload["email_provider"] == "google_smtp"
    assert "reset_token" not in payload
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "owner@saffron.example.com"
    assert "https://pos.example.com/reset-password?token=" in sent_messages[0].get_content()


def test_password_reset_mail_admin_test_sends_safe_message_to_current_user(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert host == "smtp.gmail.com"
            assert port == 587
            assert timeout == 10

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            assert username == "korvexa.reset@gmail.com"
            assert password == "app-password"

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/api/v1/integrations/password-reset-mail/test",
        headers=owner_auth["headers"],
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["email_delivery"] == "sent"
    assert payload["recipient"] == "owner@saffron.example.com"
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "owner@saffron.example.com"
    assert sent_messages[0]["Subject"] == "Korvexa password reset mail test"
    assert "configured correctly" in sent_messages[0].get_content()
    assert "token=" not in sent_messages[0].get_content()


def test_password_reset_request_ignores_placeholder_from_address(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            assert username == "korvexa.reset@gmail.com"
            assert password == "app-password"

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <your-google-email@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["email_delivery"] == "sent"
    assert len(sent_messages) == 1
    assert sent_messages[0]["From"] == "korvexa.reset@gmail.com"
    assert "your-google-email" not in sent_messages[0]["From"]


def test_password_reset_request_matches_email_case_insensitively(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            assert username == "korvexa.reset@gmail.com"
            assert password == "app-password"

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "OWNER@SAFFRON.EXAMPLE.COM"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_delivery"] == "sent"
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "owner@saffron.example.com"


def test_password_reset_link_trims_configured_frontend_url(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            self.username = username
            self.password = password

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", " https://pos.example.com/reset-password ")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["email_delivery"] == "sent"
    assert len(sent_messages) == 1
    content = sent_messages[0].get_content()
    assert "https://pos.example.com/reset-password?token=" in content
    assert "reset-password ?token=" not in content


def test_password_reset_link_replaces_stale_token_query_parameter(monkeypatch):
    from app.main import password_reset_link

    monkeypatch.setenv(
        "FRONTEND_RESET_URL",
        "https://pos.example.com/reset-password?source=email&token=stale-token",
    )

    link = password_reset_link("fresh token")

    assert link.count("token=") == 1
    assert "source=email" in link
    assert "token=fresh+token" in link
    assert "stale-token" not in link


def test_password_reset_request_supports_gmail_smtp_ssl_port_465(client, owner_auth, monkeypatch):
    sent_messages = []

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            raise AssertionError("SMTP_SSL must not call STARTTLS")

        def login(self, username, password):
            self.username = username
            self.password = password

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_SSL", "true")
    monkeypatch.setenv("SMTP_TLS", "false")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTPSSL)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_delivery"] == "sent"
    assert payload["email_provider"] == "google_smtp"
    assert len(sent_messages) == 1


def test_password_reset_mail_normalizes_grouped_google_app_password(client, owner_auth, monkeypatch):
    login_passwords = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, _username, password):
            login_passwords.append(password)

        def send_message(self, _message):
            return {}

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["email_delivery"] == "sent"
    assert login_passwords == ["abcdefghijklmnop"]


def test_password_reset_request_reports_google_smtp_delivery_failure(client, owner_auth, monkeypatch):
    class FailingSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            pass

        def login(self, *_args):
            raise OSError("gmail rejected app password")

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "wrong-app-password")
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")
    monkeypatch.setenv("FRONTEND_RESET_URL", "https://pos.example.com/reset-password")
    monkeypatch.setattr("smtplib.SMTP", FailingSMTP)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Password reset requested"
    assert payload["email_delivery"] == "failed"
    assert payload["email_provider"] == "google_smtp"
    assert "reset_token" not in payload


def test_password_reset_request_reports_google_smtp_missing_app_password_as_not_configured(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "korvexa.reset@gmail.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("SMTP_FROM", "Korvexa <korvexa.reset@gmail.com>")

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Password reset requested"
    assert payload["email_delivery"] == "not_configured"
    assert payload["email_provider"] == "google_smtp"
    assert "reset_token" not in payload


def test_password_reset_confirm_changes_password_and_rejects_reuse(client, owner_auth, monkeypatch):
    monkeypatch.setenv("EXPOSE_DEV_RESET_TOKEN", "true")
    requested = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    token = requested.json()["reset_token"]

    confirmed = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewChangeMe123!"},
    )
    assert confirmed.status_code == 200

    old_login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "NewChangeMe123!"},
    )
    assert new_login.status_code == 200

    reused = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "AnotherChangeMe123!"},
    )
    assert reused.status_code == 401


def test_password_reset_confirm_revokes_existing_login_sessions(client, owner_auth, monkeypatch):
    monkeypatch.setenv("EXPOSE_DEV_RESET_TOKEN", "true")
    requested = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    reset_token = requested.json()["reset_token"]

    confirmed = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "SessionRevoked123!"},
    )
    assert confirmed.status_code == 200

    existing_session = client.get("/api/v1/branches", headers=owner_auth["headers"])
    assert existing_session.status_code == 401


def test_password_reset_confirm_invalidates_older_unused_reset_links(client, owner_auth, monkeypatch):
    monkeypatch.setenv("EXPOSE_DEV_RESET_TOKEN", "true")
    first_request = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    second_request = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    first_token = first_request.json()["reset_token"]
    second_token = second_request.json()["reset_token"]

    confirmed = client.post(
        "/auth/password-reset/confirm",
        json={"token": second_token, "new_password": "NewestChangeMe123!"},
    )
    assert confirmed.status_code == 200

    stale = client.post(
        "/auth/password-reset/confirm",
        json={"token": first_token, "new_password": "StaleChangeMe123!"},
    )
    assert stale.status_code == 401

    stale_login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "StaleChangeMe123!"},
    )
    assert stale_login.status_code == 401

    newest_login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "NewestChangeMe123!"},
    )
    assert newest_login.status_code == 200


def test_password_reset_request_invalidates_older_unused_reset_links(client, owner_auth, monkeypatch):
    monkeypatch.setenv("EXPOSE_DEV_RESET_TOKEN", "true")
    first_request = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    first_token = first_request.json()["reset_token"]

    second_request = client.post(
        "/auth/password-reset/request",
        json={"email": "owner@saffron.example.com"},
    )
    second_token = second_request.json()["reset_token"]

    stale = client.post(
        "/auth/password-reset/confirm",
        json={"token": first_token, "new_password": "StaleRequestChangeMe123!"},
    )
    assert stale.status_code == 401

    confirmed = client.post(
        "/auth/password-reset/confirm",
        json={"token": second_token, "new_password": "LatestRequestChangeMe123!"},
    )
    assert confirmed.status_code == 200

    latest_login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "LatestRequestChangeMe123!"},
    )
    assert latest_login.status_code == 200


def test_register_duplicate_tenant_returns_conflict(client, owner_auth):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Saffron Table",
            "owner_name": "Second Owner",
            "email": "second-owner@example.com",
            "password": "ChangeMe123!",
        },
    )

    assert response.status_code == 409
    assert response.json()["success"] is False


def test_suspended_tenant_cannot_login_or_use_existing_token(client, owner_auth):
    from app.database import SessionLocal
    from app.models import Tenant

    with SessionLocal() as db:
        tenant = db.get(Tenant, owner_auth["tenant_id"])
        tenant.status = "suspended"
        db.commit()

    login = client.post(
        "/auth/login",
        json={"email": "owner@saffron.example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 403

    existing_token_request = client.get("/branches", headers=owner_auth["headers"])
    assert existing_token_request.status_code == 403


def test_locked_or_inactive_user_cannot_login_refresh_or_keep_using_existing_session(client, owner_auth):
    from datetime import timedelta

    from app.database import SessionLocal
    from app.main import naive_utcnow
    from app.models import User

    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "Lock Branch", "code": "LOCK"}).json()
    staff = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Locked Cashier",
            "email": "locked.cashier@example.com",
            "password": "ChangeMe123!",
            "role": "cashier",
        },
    )
    assert staff.status_code == 201
    staff_id = staff.json()["id"]

    login = client.post(
        "/auth/login",
        json={"email": "locked.cashier@example.com", "password": "ChangeMe123!"},
    )
    assert login.status_code == 200
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    refresh_token = login.json()["refresh_token"]

    locked = client.post(f"/admin/users/{staff_id}/lock", headers=headers)
    assert locked.status_code == 200

    existing_access = client.get("/branches", headers=staff_headers)
    assert existing_access.status_code == 401

    locked_login = client.post(
        "/auth/login",
        json={"email": "locked.cashier@example.com", "password": "ChangeMe123!"},
    )
    assert locked_login.status_code == 423

    locked_refresh = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert locked_refresh.status_code == 401

    with SessionLocal() as db:
        user = db.get(User, staff_id)
        user.failed_login_attempts = 4
        user.locked_until = naive_utcnow() + timedelta(minutes=15)
        db.commit()

    unlocked = client.post(f"/admin/users/{staff_id}/unlock", headers=headers)
    assert unlocked.status_code == 200

    with SessionLocal() as db:
        user = db.get(User, staff_id)
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    relogin = client.post(
        "/auth/login",
        json={"email": "locked.cashier@example.com", "password": "ChangeMe123!"},
    )
    assert relogin.status_code == 200

    disabled = client.patch(f"/users/{staff_id}", headers=headers, json={"status": "inactive"})
    assert disabled.status_code == 200

    inactive_login = client.post(
        "/auth/login",
        json={"email": "locked.cashier@example.com", "password": "ChangeMe123!"},
    )
    assert inactive_login.status_code == 403


def test_admin_user_cannot_delete_own_account(client, owner_auth):
    response = client.delete(f"/users/{owner_auth['user_id']}", headers=owner_auth["headers"])

    assert response.status_code == 400
    assert "own account" in response.json()["detail"]


def test_admin_password_reset_invalidates_outstanding_email_reset_link(client, owner_auth, monkeypatch):
    monkeypatch.setenv("EXPOSE_DEV_RESET_TOKEN", "true")
    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "Admin Reset Branch", "code": "ARB"}).json()
    staff = client.post(
        "/users",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Reset Cashier",
            "email": "reset.cashier@example.com",
            "password": "ChangeMe123!",
            "role": "cashier",
        },
    )
    assert staff.status_code == 201
    staff_id = staff.json()["id"]

    requested = client.post(
        "/auth/password-reset/request",
        json={"email": "reset.cashier@example.com"},
    )
    reset_token = requested.json()["reset_token"]

    admin_reset = client.post(
        f"/users/{staff_id}/reset-password",
        headers=headers,
        json={"new_password": "AdminChangeMe123!"},
    )
    assert admin_reset.status_code == 200

    stale = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "EmailChangeMe123!"},
    )
    assert stale.status_code == 401

    email_password_login = client.post(
        "/auth/login",
        json={"email": "reset.cashier@example.com", "password": "EmailChangeMe123!"},
    )
    assert email_password_login.status_code == 401

    admin_password_login = client.post(
        "/auth/login",
        json={"email": "reset.cashier@example.com", "password": "AdminChangeMe123!"},
    )
    assert admin_password_login.status_code == 200


def test_frontend_order_list_endpoint_and_payment_overage_guard(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "MG Road", "code": "MG"}).json()
    product = client.post(
        "/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Filter Coffee",
            "price": "100.00",
            "tax_rate": "0.00",
        },
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()

    listed = client.get(f"/orders?branch_id={branch['id']}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == order["id"]

    partial = client.post(
        f"/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "cash", "amount": "60.00"}]},
    )
    assert partial.status_code == 201
    assert partial.json()["payment_status"] == "partial"

    receipt = client.get(f"/orders/{order['id']}/receipt", headers=headers)
    assert receipt.status_code == 200
    receipt_lines = receipt.text.splitlines()
    paid_line = next(line for line in receipt_lines if line.startswith("Paid Amount"))
    balance_line = next(line for line in receipt_lines if line.startswith("Balance"))
    assert paid_line.endswith("60.00")
    assert balance_line.endswith("40.00")
    assert "-40.00" not in balance_line

    overage = client.post(
        f"/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "upi", "amount": "50.00"}]},
    )
    assert overage.status_code == 400
    assert "exceeds" in overage.json()["detail"]


def test_receipt_ignores_pending_gateway_attempts_for_paid_amount_and_balance(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_receipt_pending_123", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "Receipt Gateway", "code": "RCG"}).json()
    product = client.post(
        "/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Receipt Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()

    gateway = client.post(f"/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway.status_code == 201

    receipt = client.get(f"/orders/{order['id']}/receipt", headers=headers)
    assert receipt.status_code == 200
    receipt_lines = receipt.text.splitlines()
    payment_mode_line = next(line for line in receipt_lines if line.startswith("Payment Mode"))
    paid_line = next(line for line in receipt_lines if line.startswith("Paid Amount"))
    balance_line = next(line for line in receipt_lines if line.startswith("Balance"))
    assert payment_mode_line.endswith("UNPAID")
    assert paid_line.endswith("0.00")
    assert balance_line.endswith("100.00")


def test_manager_dashboard_notifies_about_pending_discount_requests(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post("/branches", headers=headers, json={"name": "Discount Alerts", "code": "DISC"}).json()
    product = client.post(
        "/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Discount Meal",
            "price": "200.00",
            "tax_rate": "0.00",
        },
    ).json()
    order = client.post(
        "/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()

    requested = client.post(
        "/discounts/request",
        headers=headers,
        json={"order_id": order["id"], "amount_or_percentage": "25.00", "is_percentage": False},
    )
    assert requested.status_code == 200

    dashboard = client.get(f"/reports/manager-dashboard?branch_id={branch['id']}", headers=headers)

    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["pending_discount_requests"] == 1
    assert any("discount" in notification["message"].lower() for notification in payload["notifications"])


def test_api_v1_staff_incentive_and_leave_actions_match_frontend_paths(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={"name": "Frontend Staff", "code": "FST"},
    ).json()["data"]

    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-API-01",
            "name": "Frontend Staff User",
            "email": "frontend.staff@saffron.example.com",
            "role": "cashier",
            "base_salary": 500,
        },
    ).json()["data"]

    incentive = client.post(
        "/api/v1/incentives",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": employee["id"],
            "sales_amount": 0,
            "incentive_amount": 125,
        },
    )
    assert incentive.status_code == 200
    assert incentive.json()["data"]["count"] == 1

    incentives = client.get(f"/api/v1/reports/incentives?branch_id={branch['id']}", headers=headers)
    assert incentives.status_code == 200
    incentive_row = incentives.json()["data"]["items"][0]
    assert incentive_row["employee_record_id"] == employee["id"]

    edited_incentive = client.patch(
        f"/api/v1/incentives/{incentive_row['id']}",
        headers=headers,
        json={"employee_id": employee["id"], "incentive_amount": 150},
    )
    assert edited_incentive.status_code == 200

    payout = client.post(f"/api/v1/incentives/{incentive_row['id']}/payout", headers=headers)
    assert payout.status_code == 200

    payroll = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    assert payroll.status_code == 200
    assert payroll.json()["data"]["items"][0]["incentives"] == "150.00"

    leave = client.post(
        "/api/v1/leaves",
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
    leave_id = leave.json()["data"]["id"]

    approved = client.patch(
        f"/api/v1/leaves/{leave_id}",
        headers=headers,
        json={"status": "approved", "reason": "Approved fever leave"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved"

    listed_leaves = client.get(f"/api/v1/leaves?branch_id={branch['id']}", headers=headers)
    assert listed_leaves.status_code == 200
    assert listed_leaves.json()["data"]["items"][0]["reason"] == "Approved fever leave"


def test_api_v1_staff_attendance_and_payroll_actions_match_frontend_paths(client, owner_auth):
    from app.database import SessionLocal
    from app.models import Attendance

    headers = owner_auth["headers"]
    branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={"name": "Staff Actions", "code": "STF"},
    ).json()["data"]

    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-ACT-01",
            "name": "Action Staff",
            "email": "action.staff@saffron.example.com",
            "role": "cashier",
            "base_salary": 500,
        },
    ).json()["data"]

    current = client.get(f"/api/v1/reports/attendance/current?branch_id={branch['id']}", headers=headers)
    assert current.status_code == 200
    assert current.json()["data"]["items"][0]["status"] == "not_started"

    clock_in = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_in.status_code == 200
    attendance_id = clock_in.json()["data"]["id"]

    overtime = client.patch(
        f"/api/v1/attendance/{attendance_id}",
        headers=headers,
        json={"overtime_minutes": 45, "overtime_status": "pending"},
    )
    assert overtime.status_code == 200

    attendance_report = client.get(f"/api/v1/reports/attendance?branch_id={branch['id']}", headers=headers)
    row = attendance_report.json()["data"]["items"][0]
    assert row["overtime_minutes"] == 45
    assert row["overtime_status"] == "pending"

    clock_out = client.post(
        "/api/v1/attendance/check-out",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_out.status_code == 200

    payroll = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    payroll_id = payroll.json()["data"]["items"][0]["id"]

    edited_payroll = client.patch(
        f"/api/v1/payroll/{payroll_id}",
        headers=headers,
        json={"day_salary": 750},
    )
    assert edited_payroll.status_code == 200

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={"payment_mode": "upi", "payment_reference": "UPI-TXN-778899"},
    )
    assert paid.status_code == 200

    payroll_after_pay = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    paid_row = payroll_after_pay.json()["data"]["items"][0]
    assert paid_row["day_salary"] == "750.00"
    assert paid_row["status"] == "paid"
    assert paid_row["payment_mode"] == "upi"
    assert paid_row["payment_reference"] == "UPI-TXN-778899"

    deleted_payroll = client.delete(f"/api/v1/payroll/{payroll_id}", headers=headers)
    assert deleted_payroll.status_code == 200

    deleted_attendance = client.delete(f"/api/v1/attendance/{attendance_id}", headers=headers)
    assert deleted_attendance.status_code == 200

    with SessionLocal() as db:
        old_attendance = Attendance(
            tenant_id=owner_auth["tenant_id"],
            branch_id=branch["id"],
            employee_id=employee["id"],
            check_in=(datetime.now(UTC) - timedelta(days=70)).replace(tzinfo=None),
            check_out=(datetime.now(UTC) - timedelta(days=70, hours=-8)).replace(tzinfo=None),
            shift_type="General",
        )
        db.add(old_attendance)
        db.commit()

    cleanup = client.delete("/api/v1/attendance/cleanup", headers=headers)
    assert cleanup.status_code == 200

    after_cleanup = client.get(f"/api/v1/reports/attendance?branch_id={branch['id']}", headers=headers)
    assert after_cleanup.json()["data"]["items"] == []


def test_razorpay_billing_order_is_verified_before_bill_is_paid(client, owner_auth, monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.text = "ok"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError(self.text)

        def json(self):
            return self._payload

    def fake_request(method, url, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        assert kwargs["auth"] == ("rzp_test_key", "rzp_secret")
        if method == "POST" and url.endswith("/v1/orders"):
            assert kwargs["json"]["currency"] == "INR"
            assert kwargs["json"]["amount"] == 10000
            return FakeResponse({"id": "order_rzp_123", "amount": 10000, "currency": "INR", "status": "created"})
        if method == "GET" and url.endswith("/v1/payments/pay_rzp_123"):
            return FakeResponse({
                "id": "pay_rzp_123",
                "order_id": "order_rzp_123",
                "amount": 10000,
                "currency": "INR",
                "status": "authorized",
            })
        if method == "POST" and url.endswith("/v1/payments/pay_rzp_123/capture"):
            assert kwargs["json"] == {"amount": 10000, "currency": "INR"}
            return FakeResponse({
                "id": "pay_rzp_123",
                "order_id": "order_rzp_123",
                "amount": 10000,
                "currency": "INR",
                "status": "captured",
                "captured": True,
            })
        raise AssertionError(f"Unexpected Razorpay request: {method} {url}")

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Bills", "code": "GWB"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Gateway Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201
    gateway_payload = gateway_order.json()["data"]
    assert gateway_payload["provider"] == "razorpay"
    assert gateway_payload["key_id"] == "rzp_test_key"
    assert gateway_payload["gateway_order_id"] == "order_rzp_123"
    assert gateway_payload["amount"] == "100.00"
    assert len(requests) == 1

    signature = hmac.new(
        b"rzp_secret",
        b"order_rzp_123|pay_rzp_123",
        hashlib.sha256,
    ).hexdigest()
    verified = client.post(
        f"/api/v1/orders/{order['id']}/payments/gateway/verify",
        headers=headers,
        json={
            "gateway_order_id": "order_rzp_123",
            "gateway_payment_id": "pay_rzp_123",
            "gateway_signature": signature,
        },
    )
    assert verified.status_code == 200
    paid_order = verified.json()["data"]
    assert paid_order["payment_status"] == "paid"
    assert paid_order["payments"][0]["method"] == "razorpay"
    assert paid_order["payments"][0]["status"] == "captured"
    assert paid_order["payments"][0]["provider"] == "razorpay"
    assert paid_order["payments"][0]["gateway_order_id"] == "order_rzp_123"
    assert paid_order["payments"][0]["gateway_payment_id"] == "pay_rzp_123"
    assert [(request["method"], request["url"].split("/v1", 1)[1]) for request in requests] == [
        ("POST", "/orders"),
        ("GET", "/payments/pay_rzp_123"),
        ("POST", "/payments/pay_rzp_123/capture"),
    ]

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert metrics["payment_gateway_totals"]["razorpay"] == "100.00"
    assert metrics["payment_method_totals"]["razorpay"] == "100.00"


def test_razorpay_credentials_are_trimmed_before_gateway_request(client, owner_auth, monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_trimmed_credentials", "amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        assert kwargs["auth"] == ("rzp_test_key", "rzp_secret")
        assert url.endswith("/v1/orders")
        return FakeResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", " rzp_test_key ")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", " rzp_secret ")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Trimmed", "code": "GWT"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Trimmed Gateway Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert gateway_order.status_code == 201
    payload = gateway_order.json()["data"]
    assert payload["key_id"] == "rzp_test_key"
    assert payload["gateway_order_id"] == "order_trimmed_credentials"
    assert len(requests) == 1


def test_razorpay_gateway_rejects_example_placeholder_credentials(client, owner_auth, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Razorpay API must not be called with placeholder credentials")

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_or_test_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_live_or_test_key_secret")
    monkeypatch.setattr("httpx.request", fail_if_called)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Placeholder", "code": "GPH"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Placeholder Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert gateway_order.status_code == 503
    assert gateway_order.json()["errors"][0]["detail"] == "RAZORPAY credentials are not configured"


def test_razorpay_gateway_returns_bad_gateway_for_invalid_provider_response(client, owner_auth, monkeypatch):
    class InvalidJsonResponse:
        status_code = 200
        text = "not-json"

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid json")

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return InvalidJsonResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Invalid Response", "code": "GIR"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Invalid Response Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert gateway_order.status_code == 502
    assert gateway_order.json()["errors"][0]["detail"] == "Razorpay request failed: invalid response"


def test_razorpay_gateway_returns_bad_gateway_when_provider_response_missing_order_id(client, owner_auth, monkeypatch):
    class MissingIdResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return MissingIdResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Missing ID", "code": "GMI"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Missing ID Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert gateway_order.status_code == 502
    assert gateway_order.json()["errors"][0]["detail"] == "Razorpay request failed: missing id"


def test_razorpay_gateway_returns_bad_gateway_when_provider_order_amount_mismatches(client, owner_auth, monkeypatch):
    class MismatchedAmountResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_wrong_amount", "amount": 5000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/orders")
        assert kwargs["json"]["amount"] == 10000
        return MismatchedAmountResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Wrong Amount", "code": "GWA"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Wrong Amount Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert gateway_order.status_code == 502
    assert gateway_order.json()["errors"][0]["detail"] == "Razorpay request failed: amount mismatch"
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unchanged = next(row for row in orders if row["id"] == order["id"])
    assert unchanged["payment_status"] == "unpaid"
    assert unchanged["payments"] == []


def test_pending_gateway_attempt_is_not_counted_in_payment_metrics(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_abandoned_123", "amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return FakeResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Metrics", "code": "GWM"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Metrics Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    cash_payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "cash", "amount": "100.00"}]},
    )
    assert cash_payment.status_code == 201

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert metrics["payment_method_totals"]["cash"] == "100.00"
    assert "razorpay" not in metrics["payment_gateway_totals"]
    assert "razorpay" not in metrics["payment_method_totals"]


def test_processing_billing_payment_does_not_mark_order_paid_or_count_metrics(client, owner_auth, monkeypatch):
    gateway_requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_after_processing_123", "amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        gateway_requests.append({"method": method, "url": url, **kwargs})
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return FakeResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Processing Payments", "code": "PRP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Processing Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    processing_payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "razorpay", "amount": "100.00", "status": "processing"}]},
    )
    assert processing_payment.status_code == 201
    processing_order = processing_payment.json()["data"]
    assert processing_order["payment_status"] == "unpaid"
    assert processing_order["status"] != "completed"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpay" not in metrics["payment_method_totals"]

    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201
    assert gateway_order.json()["data"]["amount"] == "100.00"
    assert len(gateway_requests) == 1

    captured_payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "cash", "amount": "100.00", "status": "captured"}]},
    )
    assert captured_payment.status_code == 201
    assert captured_payment.json()["data"]["payment_status"] == "paid"


def test_billing_payment_status_is_normalized_before_balance_and_metrics(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Normalized Payments", "code": "NRP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Normalized Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payments": [{"method": "razorpay", "amount": "100.00", "status": " Captured "}]},
    )
    assert payment.status_code == 201
    paid_order = payment.json()["data"]
    assert paid_order["payment_status"] == "paid"
    assert paid_order["payments"][0]["status"] == "captured"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert metrics["payment_method_totals"]["razorpay"] == "100.00"


def test_late_duplicate_gateway_callback_cannot_overpay_order(client, owner_auth, monkeypatch):
    gateway_ids = iter(["order_first_attempt", "order_second_attempt"])

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/v1/orders"):
            return FakeResponse({
                "id": next(gateway_ids),
                "amount": 10000,
                "currency": "INR",
                "status": "created",
            })
        if method == "GET" and url.endswith("/v1/payments/pay_second"):
            return FakeResponse({
                "id": "pay_second",
                "order_id": "order_second_attempt",
                "amount": 10000,
                "currency": "INR",
                "status": "captured",
                "captured": True,
            })
        raise AssertionError(f"Unexpected Razorpay request: {method} {url}")

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Duplicate", "code": "GWD"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Duplicate Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    first = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers).json()["data"]
    failed_body = json.dumps({
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_first_failed",
                    "order_id": first["gateway_order_id"],
                    "error_description": "customer payment failed",
                }
            }
        },
    }, separators=(",", ":")).encode()
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    failed_signature = hmac.new(b"webhook_secret", failed_body, hashlib.sha256).hexdigest()
    failed_webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=failed_body,
        headers={"x-razorpay-signature": failed_signature, "content-type": "application/json"},
    )
    assert failed_webhook.status_code == 200

    second = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers).json()["data"]
    assert second["gateway_order_id"] != first["gateway_order_id"]

    second_signature = hmac.new(
        b"rzp_secret",
        f"{second['gateway_order_id']}|pay_second".encode(),
        hashlib.sha256,
    ).hexdigest()
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments/gateway/verify",
        headers=headers,
        json={
            "gateway_order_id": second["gateway_order_id"],
            "gateway_payment_id": "pay_second",
            "gateway_signature": second_signature,
        },
    )
    assert paid.status_code == 200

    replay = client.post(
        f"/api/v1/orders/{order['id']}/payments/gateway/verify",
        headers=headers,
        json={
            "gateway_order_id": second["gateway_order_id"],
            "gateway_payment_id": "pay_second",
            "gateway_signature": second_signature,
        },
    )
    assert replay.status_code == 200

    first_signature = hmac.new(
        b"rzp_secret",
        f"{first['gateway_order_id']}|pay_first".encode(),
        hashlib.sha256,
    ).hexdigest()
    late_callback = client.post(
        f"/api/v1/orders/{order['id']}/payments/gateway/verify",
        headers=headers,
        json={
            "gateway_order_id": first["gateway_order_id"],
            "gateway_payment_id": "pay_first",
            "gateway_signature": first_signature,
        },
    )
    assert late_callback.status_code == 409

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert metrics["payment_gateway_totals"]["razorpay"] == "100.00"
    assert metrics["payment_method_totals"]["razorpay"] == "100.00"


def test_open_gateway_order_is_reused_for_repeated_billing_payment_clicks(client, owner_auth, monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_reused_attempt", "amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return FakeResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Reuse", "code": "GWR"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Reuse Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]

    first = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    second = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["gateway_order_id"] == "order_reused_attempt"
    assert second.json()["data"]["gateway_order_id"] == "order_reused_attempt"
    assert len(requests) == 1


def test_razorpay_payment_captured_webhook_settles_gateway_order(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_webhook_123", "amount": 10000, "currency": "INR", "status": "created"}

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/orders")
        return FakeResponse()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Gateway", "code": "RGW"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Webhook Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_webhook_123",
            "order_id": "order_webhook_123",
            "amount": 10000,
            "currency": "INR",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    paid_order = next(row for row in orders if row["id"] == order["id"])
    assert paid_order["payment_status"] == "paid"
    assert paid_order["payments"][0]["status"] == "captured"
    assert paid_order["payments"][0]["gateway_payment_id"] == "pay_webhook_123"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert metrics["payment_gateway_totals"]["razorpay"] == "100.00"


def test_razorpay_payment_captured_webhook_rejects_amount_mismatch(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_amount_mismatch_123", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Mismatch", "code": "RWM"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Mismatch Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_amount_mismatch",
            "order_id": "order_amount_mismatch_123",
            "amount": 5000,
            "currency": "INR",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 409
    assert webhook.json()["errors"][0]["detail"] == "Razorpay payment amount mismatch"

    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unpaid_order = next(row for row in orders if row["id"] == order["id"])
    assert unpaid_order["payment_status"] == "unpaid"
    assert unpaid_order["payments"][0]["status"] == "created"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpay" not in metrics["payment_gateway_totals"]


def test_razorpay_payment_captured_webhook_rejects_currency_mismatch(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_currency_mismatch_123", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Currency", "code": "RWC"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Currency Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    assert client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers).status_code == 201

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_currency_mismatch",
            "order_id": "order_currency_mismatch_123",
            "amount": 10000,
            "currency": "USD",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 409
    assert webhook.json()["errors"][0]["detail"] == "Razorpay payment currency mismatch"
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unpaid_order = next(row for row in orders if row["id"] == order["id"])
    assert unpaid_order["payment_status"] == "unpaid"
    assert unpaid_order["payments"][0]["status"] == "created"


def test_razorpay_refund_waits_for_processed_webhook_before_marking_order_refunded(client, owner_auth, monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_request(method, url, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        if method == "POST" and url.endswith("/v1/orders"):
            return FakeResponse({"id": "order_refund_123", "amount": 10000, "currency": "INR", "status": "created"})
        if method == "GET" and url.endswith("/v1/payments/pay_refund_123"):
            return FakeResponse({
                "id": "pay_refund_123",
                "order_id": "order_refund_123",
                "amount": 10000,
                "currency": "INR",
                "status": "captured",
                "captured": True,
            })
        if method == "POST" and url.endswith("/v1/payments/pay_refund_123/refund"):
            assert kwargs["headers"]["X-Refund-Idempotency"]
            assert kwargs["json"]["amount"] == 10000
            assert kwargs["json"]["speed"] == "normal"
            return FakeResponse({
                "id": "rfnd_refund_123",
                "payment_id": "pay_refund_123",
                "amount": 10000,
                "currency": "INR",
                "status": "pending",
                "receipt": kwargs["json"]["receipt"],
            })
        raise AssertionError(f"Unexpected Razorpay request: {method} {url}")

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Refund", "code": "RGR"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Refund Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers).json()["data"]
    signature = hmac.new(
        b"rzp_secret",
        f"{gateway['gateway_order_id']}|pay_refund_123".encode(),
        hashlib.sha256,
    ).hexdigest()
    paid_order = client.post(
        f"/api/v1/orders/{order['id']}/payments/gateway/verify",
        headers=headers,
        json={
            "gateway_order_id": gateway["gateway_order_id"],
            "gateway_payment_id": "pay_refund_123",
            "gateway_signature": signature,
        },
    ).json()["data"]
    local_payment_id = paid_order["payments"][0]["id"]

    refund = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=headers,
        json={"payment_id": local_payment_id, "amount": "100.00", "reason": "customer_request"},
    )

    assert refund.status_code == 201
    assert refund.json()["data"]["refund"]["gateway_refund_id"] == "rfnd_refund_123"
    assert refund.json()["data"]["refund"]["status"] == "pending"
    assert refund.json()["data"]["order"]["payment_status"] == "refund_pending"

    body = json.dumps({
        "event": "refund.processed",
        "payload": {"refund": {"entity": {
            "id": "rfnd_refund_123",
            "payment_id": "pay_refund_123",
            "amount": 10000,
            "currency": "INR",
            "status": "processed",
        }}},
    }, separators=(",", ":")).encode()
    webhook_signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": webhook_signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 200
    assert webhook.json()["data"]["refund_id"]
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    refunded_order = next(row for row in orders if row["id"] == order["id"])
    assert refunded_order["payment_status"] == "refunded"
    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpay" not in metrics["payment_gateway_totals"]


def test_razorpay_webhook_secret_is_trimmed_before_signature_verification(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_trimmed_webhook_secret", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", " webhook_secret ")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Trimmed", "code": "RWT"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Trimmed Webhook Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_trimmed_webhook_secret",
            "order_id": "order_trimmed_webhook_secret",
            "amount": 10000,
            "currency": "INR",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 200
    paid_order = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]
    assert paid_order["payment_status"] == "paid"


def test_razorpay_webhook_rejects_example_placeholder_secret(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_placeholder_webhook_secret", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "your_razorpay_webhook_signing_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Placeholder", "code": "RWP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Placeholder Webhook Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_placeholder_webhook_secret", "order_id": "order_placeholder_webhook_secret"}}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"your_razorpay_webhook_signing_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 503
    assert webhook.json()["errors"][0]["detail"] == "RAZORPAY_WEBHOOK_SECRET is not configured"
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unpaid_order = next(row for row in orders if row["id"] == order["id"])
    assert unpaid_order["payment_status"] == "unpaid"
    assert unpaid_order["payments"][0]["status"] == "created"


def test_razorpay_payment_failed_webhook_marks_pending_attempt_failed(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "order_failed_webhook", "amount": 10000, "currency": "INR", "status": "created"}

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Failed", "code": "RGF"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Failed Meal", "price": "100.00", "tax_rate": "0.00"},
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={"branch_id": branch["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()["data"]
    gateway_order = client.post(f"/api/v1/orders/{order['id']}/payments/gateway", headers=headers)
    assert gateway_order.status_code == 201

    body = json.dumps({
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_webhook",
                    "order_id": "order_failed_webhook",
                    "error_description": "card declined",
                }
            }
        },
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    failed_order = next(row for row in orders if row["id"] == order["id"])
    assert failed_order["payment_status"] == "unpaid"
    assert failed_order["payments"][0]["status"] == "failed"
    assert failed_order["payments"][0]["gateway_payment_id"] == "pay_failed_webhook"
    assert failed_order["payments"][0]["reference"] == "card declined"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpay" not in metrics["payment_gateway_totals"]


def test_online_delivery_order_accept_creates_delivery_order_in_kds(client, owner_auth, monkeypatch):
    provider_calls = []

    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "confirmed"}

    def fake_provider_post(url, **kwargs):
        provider_calls.append({"url": url, **kwargs})
        assert url == "https://partner.test/online-ordering/v1/order/confirm"
        assert kwargs["headers"]["Authorization"] == "Bearer zomato-token"
        assert kwargs["json"]["external_order_id"] == "ZOM-1001"
        assert kwargs["json"]["status"] == "accepted"
        return FakeProviderResponse()

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://partner.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "outlet-1")
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Aggregator Branch", "code": "AGG"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Delivery Biryani", "price": "180.00", "tax_rate": "0.00"},
    ).json()["data"]

    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "zomato",
            "external_order_id": "ZOM-1001",
            "customer_name": "Online Guest",
            "customer_phone": "+919999999999",
            "delivery_address": "Tower 1, Test Street",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    assert delivery["status"] == "new"
    assert delivery["provider"] == "zomato"
    assert delivery["total"] == "360.00"

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    assert len(provider_calls) == 1
    payload = accepted.json()["data"]
    assert payload["delivery_order"]["status"] == "accepted"
    assert payload["delivery_order"]["order_id"]
    assert payload["order"]["order_type"] == "delivery"
    assert payload["order"]["status"] == "active"
    assert payload["order"]["kds_status"] == "new"
    assert payload["order"]["payment_status"] == "paid"

    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    delivery_orders = [order for order in orders if order["order_type"] == "delivery"]
    assert len(delivery_orders) == 1
    assert delivery_orders[0]["items"][0]["name"] == "Delivery Biryani"


def test_online_delivery_provider_config_is_trimmed_before_accept_call(client, owner_auth, monkeypatch):
    provider_calls = []

    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    def fake_provider_post(url, **kwargs):
        provider_calls.append({"url": url, **kwargs})
        assert url == "https://swiggy.test/orders/SWG-TRIM-1/accept"
        assert kwargs["headers"]["X-Partner-Token"] == "Token swiggy-token"
        assert kwargs["json"]["outlet_id"] == "swiggy-outlet"
        return FakeProviderResponse()

    monkeypatch.setenv("SWIGGY_API_BASE_URL", " https://swiggy.test/ ")
    monkeypatch.setenv("SWIGGY_API_TOKEN", " swiggy-token ")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", " swiggy-outlet ")
    monkeypatch.setenv("SWIGGY_AUTH_HEADER", " X-Partner-Token ")
    monkeypatch.setenv("SWIGGY_AUTH_SCHEME", " Token ")
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Trim", "code": "SWT"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Trim Delivery Meal", "price": "120.00", "tax_rate": "0.00"},
    ).json()["data"]

    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-TRIM-1",
            "customer_name": "Trim Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)

    assert accepted.status_code == 200
    assert len(provider_calls) == 1
    assert accepted.json()["data"]["delivery_order"]["status"] == "accepted"


def test_online_delivery_accept_rejects_placeholder_provider_credentials(client, owner_auth, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Delivery provider API must not be called with placeholder credentials")

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://partner-api.swiggy.com")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "your_swiggy_pos_integration_token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "your_swiggy_outlet_id")
    monkeypatch.setattr("httpx.post", fail_if_called)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Placeholder", "code": "SWP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Placeholder Delivery Meal", "price": "120.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-PLACEHOLDER-1",
            "customer_name": "Placeholder Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)

    assert accepted.status_code == 503
    assert accepted.json()["errors"][0]["detail"] == "Swiggy integration is not configured"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unchanged = next(item for item in deliveries if item["id"] == delivery["id"])
    assert unchanged["status"] == "new"
    assert unchanged["order_id"] is None


def test_online_delivery_accept_requires_provider_outlet_id(client, owner_auth, monkeypatch):
    provider_calls = []

    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    def fake_provider_post(url, **kwargs):
        provider_calls.append({"url": url, **kwargs})
        return FakeProviderResponse()

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.delenv("SWIGGY_OUTLET_ID", raising=False)
    monkeypatch.delenv("SWIGGY_RESTAURANT_ID", raising=False)
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Missing Outlet", "code": "SMO"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Missing Outlet Meal", "price": "120.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-MISSING-OUTLET-1",
            "customer_name": "Missing Outlet Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)

    assert accepted.status_code == 503
    assert accepted.json()["errors"][0]["detail"] == "Swiggy integration is not configured"
    assert provider_calls == []
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unchanged = next(item for item in deliveries if item["id"] == delivery["id"])
    assert unchanged["status"] == "new"
    assert unchanged["order_id"] is None


def test_online_delivery_accept_rejects_provider_body_failure(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "message": "outlet is offline"}

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Body Failure", "code": "ZBF"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Body Failure Meal", "price": "110.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "zomato",
            "external_order_id": "ZOM-BODY-FAIL-1",
            "customer_name": "Body Fail Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)

    assert accepted.status_code == 502
    assert accepted.json()["errors"][0]["detail"] == "Zomato update failed: outlet is offline"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    unchanged = next(item for item in deliveries if item["id"] == delivery["id"])
    assert unchanged["status"] == "new"
    assert unchanged["order_id"] is None
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(order["order_type"] != "delivery" for order in orders)


def test_online_delivery_webhook_creates_provider_order_from_menu_sku(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Webhook", "code": "SWG"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Webhook Dosa", "sku": "SWG-DOSA", "price": "90.00", "tax_rate": "0.00"},
    ).json()["data"]

    payload = {
        "order": {
            "order_id": "SWG-2001",
            "customer": {"name": "Webhook Guest", "phone": "+918888888888"},
            "payment": {"mode": "prepaid", "status": "paid"},
            "items": [{"sku": "SWG-DOSA", "name": "Webhook Dosa", "quantity": 2, "price": "90.00"}],
        }
    }
    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json=payload,
    )

    assert response.status_code == 201
    delivery = response.json()["data"]
    assert delivery["provider"] == "swiggy"
    assert delivery["external_order_id"] == "SWG-2001"
    assert delivery["status"] == "new"
    assert delivery["items"][0]["product_id"] == product["id"]
    assert delivery["items"][0]["unmapped"] is False


def test_delivery_webhook_without_payment_details_does_not_mark_order_paid(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Unknown Payment", "code": "UNP"}).json()["data"]
    client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Unknown Payment Meal", "sku": "UNP-MEAL", "price": "90.00", "tax_rate": "0.00"},
    )
    payload = {
        "order": {
            "order_id": "SWG-UNKNOWN-PAYMENT",
            "items": [{"sku": "UNP-MEAL", "name": "Unknown Payment Meal", "quantity": 1, "price": "90.00"}],
        }
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    intake = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        content=body,
        headers={"x-korvexa-webhook-secret": "hook-secret", "content-type": "application/json"},
    )

    assert intake.status_code == 201
    delivery = intake.json()["data"]
    assert delivery["payment_mode"] == "unknown"
    assert delivery["payment_status"] == "pending"

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()["data"]["order"]["payment_status"] == "unpaid"
    assert accepted.json()["data"]["order"]["payments"] == []


def test_zomato_order_relay_returns_provider_acknowledgement_contract(client, owner_auth, monkeypatch):
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    headers = owner_auth["headers"]
    branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={"name": "Zomato Relay Ack", "code": "ZRA"},
    ).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Relay Meal",
            "sku": "ZOM-RELAY-MEAL",
            "price": "125.00",
            "tax_rate": "0.00",
        },
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "ZOM-RELAY-1",
                "restaurant_id": "zomato-outlet",
                "items": [{"sku": "ZOM-RELAY-MEAL", "name": product["name"], "quantity": 1, "price": "125.00"}],
            }
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["code"] == 200
    assert payload["status"] == "success"
    assert payload["message"] == "Order received successfully"
    assert payload["external_order_id"]
    assert payload["rejection_message_id"] == 0
    assert payload["data"]["external_order_id"] == "ZOM-RELAY-1"


def test_delivery_webhook_accepts_configured_authorization_header(client, owner_auth, monkeypatch):
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setenv("ZOMATO_WEBHOOK_AUTH_HEADER", "Authorization")
    monkeypatch.setenv("ZOMATO_WEBHOOK_AUTH_SCHEME", "Bearer")
    headers = owner_auth["headers"]
    branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={"name": "Zomato Auth Header", "code": "ZAH"},
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"Authorization": "Bearer hook-secret"},
        json={"order": {"order_id": "ZOM-AUTH-1"}},
    )

    assert response.status_code == 201
    assert response.json()["data"]["external_order_id"] == "ZOM-AUTH-1"


def test_online_delivery_webhook_secret_is_trimmed_before_verification(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", " hook-secret ")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Hook Trim", "code": "SHT"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Hook Trim Dosa", "sku": "SWG-HOOK-TRIM", "price": "95.00", "tax_rate": "0.00"},
    ).json()["data"]

    payload = {
        "order": {
            "order_id": "SWG-HOOK-TRIM-1",
            "customer": {"name": "Hook Trim Guest", "phone": "+918888888889"},
            "payment": {"mode": "prepaid", "status": "paid"},
            "items": [{"sku": "SWG-HOOK-TRIM", "name": "Hook Trim Dosa", "quantity": 1, "price": "95.00"}],
        }
    }
    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json=payload,
    )

    assert response.status_code == 201
    delivery = response.json()["data"]
    assert delivery["external_order_id"] == "SWG-HOOK-TRIM-1"
    assert delivery["items"][0]["product_id"] == product["id"]


def test_online_delivery_webhook_requires_configured_secret(client, owner_auth, monkeypatch):
    monkeypatch.delenv("SWIGGY_WEBHOOK_SECRET", raising=False)
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Hook Missing", "code": "SHM"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Missing Secret Dosa", "sku": "SWG-HOOK-MISSING", "price": "95.00", "tax_rate": "0.00"},
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        json={
            "order": {
                "order_id": "SWG-HOOK-MISSING-1",
                "customer": {"name": "Unsigned Guest"},
                "payment": {"mode": "prepaid", "status": "paid"},
                "items": [{"sku": "SWG-HOOK-MISSING", "name": "Missing Secret Dosa", "quantity": 1, "price": "95.00"}],
            }
        },
    )

    assert response.status_code == 503
    assert response.json()["errors"][0]["detail"] == "Swiggy webhook is not configured"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(item["external_order_id"] != "SWG-HOOK-MISSING-1" for item in deliveries)
    assert product["id"]


def test_online_delivery_webhook_rejects_non_positive_item_quantity(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Bad Quantity", "code": "SBQ"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Bad Quantity Dosa", "sku": "SWG-BAD-QTY", "price": "95.00", "tax_rate": "0.00"},
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "SWG-BAD-QTY-1",
                "customer": {"name": "Bad Quantity Guest"},
                "payment": {"mode": "prepaid", "status": "paid"},
                "items": [{"sku": "SWG-BAD-QTY", "name": "Bad Quantity Dosa", "quantity": 0, "price": "95.00"}],
            }
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["detail"] == "Invalid delivery item quantity"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(item["external_order_id"] != "SWG-BAD-QTY-1" for item in deliveries)
    assert product["id"]


def test_online_delivery_webhook_rejects_negative_item_price(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Bad Price", "code": "SBP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Bad Price Dosa", "sku": "SWG-BAD-PRICE", "price": "95.00", "tax_rate": "0.00"},
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "SWG-BAD-PRICE-1",
                "customer": {"name": "Bad Price Guest"},
                "payment": {"mode": "prepaid", "status": "paid"},
                "items": [{"sku": "SWG-BAD-PRICE", "name": "Bad Price Dosa", "quantity": 1, "price": "-95.00"}],
            }
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["detail"] == "Invalid delivery item amount"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(item["external_order_id"] != "SWG-BAD-PRICE-1" for item in deliveries)
    assert product["id"]


def test_online_delivery_webhook_rejects_negative_order_total(client, owner_auth, monkeypatch):
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Bad Total", "code": "ZBT"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Bad Total Meal", "sku": "ZOM-BAD-TOTAL", "price": "125.00", "tax_rate": "0.00"},
    ).json()["data"]

    response = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "ZOM-BAD-TOTAL-1",
                "customer": {"name": "Bad Total Guest"},
                "payment": {"mode": "prepaid", "status": "paid"},
                "total": "-125.00",
                "items": [{"sku": "ZOM-BAD-TOTAL", "name": "Bad Total Meal", "quantity": 1, "price": "125.00"}],
            }
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["detail"] == "Invalid delivery order amount"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(item["external_order_id"] != "ZOM-BAD-TOTAL-1" for item in deliveries)
    assert product["id"]


def test_online_delivery_webhook_rejects_example_placeholder_secret(client, owner_auth, monkeypatch):
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "your_swiggy_webhook_secret")
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Hook Placeholder", "code": "SHP"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Hook Placeholder Dosa", "sku": "SWG-HOOK-PLACEHOLDER", "price": "95.00", "tax_rate": "0.00"},
    ).json()["data"]

    payload = {
        "order": {
            "order_id": "SWG-HOOK-PLACEHOLDER-1",
            "customer": {"name": "Hook Placeholder Guest", "phone": "+918888888890"},
            "payment": {"mode": "prepaid", "status": "paid"},
            "items": [{"sku": "SWG-HOOK-PLACEHOLDER", "name": "Hook Placeholder Dosa", "quantity": 1, "price": "95.00"}],
        }
    }
    response = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "your_swiggy_webhook_secret"},
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["errors"][0]["detail"] == "Invalid delivery webhook signature"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    assert all(item["external_order_id"] != "SWG-HOOK-PLACEHOLDER-1" for item in deliveries)
    assert product["id"]


def test_online_delivery_webhook_completed_payment_is_paid_when_accepted(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Paid Webhook", "code": "ZPW"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Paid Delivery Meal", "sku": "ZOM-PAID-MEAL", "price": "140.00", "tax_rate": "0.00"},
    ).json()["data"]
    webhook = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "ZOM-PAID-1",
                "customer": {"name": "Paid Guest"},
                "payment": {"mode": "prepaid", "status": "completed"},
                "items": [{"sku": "ZOM-PAID-MEAL", "name": "Paid Delivery Meal", "quantity": 1, "price": "140.00"}],
            }
        },
    )
    assert webhook.status_code == 201
    delivery = webhook.json()["data"]
    assert delivery["payment_mode"] == "prepaid"
    assert delivery["payment_status"] == "paid"

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    order = accepted.json()["data"]["order"]
    assert order["payment_status"] == "paid"
    assert order["payments"][0]["provider"] == "zomato"
    assert order["payments"][0]["amount"] == "140.00"
    assert product["id"] == order["items"][0]["product_id"]


def test_online_delivery_webhook_cod_without_status_stays_unpaid_when_accepted(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy COD Webhook", "code": "SCW"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "COD Delivery Meal", "sku": "SWG-COD-MEAL", "price": "160.00", "tax_rate": "0.00"},
    ).json()["data"]
    webhook = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "SWG-COD-1",
                "customer": {"name": "COD Guest"},
                "payment": {"mode": "cod"},
                "items": [{"sku": "SWG-COD-MEAL", "name": "COD Delivery Meal", "quantity": 1, "price": "160.00"}],
            }
        },
    )
    assert webhook.status_code == 201
    delivery = webhook.json()["data"]
    assert delivery["payment_mode"] == "cod"
    assert delivery["payment_status"] == "unpaid"

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    order = accepted.json()["data"]["order"]
    assert order["payment_status"] == "unpaid"
    assert order["payments"] == []
    assert product["id"] == order["items"][0]["product_id"]


def test_online_delivery_webhook_cancellation_updates_linked_pos_order(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    def fake_provider_post(url, **kwargs):
        assert url == "https://swiggy.test/orders/SWG-CANCEL-1/accept"
        assert kwargs["headers"]["Authorization"] == "Bearer swiggy-token"
        return FakeProviderResponse()

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Cancel", "code": "SWC"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Cancel Dosa", "sku": "SWG-CANCEL-DOSA", "price": "90.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-CANCEL-1",
            "customer_name": "Cancel Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    linked_order_id = accepted.json()["data"]["order"]["id"]

    cancel_payload = {
        "order": {
            "order_id": "SWG-CANCEL-1",
            "status": "cancelled",
        }
    }
    cancelled = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json=cancel_payload,
    )
    assert cancelled.status_code == 201
    cancelled_delivery = cancelled.json()["data"]
    assert cancelled_delivery["status"] == "cancelled"
    assert cancelled_delivery["customer_name"] == "Cancel Guest"
    assert cancelled_delivery["payment_mode"] == "prepaid"
    assert cancelled_delivery["payment_status"] == "paid"
    assert cancelled_delivery["total"] == "90.00"
    assert cancelled_delivery["items"][0]["product_id"] == product["id"]

    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    linked = next(order for order in orders if order["id"] == linked_order_id)
    assert linked["status"] == "cancelled"


def test_kds_ready_updates_linked_online_delivery_status_and_notifies_provider(client, owner_auth, monkeypatch):
    provider_calls = []

    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "sent"}

    def fake_provider_post(url, **kwargs):
        provider_calls.append({"url": url, **kwargs})
        return FakeProviderResponse()

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy KDS Ready", "code": "SKR"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Ready Dosa", "sku": "SWG-READY-DOSA", "price": "90.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-READY-1",
            "customer_name": "Ready Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]

    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    order_id = accepted.json()["data"]["order"]["id"]

    ready = client.patch(
        f"/api/v1/kds/orders/{order_id}",
        headers=headers,
        json={"kds_status": "ready"},
    )

    assert ready.status_code == 200
    assert provider_calls[-1]["url"] == "https://swiggy.test/orders/SWG-READY-1/ready"
    assert provider_calls[-1]["json"]["status"] == "ready"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    linked_delivery = next(item for item in deliveries if item["id"] == delivery["id"])
    assert linked_delivery["status"] == "ready"


def test_kds_ready_provider_failure_keeps_delivery_and_order_in_previous_state(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def __init__(self, failed=False):
            self.failed = failed

        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "message": "provider temporarily unavailable"} if self.failed else {"status": "sent"}

    def fake_provider_post(url, **_kwargs):
        return FakeProviderResponse(failed=url.endswith("/ready"))

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setattr("httpx.post", fake_provider_post)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "KDS Sync Failure", "code": "KSF"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Sync Meal", "sku": "SYNC-MEAL", "price": "90.00", "tax_rate": "0.00"},
    ).json()["data"]
    delivery = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-SYNC-FAIL",
            "customer_name": "Sync Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    ).json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    order_id = accepted.json()["data"]["order"]["id"]

    ready = client.patch(
        f"/api/v1/kds/orders/{order_id}",
        headers=headers,
        json={"kds_status": "ready"},
    )

    assert ready.status_code == 502
    assert ready.json()["errors"][0]["detail"] == "Swiggy update failed: provider temporarily unavailable"
    deliveries = client.get(f"/api/v1/online-delivery/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    linked_delivery = next(item for item in deliveries if item["id"] == delivery["id"])
    assert linked_delivery["status"] == "accepted"
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    linked_order = next(item for item in orders if item["id"] == order_id)
    assert linked_order["kds_status"] == "new"


def test_online_delivery_webhook_ready_status_updates_existing_delivery_status(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Ready Status", "code": "ZRS"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Ready Status Meal", "sku": "ZOM-READY-MEAL", "price": "125.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "zomato",
            "external_order_id": "ZOM-READY-1",
            "customer_name": "Ready Status Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200

    ready_update = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={"order": {"order_id": "ZOM-READY-1", "status": "food_ready"}},
    )

    assert ready_update.status_code == 201
    updated = ready_update.json()["data"]
    assert updated["status"] == "ready"
    assert updated["total"] == "125.00"
    orders = client.get(f"/api/v1/orders?branch_id={branch['id']}", headers=headers).json()["data"]["items"]
    linked = next(order for order in orders if order["id"] == accepted.json()["data"]["order"]["id"])
    assert linked["kds_status"] == "ready"


def test_online_delivery_webhook_late_ready_status_does_not_downgrade_picked_up_order(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "sent"}

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Late Ready", "code": "SLR"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Late Ready Meal", "sku": "SWG-LATE-READY", "price": "140.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-LATE-READY-1",
            "customer_name": "Late Ready Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    picked_up = client.patch(
        f"/api/v1/online-delivery/orders/{delivery['id']}",
        headers=headers,
        json={"status": "picked_up"},
    )
    assert picked_up.status_code == 200
    assert picked_up.json()["data"]["status"] == "picked_up"

    late_ready = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={"order": {"order_id": "SWG-LATE-READY-1", "status": "food_ready"}},
    )

    assert late_ready.status_code == 201
    updated = late_ready.json()["data"]
    assert updated["status"] == "picked_up"
    assert updated["total"] == "140.00"


def test_online_delivery_webhook_without_status_preserves_existing_delivery_status(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Rider", "code": "ZRD"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Rider Meal", "sku": "ZOM-RIDER-MEAL", "price": "110.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "zomato",
            "external_order_id": "ZOM-RIDER-1",
            "customer_name": "Rider Guest",
            "payment_mode": "cod",
            "payment_status": "unpaid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200

    rider_update = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "ZOM-RIDER-1",
                "rider": {"name": "Ravi", "phone": "+919876543210"},
            }
        },
    )
    assert rider_update.status_code == 201
    updated = rider_update.json()["data"]
    assert updated["status"] == "accepted"
    assert updated["rider_name"] == "Ravi"
    assert updated["rider_phone"] == "+919876543210"
    assert updated["payment_mode"] == "cod"
    assert updated["payment_status"] == "unpaid"
    assert updated["total"] == "110.00"


def test_online_delivery_webhook_unknown_status_preserves_existing_delivery_status(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("ZOMATO_API_BASE_URL", "https://zomato.test")
    monkeypatch.setenv("ZOMATO_API_TOKEN", "zomato-token")
    monkeypatch.setenv("ZOMATO_OUTLET_ID", "zomato-outlet")
    monkeypatch.setenv("ZOMATO_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Zomato Unknown Status", "code": "ZUS"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Unknown Status Meal", "sku": "ZOM-UNKNOWN-MEAL", "price": "125.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "zomato",
            "external_order_id": "ZOM-UNKNOWN-1",
            "customer_name": "Unknown Status Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200

    rider_update = client.post(
        f"/api/v1/integrations/zomato/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "ZOM-UNKNOWN-1",
                "status": "rider_assigned",
                "rider": {"name": "Meera", "phone": "+919800000001"},
            }
        },
    )
    assert rider_update.status_code == 201
    updated = rider_update.json()["data"]
    assert updated["status"] == "accepted"
    assert updated["rider_name"] == "Meera"
    assert updated["rider_phone"] == "+919800000001"
    assert updated["total"] == "125.00"


def test_online_delivery_webhook_blank_status_preserves_existing_delivery_status(client, owner_auth, monkeypatch):
    class FakeProviderResponse:
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted"}

    monkeypatch.setenv("SWIGGY_API_BASE_URL", "https://swiggy.test")
    monkeypatch.setenv("SWIGGY_API_TOKEN", "swiggy-token")
    monkeypatch.setenv("SWIGGY_OUTLET_ID", "swiggy-outlet")
    monkeypatch.setenv("SWIGGY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: FakeProviderResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Swiggy Blank Status", "code": "SBS"}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "Blank Status Meal", "sku": "SWG-BLANK-MEAL", "price": "135.00", "tax_rate": "0.00"},
    ).json()["data"]
    intake = client.post(
        "/api/v1/online-delivery/orders",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "provider": "swiggy",
            "external_order_id": "SWG-BLANK-1",
            "customer_name": "Blank Status Guest",
            "payment_mode": "prepaid",
            "payment_status": "paid",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    delivery = intake.json()["data"]
    accepted = client.post(f"/api/v1/online-delivery/orders/{delivery['id']}/accept", headers=headers)
    assert accepted.status_code == 200

    rider_update = client.post(
        f"/api/v1/integrations/swiggy/online-delivery/webhook?branch_id={branch['id']}",
        headers={"x-korvexa-webhook-secret": "hook-secret"},
        json={
            "order": {
                "order_id": "SWG-BLANK-1",
                "status": "   ",
                "delivery_partner": {"name": "Asha", "phone": "+919800000002"},
            }
        },
    )
    assert rider_update.status_code == 201
    updated = rider_update.json()["data"]
    assert updated["status"] == "accepted"
    assert updated["rider_name"] == "Asha"
    assert updated["rider_phone"] == "+919800000002"
    assert updated["total"] == "135.00"


def test_qr_order_places_table_order_and_accepts_online_payment(client, owner_auth, monkeypatch):
    gateway_requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_request(method, url, **kwargs):
        gateway_requests.append({"method": method, "url": url, **kwargs})
        assert kwargs["auth"] == ("rzp_qr_key", "rzp_qr_secret")
        if method == "POST" and url.endswith("/v1/orders"):
            assert kwargs["json"]["amount"] == 12000
            return FakeResponse({"id": "order_qr_123", "amount": 12000, "currency": "INR", "status": "created"})
        if method == "GET" and url.endswith("/v1/payments/pay_qr_123"):
            return FakeResponse({
                "id": "pay_qr_123",
                "order_id": "order_qr_123",
                "amount": 12000,
                "currency": "INR",
                "status": "captured",
                "captured": True,
            })
        raise AssertionError(f"Unexpected Razorpay request: {method} {url}")

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_qr_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_qr_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "QR Branch", "code": "QRB"}).json()["data"]
    table = client.post("/api/v1/tables", headers=headers, json={"branch_id": branch["id"], "name": "T-QR", "capacity": 2}).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"branch_id": branch["id"], "name": "QR Meal", "price": "120.00", "tax_rate": "0.00"},
    ).json()["data"]

    menu = client.get(f"/api/v1/qr/menu?branch_id={branch['id']}&table_id={table['id']}")
    assert menu.status_code == 200
    assert menu.json()["data"]["table"]["name"] == "T-QR"
    assert menu.json()["data"]["products"][0]["name"] == "QR Meal"

    placed = client.post(
        "/api/v1/qr/orders",
        json={
            "branch_id": branch["id"],
            "table_id": table["id"],
            "customer_name": "QR Guest",
            "customer_phone": "+917000000001",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert placed.status_code == 201
    order = placed.json()["data"]
    assert order["order_type"] == "dine_in"
    assert order["status"] == "active"
    assert order["kds_status"] == "new"
    assert order["payment_status"] == "unpaid"

    gateway = client.post(f"/api/v1/qr/orders/{order['id']}/payments/gateway")
    assert gateway.status_code == 201
    assert gateway.json()["data"]["key_id"] == "rzp_qr_key"
    repeated_gateway = client.post(f"/api/v1/qr/orders/{order['id']}/payments/gateway")
    assert repeated_gateway.status_code == 201
    assert repeated_gateway.json()["data"]["gateway_order_id"] == gateway.json()["data"]["gateway_order_id"]
    assert repeated_gateway.json()["data"]["reused"] is True
    assert len(gateway_requests) == 1

    signature = hmac.new(
        b"rzp_qr_secret",
        b"order_qr_123|pay_qr_123",
        hashlib.sha256,
    ).hexdigest()
    verified = client.post(
        f"/api/v1/qr/orders/{order['id']}/payments/gateway/verify",
        json={
            "gateway_order_id": "order_qr_123",
            "gateway_payment_id": "pay_qr_123",
            "gateway_signature": signature,
        },
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["payment_status"] == "paid"
    assert len(gateway_requests) == 2


def test_qr_order_uses_server_prices_for_variants_and_addons(client, owner_auth):
    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Secure QR Branch", "code": "SQR"}).json()["data"]
    table = client.post(
        "/api/v1/tables",
        headers=headers,
        json={"branch_id": branch["id"], "name": "T-Secure", "capacity": 2},
    ).json()["data"]
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "name": "Secure QR Meal",
            "price": "120.00",
            "tax_rate": "0.00",
            "variants": [{"name": "Large", "price_delta": "40.00"}],
            "addons": [{"name": "Extra Chutney", "price": "20.00"}],
        },
    ).json()["data"]

    tampered = client.post(
        "/api/v1/qr/orders",
        json={
            "branch_id": branch["id"],
            "table_id": table["id"],
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "variant_name": "Large",
                    "addons": [{"name": "Extra Chutney", "price": "-1000.00"}],
                }
            ],
        },
    )

    assert tampered.status_code == 422

    placed = client.post(
        "/api/v1/qr/orders",
        json={
            "branch_id": branch["id"],
            "table_id": table["id"],
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "variant_name": "Large",
                    "addons": [{"name": "Extra Chutney"}],
                }
            ],
        },
    )

    assert placed.status_code == 201
    assert placed.json()["data"]["total"] == "180.00"


def test_razorpayx_payroll_payout_waits_for_processed_webhook(client, owner_auth, monkeypatch):
    payout_requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "pout_123", "status": "processing", "utr": "UTR123456", "mode": "UPI"}

    def fake_request(method, url, **kwargs):
        payout_requests.append({"method": method, "url": url, **kwargs})
        assert method == "POST"
        assert url.endswith("/v1/payouts")
        assert kwargs["auth"] == ("rzpx_key", "rzpx_secret")
        assert kwargs["headers"]["X-Payout-Idempotency"]
        payload = kwargs["json"]
        assert payload["account_number"] == "2323230066666666"
        assert payload["amount"] == 75000
        assert payload["mode"] == "UPI"
        assert payload["purpose"] == "salary"
        assert payload["fund_account"]["account_type"] == "vpa"
        assert payload["fund_account"]["vpa"]["address"] == "staff@upi"
        return FakeResponse()

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "payout_webhook_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Gateway Payroll", "code": "GWP"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-GW-01",
            "name": "Gateway Staff",
            "email": "gateway.staff@saffron.example.com",
            "phone": "+919999777777",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    clock_in = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_in.status_code == 200
    clock_out = client.post(
        "/api/v1/attendance/check-out",
        headers=headers,
        json={"employee_id": employee["id"], "shift_type": "General"},
    )
    assert clock_out.status_code == 200
    payroll = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    payroll_id = payroll.json()["data"]["items"][0]["id"]

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
            "recipient_phone": "+919999777777",
        },
    )
    assert paid.status_code == 200
    assert len(payout_requests) == 1

    payroll_after_pay = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    paid_row = payroll_after_pay.json()["data"]["items"][0]
    assert paid_row["status"] == "processing"
    assert paid_row["payment_mode"] == "upi"
    assert paid_row["payout_provider"] == "razorpayx"
    assert paid_row["payout_id"] == "pout_123"
    assert paid_row["payout_status"] == "processing"
    assert paid_row["payment_reference"] == "UTR123456"

    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpayx" not in metrics["payout_gateway_totals"]
    assert "upi" not in metrics["payout_method_totals"]

    duplicate = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["status"] == "processing"
    assert duplicate.json()["data"]["reused"] is True
    assert len(payout_requests) == 1

    body = json.dumps({
        "event": "payout.processed",
        "payload": {"payout": {"entity": {
            "id": "pout_123",
            "status": "processed",
            "amount": 75000,
            "currency": "INR",
            "utr": "UTR999999",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"payout_webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpayx/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    payroll_after_webhook = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    webhook_row = payroll_after_webhook.json()["data"]["items"][0]
    assert webhook_row["status"] == "paid"
    assert webhook_row["payout_status"] == "processed"
    assert webhook_row["payment_reference"] == "UTR999999"
    processed_metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert processed_metrics["payout_gateway_totals"]["razorpayx"] == "750.00"


def test_razorpayx_webhook_rejects_payment_events(client, monkeypatch):
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "payout_webhook_secret")
    body = json.dumps({
        "event": "payment.captured",
        "payload": {},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"payout_webhook_secret", body, hashlib.sha256).hexdigest()

    webhook = client.post(
        "/api/v1/integrations/razorpayx/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 422
    assert webhook.json()["errors"][0]["detail"] == "RazorpayX webhook only accepts payout events"


def test_razorpayx_payout_rejects_provider_amount_mismatch(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "pout_wrong_amount", "status": "processing", "amount": 50000, "currency": "INR", "mode": "UPI"}

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v1/payouts")
        assert kwargs["json"]["amount"] == 75000
        return FakeResponse()

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Payout Wrong Amount", "code": "PWA"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-RX-WRONG-AMOUNT",
            "name": "Wrong Amount Gateway Staff",
            "email": "wrong.amount.gateway.staff@saffron.example.com",
            "phone": "+919999777781",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    assert client.post("/api/v1/attendance/check-in", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    payroll_id = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]["id"]

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )

    assert paid.status_code == 502
    assert paid.json()["errors"][0]["detail"] == "Razorpay request failed: amount mismatch"
    payroll_after = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]
    assert payroll_after["status"] == "pending"
    assert payroll_after["payout_provider"] is None
    assert payroll_after["payout_id"] is None


def test_razorpayx_failed_payout_webhook_is_excluded_from_gateway_metrics(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "pout_failed_123", "status": "processing", "mode": "UPI"}

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "payout_webhook_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Failed Payout", "code": "GWF"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-GW-FAIL",
            "name": "Failed Gateway Staff",
            "email": "failed.gateway.staff@saffron.example.com",
            "phone": "+919999777778",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    assert client.post("/api/v1/attendance/check-in", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    payroll_id = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]["id"]

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )
    assert paid.status_code == 200
    before = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpayx" not in before["payout_gateway_totals"]
    assert "upi" not in before["payout_method_totals"]

    body = json.dumps({
        "event": "payout.failed",
        "payload": {"payout": {"entity": {
            "id": "pout_failed_123",
            "status": "failed",
            "amount": 75000,
            "currency": "INR",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"payout_webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpayx/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    after = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpayx" not in after["payout_gateway_totals"]
    assert "upi" not in after["payout_method_totals"]
    payroll_after_webhook = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    webhook_row = payroll_after_webhook.json()["data"]["items"][0]
    assert webhook_row["status"] == "pending"
    assert webhook_row["payout_status"] == "failed"


def test_razorpayx_processed_payout_webhook_rejects_amount_mismatch(client, owner_auth, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "pout_webhook_wrong_amount", "status": "processing", "amount": 75000, "mode": "UPI"}

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "payout_webhook_secret")
    monkeypatch.setattr("httpx.request", lambda *_args, **_kwargs: FakeResponse())

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Webhook Wrong Payout", "code": "WWP"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-RX-WEBHOOK-WRONG",
            "name": "Webhook Wrong Payout Staff",
            "email": "webhook.wrong.payout.staff@saffron.example.com",
            "phone": "+919999777782",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    assert client.post("/api/v1/attendance/check-in", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    payroll_id = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]["id"]

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )
    assert paid.status_code == 200

    body = json.dumps({
        "event": "payout.processed",
        "payload": {"payout": {"entity": {
            "id": "pout_webhook_wrong_amount",
            "status": "processed",
            "amount": 50000,
            "currency": "INR",
            "utr": "UTR-WRONG",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"payout_webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpayx/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 409
    assert webhook.json()["errors"][0]["detail"] == "Razorpay payout amount mismatch"
    payroll_after_webhook = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers)
    webhook_row = payroll_after_webhook.json()["data"]["items"][0]
    assert webhook_row["status"] == "processing"
    assert webhook_row["payout_status"] == "processing"
    assert webhook_row["payment_reference"] != "UTR-WRONG"
    metrics = client.get(f"/api/v1/reports/manager-dashboard?branch_id={branch['id']}", headers=headers).json()["data"]
    assert "razorpayx" not in metrics["payout_gateway_totals"]


def test_razorpayx_payout_rejects_placeholder_account_number(client, owner_auth, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("RazorpayX API must not be called with placeholder account number")

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "your_razorpayx_customer_identifier")
    monkeypatch.setattr("httpx.request", fail_if_called)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Placeholder Payout", "code": "PHP"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-RX-PLACEHOLDER",
            "name": "Placeholder Gateway Staff",
            "email": "placeholder.gateway.staff@saffron.example.com",
            "phone": "+919999777780",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    assert client.post("/api/v1/attendance/check-in", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    payroll_id = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]["id"]

    paid = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )

    assert paid.status_code == 503
    assert paid.json()["errors"][0]["detail"] == "RAZORPAYX_ACCOUNT_NUMBER is not configured"
    payroll_after = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]
    assert payroll_after["status"] == "pending"
    assert payroll_after["payout_provider"] is None
    assert payroll_after["payout_id"] is None


def test_razorpayx_failed_payout_can_retry_with_new_idempotency_key(client, owner_auth, monkeypatch):
    payout_ids = iter(["pout_retry_failed", "pout_retry_success"])
    payout_requests = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payout_id):
            self.payout_id = payout_id

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": self.payout_id, "status": "processing", "mode": "UPI"}

    def fake_request(method, url, **kwargs):
        payout_requests.append({"method": method, "url": url, **kwargs})
        assert method == "POST"
        assert url.endswith("/v1/payouts")
        return FakeResponse(next(payout_ids))

    monkeypatch.setenv("RAZORPAYX_KEY_ID", "rzpx_key")
    monkeypatch.setenv("RAZORPAYX_KEY_SECRET", "rzpx_secret")
    monkeypatch.setenv("RAZORPAYX_ACCOUNT_NUMBER", "2323230066666666")
    monkeypatch.setenv("RAZORPAYX_WEBHOOK_SECRET", "payout_webhook_secret")
    monkeypatch.setattr("httpx.request", fake_request)

    headers = owner_auth["headers"]
    branch = client.post("/api/v1/branches", headers=headers, json={"name": "Retry Payout", "code": "RXP"}).json()["data"]
    employee = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "branch_id": branch["id"],
            "employee_id": "EMP-RX-RETRY",
            "name": "Retry Gateway Staff",
            "email": "retry.gateway.staff@saffron.example.com",
            "phone": "+919999777779",
            "role": "cashier",
            "base_salary": 750,
        },
    ).json()["data"]
    assert client.post("/api/v1/attendance/check-in", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=headers, json={"employee_id": employee["id"], "shift_type": "General"}).status_code == 200
    payroll_id = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]["id"]

    first = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )
    assert first.status_code == 200

    body = json.dumps({
        "event": "payout.failed",
        "payload": {"payout": {"entity": {
            "id": "pout_retry_failed",
            "status": "failed",
            "amount": 75000,
            "currency": "INR",
            "failure_reason": "bank rejected",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(b"payout_webhook_secret", body, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/integrations/razorpayx/webhook",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    retry = client.post(
        f"/api/v1/payroll/{payroll_id}/pay",
        headers=headers,
        json={
            "payment_mode": "upi",
            "gateway_provider": "razorpayx",
            "recipient_upi": "staff@upi",
            "recipient_name": employee["name"],
        },
    )
    assert retry.status_code == 200
    assert len(payout_requests) == 2
    assert payout_requests[0]["headers"]["X-Payout-Idempotency"] != payout_requests[1]["headers"]["X-Payout-Idempotency"]

    payroll_after_retry = client.get(f"/api/v1/reports/payroll?branch_id={branch['id']}", headers=headers).json()["data"]["items"][0]
    assert payroll_after_retry["status"] == "processing"
    assert payroll_after_retry["payout_id"] == "pout_retry_success"
    assert payroll_after_retry["payout_status"] == "processing"
