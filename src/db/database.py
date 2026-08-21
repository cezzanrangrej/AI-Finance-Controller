"""
Database engine configuration and session management.

Supports SQLite local file fallback by default, or PostgreSQL when DATABASE_URL is set.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Database URL from env or SQLite default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/finance_controller.db")

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



def init_db():
    """Initialises database tables."""
    Base.metadata.create_all(bind=engine)
