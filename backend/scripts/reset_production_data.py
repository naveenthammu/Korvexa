from __future__ import annotations

import argparse
from decimal import Decimal
import os

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import database
from app.models import Branch, Category, Product, RestaurantTable, Role, SecuritySettings, Tenant, User, UserRole
from app.security import hash_password


ROLE_NAMES = ("super_admin", "platform_admin", "tenant_owner", "manager", "cashier", "waiter", "kitchen_staff", "accountant")
RESET_CONFIRMATION = "RESET-KORVEXA-PRODUCTION-DATA"


def item(name: str, sku: str, price: str, description: str, *, variants: list[dict] | None = None, addons: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "sku": sku,
        "price": price,
        "tax_rate": "5.00",
        "description": description,
        "variants": variants or [],
        "addons": addons or [],
    }


MARKET_MENU = (
    {
        "name": "Starters",
        "items": (
            item("Crispy Corn Pepper Salt", "STR-CRN-001", "229.00", "Golden sweet corn tossed with peppers, spring onion and mild spices."),
            item("Paneer Tikka", "STR-PNR-002", "279.00", "Char-grilled cottage cheese, onion and capsicum with mint chutney.", addons=[{"name": "Extra Mint Chutney", "price": 20}]),
            item("Chicken 65", "STR-CHK-003", "299.00", "South Indian-style fried chicken finished with curry leaves and chilli."),
            item("Chilli Chicken", "STR-CHK-004", "309.00", "Wok-tossed chicken with onion, capsicum and house chilli sauce.", variants=[{"name": "Dry", "price_delta": 0}, {"name": "Gravy", "price_delta": 20}]),
            item("Andhra Fish Fry", "STR-FSH-005", "369.00", "Seer fish marinated with Andhra spices and shallow fried."),
        ),
    },
    {
        "name": "South Indian",
        "items": (
            item("Steamed Idli", "STH-IDL-001", "89.00", "Three soft rice-lentil cakes served with sambar and two chutneys."),
            item("Masala Dosa", "STH-DSA-002", "149.00", "Crisp dosa filled with potato masala, served with sambar and chutneys."),
            item("Ghee Karam Dosa", "STH-DSA-003", "179.00", "Dosa layered with ghee and Andhra karam podi."),
            item("Pesarattu Upma", "STH-PST-004", "169.00", "Green gram crepe filled with upma, ginger chutney and sambar."),
            item("Vegetable Uttapam", "STH-UTP-005", "159.00", "Thick fermented pancake topped with onion, tomato and capsicum."),
        ),
    },
    {
        "name": "Biryani & Rice",
        "items": (
            item("Vegetable Dum Biryani", "BRY-VEG-001", "239.00", "Basmati rice dum-cooked with garden vegetables, herbs and whole spices.", variants=[{"name": "Regular", "price_delta": 0}, {"name": "Family Pack", "price_delta": 360}]),
            item("Paneer Tikka Biryani", "BRY-PNR-002", "289.00", "Smoky paneer tikka layered with aromatic basmati rice."),
            item("Hyderabadi Chicken Dum Biryani", "BRY-CHK-003", "319.00", "Marinated chicken and basmati rice slow-cooked on dum.", variants=[{"name": "Regular", "price_delta": 0}, {"name": "Family Pack", "price_delta": 450}]),
            item("Korvexa Special Chicken Biryani", "BRY-CHK-004", "369.00", "House special biryani with boneless chicken, fried onion and boiled egg."),
            item("Mutton Dum Biryani", "BRY-MTN-005", "429.00", "Tender mutton and aged basmati rice sealed and cooked on dum."),
            item("Jeera Rice", "BRY-RCE-006", "189.00", "Basmati rice tempered with cumin, ghee and fresh coriander."),
        ),
    },
    {
        "name": "Indian Mains",
        "items": (
            item("Dal Tadka", "MAN-DAL-001", "219.00", "Yellow lentils tempered with cumin, garlic, tomato and chilli."),
            item("Kadai Vegetable", "MAN-VEG-002", "259.00", "Seasonal vegetables and capsicum in a coarse kadai masala."),
            item("Paneer Butter Masala", "MAN-PNR-003", "309.00", "Cottage cheese in a smooth tomato, butter and cashew gravy."),
            item("Butter Chicken", "MAN-CHK-004", "369.00", "Tandoori chicken simmered in a creamy tomato and butter gravy."),
            item("Andhra Chicken Curry", "MAN-CHK-005", "349.00", "Country-style chicken curry with roasted Andhra spices."),
            item("Mutton Rogan Josh", "MAN-MTN-006", "449.00", "Slow-cooked mutton in an aromatic Kashmiri-style gravy."),
        ),
    },
    {
        "name": "Breads",
        "items": (
            item("Tandoori Roti", "BRD-ROT-001", "49.00", "Whole-wheat bread baked in the tandoor."),
            item("Plain Naan", "BRD-NAN-002", "69.00", "Soft refined-flour bread baked in the tandoor."),
            item("Butter Naan", "BRD-NAN-003", "79.00", "Tandoor-baked naan finished with butter."),
            item("Garlic Naan", "BRD-NAN-004", "89.00", "Naan topped with garlic, coriander and butter."),
            item("Laccha Paratha", "BRD-PAR-005", "79.00", "Layered whole-wheat bread baked until crisp and flaky."),
        ),
    },
    {
        "name": "Desserts",
        "items": (
            item("Gulab Jamun", "DST-GLB-001", "99.00", "Two warm milk-solid dumplings in cardamom sugar syrup."),
            item("Rasmalai", "DST-RSM-002", "149.00", "Soft chenna patties in saffron and cardamom milk."),
            item("Matka Kulfi", "DST-KLF-003", "139.00", "Traditional slow-reduced milk kulfi served in an earthen cup."),
            item("Brownie with Ice Cream", "DST-BRN-004", "189.00", "Warm chocolate brownie with vanilla ice cream and chocolate sauce."),
            item("Semiya Payasam", "DST-PAY-005", "119.00", "Vermicelli pudding with milk, cardamom, cashew and raisins."),
        ),
    },
    {
        "name": "Beverages",
        "items": (
            item("Masala Chai", "BEV-TEA-001", "59.00", "Fresh-brewed tea with milk and warming spices."),
            item("Filter Coffee", "BEV-CFE-002", "69.00", "South Indian filter coffee served with frothy milk."),
            item("Fresh Lime Soda", "BEV-LIM-003", "109.00", "Fresh lime with chilled soda.", variants=[{"name": "Sweet", "price_delta": 0}, {"name": "Salt", "price_delta": 0}, {"name": "Mixed", "price_delta": 0}]),
            item("Sweet Lassi", "BEV-LAS-004", "129.00", "Chilled yoghurt drink lightly sweetened and churned until smooth."),
            item("Cold Coffee", "BEV-CFE-005", "179.00", "Chilled coffee blended with milk and ice cream."),
            item("Packaged Water", "BEV-WTR-006", "30.00", "One litre packaged drinking water."),
        ),
    },
)


