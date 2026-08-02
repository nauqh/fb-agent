"""SQLite, WAL mode, one file.

There is no migration tool. `init_db()` calls `create_all`, which creates
missing tables and *never alters existing ones* — during v1 a schema change
means deleting the db file. That is acceptable while there is one operator and
no data worth keeping; the moment production rows exist, add Alembic.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  — registers tables on SQLModel.metadata
from app.settings import settings

_engine: Engine | None = None


def _configure_sqlite(dbapi_connection, _record) -> None:
    """Applied to every connection, not just the first.

    WAL survives in the file header, but `foreign_keys` is per-connection and
    off by default — without this, every FK in models.py is decorative.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        path = Path(settings.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{path}",
            # FastAPI runs background tasks on a different thread to the request
            # that spawned them, and a generate run outlives its request.
            connect_args={"check_same_thread": False},
            echo=settings.sql_echo,
        )
        event.listen(_engine, "connect", _configure_sqlite)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency. One session per request."""
    with Session(get_engine()) as session:
        yield session
