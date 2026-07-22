from decimal import Decimal

import pytest


def test_database_url_accepts_postgresql_and_rejects_other_engines():
    from app.database import normalize_database_url

    assert (
        normalize_database_url("postgresql://user:pass@db.example.com/korvexa")
        == "postgresql+psycopg://user:pass@db.example.com/korvexa"
    )
    assert (
        normalize_database_url("postgres://user:pass@db.example.com/korvexa")
        == "postgresql+psycopg://user:pass@db.example.com/korvexa"
    )

    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_database_url("mysql://user:pass@db.example.com/korvexa")


def test_cors_origins_come_from_configuration(monkeypatch):
    from app.main import configured_cors_origins

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://pos.example.com ")

    assert configured_cors_origins() == ["http://localhost:5173", "https://pos.example.com"]


def test_production_cors_rejects_wildcard(monkeypatch):
    from app.main import configured_cors_origins

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        configured_cors_origins()


def test_market_menu_seed_is_balanced_and_production_safe():
    from scripts.reset_production_data import MARKET_MENU

    assert 5 <= len(MARKET_MENU) <= 8
    assert all(4 <= len(category["items"]) <= 7 for category in MARKET_MENU)

    items = [item for category in MARKET_MENU for item in category["items"]]
    skus = [item["sku"] for item in items]

    assert len(items) >= 30
    assert len(skus) == len(set(skus))
    assert all(item["name"].strip() for item in items)
    assert all(item["description"].strip() for item in items)
    assert all(Decimal(item["price"]) > 0 for item in items)
    assert all(Decimal(item["tax_rate"]) == Decimal("5.00") for item in items)


def test_migrations_produce_the_complete_postgresql_schema(client):
    from sqlalchemy import inspect

    from app.database import Base, engine

    assert engine.dialect.name == "postgresql"
    schema = inspect(engine)
    assert set(Base.metadata.tables) <= set(schema.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        migrated_columns = {column["name"] for column in schema.get_columns(table_name)}
        assert set(table.columns.keys()) <= migrated_columns
