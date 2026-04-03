"""
database.py – Database Engine, Session, and Base for PawVibe
─────────────────────────────────────────────────────────────
Sets up:
  - SQLAlchemy engine (SQLite, with WAL mode for concurrency)
  - Session factory (scoped for request lifecycle)
  - Declarative Base (imported by all models)
  - Dependency injection helper `get_db` for FastAPI routes
"""

import os
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from dotenv import load_dotenv

# ── Load environment variables from .env ─────────────────────────────────────
load_dotenv()

# ── Database URL ─────────────────────────────────────────────────────────────
# Defaults to a local SQLite file inside the backend directory.
# For PostgreSQL in production: "postgresql://user:pass@host/dbname"
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pawvibe.db")

# ── SQLAlchemy Engine ─────────────────────────────────────────────────────────
# connect_args is SQLite-specific: enables multi-thread access (FastAPI is async)
# For PostgreSQL, remove connect_args entirely.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    # Echo SQL statements to console only in development
    echo=os.getenv("ENVIRONMENT", "development") == "development",
    # Connection pool configuration
    pool_pre_ping=True,   # Test connections before using from pool
)


# ── SQLite Performance Optimizations ─────────────────────────────────────────
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Apply SQLite PRAGMAs on every new connection for best performance:
      - WAL mode: allows concurrent reads while writing
      - Busy timeout: wait up to 5s instead of immediately failing on lock
      - Foreign keys: enforce referential integrity
      - Synchronous NORMAL: good balance of safety vs. speed
    """
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")   # 64MB page cache
        cursor.close()


# ── Session Factory ───────────────────────────────────────────────────────────
# autocommit=False: transactions must be committed explicitly (safer)
# autoflush=False:  we control when changes are flushed to the DB
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── Declarative Base ──────────────────────────────────────────────────────────
# All ORM models must inherit from this Base.
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    Inheriting from DeclarativeBase (SQLAlchemy 2.x style).
    """
    pass


# ── FastAPI Dependency: DB Session ────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.

    Usage in a route:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...

    Guarantees:
      - Session is always closed after the request completes
      - If an exception occurs, the session is rolled back via context manager
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Utility: Create All Tables ────────────────────────────────────────────────
def create_tables() -> None:
    """
    Create all tables defined in models.py.
    Called during app startup if Alembic is not being used.
    In production, prefer `alembic upgrade head` instead.
    """
    from . import models   # noqa: F401  – import to register models with Base
    Base.metadata.create_all(bind=engine)


# ── Health Check ─────────────────────────────────────────────────────────────
def check_db_connection() -> bool:
    """
    Verify the database is reachable. Used in the health-check endpoint.
    Returns True if connection succeeds, False otherwise.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
