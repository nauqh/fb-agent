"""The local seed's one guard that must never break: it writes only to this machine.

The rest of `scripts/seed_local.py` is a copy between two live Postgres servers
and a bucket, and was checked by running it. This is the part a typo would turn
into writing rows into production.
"""

import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parent.parent / "scripts" / "seed_local.py"
_spec = importlib.util.spec_from_file_location("seed_local", _path)
seed_local = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_local)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres:local@127.0.0.1:54320/fbagent",
        "postgresql+psycopg://postgres:local@localhost:5432/fbagent",
    ],
)
def test_a_postgres_on_this_machine_is_accepted(url):
    seed_local.require_local(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres.ref:secret@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres",
        "postgresql+psycopg://user:secret@db.example.com:5432/fbagent",
        "sqlite:///local.db",
    ],
)
def test_anything_else_is_refused(url):
    with pytest.raises(ValueError):
        seed_local.require_local(url)
