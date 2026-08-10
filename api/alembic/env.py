"""Alembic's entry point. Reads `DATABASE_URL` from settings, not from alembic.ini.

`alembic.ini` ships a `sqlalchemy.url` line by default; ours is blank on purpose.
The connection string carries a password, and a second place to write it down is
a second place to leak it — `.env` is gitignored, `alembic.ini` is not.

`ALEMBIC_URL` overrides it, for the one job that cannot use the real database:
autogenerating a baseline. Autogenerate diffs the models against whatever it is
pointed at, so run against Supabase — which already has the tables — it produces
an empty migration. Pointing it at a throwaway file gives the real `create_table`
calls, and `alembic stamp head` then tells the live database it is already there.
"""

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: F401,E402  — registers the tables on the metadata
from app.settings import settings  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    # Skipped when `db.init_db` runs this in-process: `fileConfig` reconfigures
    # root logging, and it would otherwise silence uvicorn's own handlers for
    # the rest of the process's life.
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _url() -> str:
    url = os.environ.get("ALEMBIC_URL") or settings.database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set, and no ALEMBIC_URL was given.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Off by default, and worth having: without it a column whose type
            # changed in models.py autogenerates as no change at all.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
