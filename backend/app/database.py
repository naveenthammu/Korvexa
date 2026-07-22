from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


load_env_file()


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use PostgreSQL with the psycopg driver")
    return url


def configured_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return normalize_database_url(url)


def make_engine():
    return create_engine(
        configured_database_url(),
        pool_pre_ping=True,
        pool_recycle=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")),
        pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
        future=True,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def reset_engine_from_env() -> None:
    global engine, SessionLocal
    engine = make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
