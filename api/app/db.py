"""Supabase Postgres, one connection URL. There is no other backend.

The local SQLite file is gone — migrated to Supabase on 2026-08-10, 2 pages /
954 source items / 6 drafts, ids preserved. It was right for a laptop-only v1
and wrong the moment anything deployed: Railway's filesystem is ephemeral, so
every redeploy dropped the drafts while their pictures stayed in the bucket as
orphans.

`get_engine` refuses a non-Postgres URL rather than quietly building an engine
for it. That is the whole reason this module is short: with two backends, every
question about behaviour had to be asked twice, and the enum bug that shipped
into review — a column that round-tripped as `str` on one and as the enum on the
other — was invisible precisely because the two disagreed.

The test suite still runs on a throwaway SQLite file, but it builds that engine
itself (`tests/conftest.py`) and assigns `_engine` directly. So SQLite is a
testing convenience with no representation in the app's own configuration, and
`DATABASE_URL` has exactly one legal shape.

Still no migration tool. `init_db()` calls `create_all`, which creates missing
tables and **never alters existing ones**, so a schema change is a manual
`ALTER TABLE` — as the inset columns already were. Deliberate, and the cost is
now higher than it was: Postgres holds rows worth keeping, so "delete the file
and let it rebuild" is no longer the escape hatch it was on SQLite.
"""

from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  — registers tables on SQLModel.metadata
from app.settings import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. There is no local database to fall "
                "back to — see /health, which names it as a missing secret."
            )
        if not url.startswith("postgresql"):
            # Loud, because the quiet version of this is a second database
            # nobody meant to create. A typo'd scheme used to be a working app
            # pointed at an empty SQLite file.
            raise RuntimeError(
                f"DATABASE_URL must be a postgresql:// URL; got {url.split(':', 1)[0]}://"
            )

        _engine = create_engine(
            url,
            echo=settings.sql_echo,
            # Supabase's pooler closes idle connections on its own, and a dead
            # one is handed out as a live one — `pool_pre_ping` costs a round
            # trip on checkout and turns that into a reconnect rather than an
            # error on the first query after an idle spell.
            pool_pre_ping=True,
            # One uvicorn, one replica (`generate.sweep_stranded` depends on
            # exactly one writer). Small pool, recycled well inside the pooler's
            # own idle timeout.
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
        )
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency. One session per request."""
    with Session(get_engine()) as session:
        yield session
