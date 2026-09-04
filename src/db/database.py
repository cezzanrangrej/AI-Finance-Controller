"""
Database engine configuration and session management.

Supports SQLite local file fallback by default, or PostgreSQL when DATABASE_URL is set.
"""

import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import settings

logger = logging.getLogger(__name__)

# Database URL from settings or SQLite default
DATABASE_URL = settings.database_url or "sqlite:///./data/finance_controller.db"

# Convert postgres:// to postgresql:// if needed for SQLAlchemy 2.0
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure directory exists for SQLite
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for obtaining a database session."""
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



#: Additive columns applied to existing SQLite databases on startup, as
#: (table, column, DDL type). create_all() only creates missing *tables*, so a
#: database created before a column was added would otherwise keep failing
#: inserts with "table has no column named ...".
_ADDITIVE_COLUMNS = (
    ("transaction_results", "source_provenance_json", "TEXT"),
    ("runs", "llm_degraded", "BOOLEAN NOT NULL DEFAULT 0"),
    ("runs", "llm_degraded_reason", "VARCHAR(500)"),
)


def init_db():
    """Initialises database tables and applies lightweight schema updates."""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name != "sqlite":
        return
    try:
        with engine.begin() as conn:
            for table, column, ddl_type in _ADDITIVE_COLUMNS:
                res = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                col_names = [r[1] for r in res]
                # An empty result means the table does not exist yet, in which
                # case create_all() will build it with the column already present.
                if col_names and column not in col_names:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    except Exception:
        logger.exception("Lightweight schema update failed; continuing with existing schema.")

