"""Engine/session factory. Reads DATABASE_URL from the environment; falls
back to a local SQLite file so the app runs with zero setup in demo mode."""
from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./equitylens.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (no-op if they exist)."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency form (yields, doesn't auto-commit on error)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
