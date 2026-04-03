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
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

# ── Database URL ─────────────────────────────────────────────────────────────
# Defaults to a local SQLite file inside the backend directory.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pawvibe.db")

# ── SQLAlchemy Engine ─────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    # Echo SQL statements to console only in development
    echo=os.getenv("ENVIRONMENT", "development") == "development",
    pool_pre_ping=True,
)

# ── SQLite Performance Optimizations ─────────────────────────────────────────
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Apply SQLite PRAGMAs on every new connection for best performance.
    """
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000") 
        cursor.close()

# ── Session Factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    """
    pass

# ── FastAPI Dependency: DB Session ────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.
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
    """
    # Note: Ensure models are imported here to register them with Base
    Base.metadata.create_all(bind=engine)

# ── Health Check ─────────────────────────────────────────────────────────────
def check_db_connection() -> bool:
    """
    Verify the database is reachable.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False