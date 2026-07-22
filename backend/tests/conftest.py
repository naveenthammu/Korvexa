import os
from pathlib import Path
import re
import sys

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://korvexa:korvexa@localhost:5432/korvexa"
DEFAULT_TEST_SCHEMA = "korvexa_test"


def normalized_postgresql_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    if make_url(value).get_backend_name() != "postgresql":
        raise RuntimeError("Tests require a PostgreSQL TEST_DATABASE_URL")
    return value


def configured_test_database_url() -> str:
    if os.getenv("TEST_DATABASE_URL"):
        return normalized_postgresql_url(os.environ["TEST_DATABASE_URL"])
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            if raw_line.strip().startswith("TEST_DATABASE_URL="):
                return normalized_postgresql_url(raw_line.split("=", 1)[1])
    return DEFAULT_TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def postgres_test_schema():
    database_url = configured_test_database_url()
    schema_name = os.getenv("TEST_DATABASE_SCHEMA", DEFAULT_TEST_SCHEMA).strip()
    if not re.fullmatch(r"korvexa_test(?:_[a-z0-9_]+)?", schema_name):
        raise RuntimeError("TEST_DATABASE_SCHEMA must start with 'korvexa_test'")

    original_database_url = os.environ.get("DATABASE_URL")
    original_pgoptions = os.environ.get("PGOPTIONS")
    admin_engine = create_engine(database_url, pool_pre_ping=True, future=True)
    quoted_schema = admin_engine.dialect.identifier_preparer.quote(schema_name)
    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))

    os.environ["DATABASE_URL"] = database_url
    os.environ["PGOPTIONS"] = f"-c search_path={schema_name}"
    os.environ["JWT_SECRET"] = "test-secret-not-for-production"
    os.environ["ENVIRONMENT"] = "test"

    from app import database

    database.reset_engine_from_env()
    alembic_config = Config(str(ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(alembic_config, "head")

    yield

    database.engine.dispose()
    if original_pgoptions is None:
        os.environ.pop("PGOPTIONS", None)
    else:
        os.environ["PGOPTIONS"] = original_pgoptions
    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"))
    admin_engine.dispose()
    if original_database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original_database_url


def clear_test_data() -> None:
    from app import database

    database.reset_engine_from_env()
    with database.engine.begin() as connection:
        table_names = [name for name in inspect(connection).get_table_names() if name != "alembic_version"]
        if not table_names:
            return
        preparer = connection.dialect.identifier_preparer
        tables = ", ".join(preparer.quote(name) for name in sorted(table_names))
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def client(postgres_test_schema):
    clear_test_data()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def owner_auth(client):
    response = client.post(
        "/auth/register",
        json={
            "tenant_name": "Saffron Table",
            "owner_name": "Asha Rao",
            "email": "owner@saffron.example.com",
            "password": "ChangeMe123!",
            "phone": "+919999000001",
        },
    )
    assert response.status_code == 201
    data = response.json()
    return {
        "tenant_id": data["tenant"]["id"],
        "user_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }
