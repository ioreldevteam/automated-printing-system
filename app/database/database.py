"""Database engine/session management (Section 83).

Uses SQLite with WAL mode and foreign keys enabled. The application must never
treat in-memory state as authoritative -- every module that changes production
state does so inside a transaction against this database.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Multiple worker threads (ANSER/Zebra/monitor) write concurrently; let
    # SQLite wait for the writer lock instead of failing immediately with
    # "database is locked".
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def init_db(db_path: str) -> Engine:
    """Create the engine, ensure the parent directory exists, and create any
    tables that are missing. Safe to call repeatedly (idempotent)."""
    global _engine, _SessionFactory

    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path.as_posix()}"
    else:
        url = "sqlite:///:memory:"

    _engine = create_engine(url, future=True, connect_args={"timeout": 30})
    Base.metadata.create_all(_engine)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database has not been initialized. Call init_db() first.")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope. Commits on success, rolls back on error."""
    if _SessionFactory is None:
        raise RuntimeError("Database has not been initialized. Call init_db() first.")
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
