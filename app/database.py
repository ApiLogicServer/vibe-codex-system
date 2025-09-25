from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")


def _create_engine(url: str = DATABASE_URL):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, echo=False, connect_args=connect_args)


engine = _create_engine()
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
)


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


@contextmanager
def db_session() -> Iterator[sessionmaker]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables for the metadata if they do not exist."""
    from . import models  # noqa: F401  # ensure models are imported

    Base.metadata.create_all(bind=engine)