def truncate_application_data(session: Session) -> None:
    table_names = [name for name in inspect(session.get_bind()).get_table_names() if name != "alembic_version"]
    if not table_names:
        return
    preparer = session.get_bind().dialect.identifier_preparer
    quoted_tables = ", ".join(preparer.quote(name) for name in sorted(table_names))
    session.execute(text(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE"))


def seed_baseline(session: Session, email: str, password: str) -> dict[str, int | str]:
    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("The production reset command requires PostgreSQL")
    if len(password) < 8:
        raise ValueError("Super user password must contain at least 8 characters")

    truncate_application_data(session)

    tenant = Tenant(
        name="Korvexa Hospitality",
        status="active",
        subscription_plan="enterprise",
        settings={"currency": "INR", "timezone": "Asia/Kolkata"},
    )
    session.add(tenant)
    session.flush()

    branch = Branch(
        tenant_id=tenant.id,
        name="Korvexa Central",
        code="KOR-CENTRAL",
        address="Primary Outlet, India",
        settings={"currency": "INR", "timezone": "Asia/Kolkata", "table_floors": ["Main Hall", "Family Section"]},
    )
    session.add(branch)
    session.flush()

    roles = {name: Role(tenant_id=tenant.id, name=name) for name in ROLE_NAMES}
    session.add_all(roles.values())
    session.flush()

    super_user = User(
        tenant_id=tenant.id,
        name="Korvexa Super Admin",
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role="super_admin",
        active=True,
        custom_permissions={},
    )
    session.add(super_user)
    session.flush()
    session.add(UserRole(tenant_id=tenant.id, user_id=super_user.id, role_id=roles["super_admin"].id))
    session.add(
        SecuritySettings(
            tenant_id=tenant.id,
            password_min_length=8,
            session_timeout_minutes=60,
            multi_device_login=False,
            two_factor_auth=False,
            login_attempts_threshold=5,
        )
    )

    product_count = 0
    for category_data in MARKET_MENU:
        category = Category(tenant_id=tenant.id, branch_id=branch.id, name=category_data["name"], active=True)
        session.add(category)
        session.flush()
        for product_data in category_data["items"]:
            session.add(
                Product(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    category_id=category.id,
                    name=product_data["name"],
                    description=product_data["description"],
                    sku=product_data["sku"],
                    price=Decimal(product_data["price"]),
                    tax_rate=Decimal(product_data["tax_rate"]),
                    variants=product_data["variants"],
                    addons=product_data["addons"],
                    combo_items=[],
                    available=True,
                    active=True,
                )
            )
            product_count += 1

    table_layout = (("Main Hall", 8), ("Family Section", 4))
    table_number = 1
    for floor_name, count in table_layout:
        for _ in range(count):
            session.add(
                RestaurantTable(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    name=f"T{table_number:02d}",
                    capacity=4 if floor_name == "Main Hall" else 6,
                    status="available",
                    floor_area=floor_name,
                )
            )
            table_number += 1

    session.commit()
    return {
        "tenant_id": tenant.id,
        "branch_id": branch.id,
        "users": 1,
        "categories": len(MARKET_MENU),
        "products": product_count,
        "tables": table_number - 1,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear Korvexa application data and seed the production baseline.")
    parser.add_argument("--confirm", required=True, help=f"Required safety phrase: {RESET_CONFIRMATION}")
    parser.add_argument("--email", default=os.getenv("KORVEXA_SUPERUSER_EMAIL"), required=not os.getenv("KORVEXA_SUPERUSER_EMAIL"))
    parser.add_argument("--password", default=os.getenv("KORVEXA_SUPERUSER_PASSWORD"), required=not os.getenv("KORVEXA_SUPERUSER_PASSWORD"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.confirm != RESET_CONFIRMATION:
        raise SystemExit("Reset confirmation phrase did not match; no data was changed.")
    with Session(database.engine) as session:
        result = seed_baseline(session, args.email, args.password)
    print(
        "Korvexa baseline created: "
        f"{result['users']} user, {result['categories']} categories, "
        f"{result['products']} products, {result['tables']} tables."
    )


if __name__ == "__main__":
    main()
