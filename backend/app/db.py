"""SQLAlchemy 2.0 engine/session setup for the ECDAT backend.

Reads DATABASE_URL from env (default to a local sqlite file for testability
without Postgres running yet).
"""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, scoped_session, sessionmaker

Base = declarative_base()

_db_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
_engine = create_engine(_db_url, future=True, echo=False)


_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine, future=True)
_db_session = scoped_session(_session_factory)


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for dependency injection."""
    session = _db_session()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (Base.metadata.create_all) — for quick bootstrapping."""
    Base.metadata.create_all(_engine)


__all__ = ["Base", "get_db", "init_db", "session", "engine"]

session = _db_session
engine = _engine