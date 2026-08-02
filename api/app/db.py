"""SQLite, stock settings, one file.

No journal-mode tuning: v1 is one operator on local disk, and the workload
never justified it. If two processes ever contend badly, WAL is one line.

No migration tool either. `init_db()` calls `create_all`, which creates missing
tables and *never alters existing ones* — a schema change means deleting the db
file and letting it rebuild. That is the intended workflow for v1; Alembic
arrives with the move to Supabase, when rows start being worth keeping.
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

    Neither of these is a performance knob:

    `foreign_keys` is off by default in SQLite and is per-connection. Without
    it, every foreign key declared in models.py is decorative — a draft can
    point at a page id that does not exist and nothing complains.

    `busy_timeout` defaults to 0, meaning a locked database fails instantly
    rather than waiting. Five seconds covers the one real case: a script (the
    Phase 1 page seed) running while the dev server is up.
    """
    cursor = dbapi_connection.cursor()
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
