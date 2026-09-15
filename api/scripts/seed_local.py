"""A local Postgres holding a copy of the real setup, read from Supabase.

Run from `api/`, after starting an empty Postgres:

    docker run -d --name fb-agent-local-db -e POSTGRES_PASSWORD=local \
        -e POSTGRES_DB=fbagent -p 127.0.0.1:54320:5432 postgres:16
    uv run python scripts/seed_local.py --to postgresql+psycopg://postgres:local@127.0.0.1:54320/fbagent

Then run the API against it, with both variables set in the shell - a variable
in the environment outranks `.env`:

    $env:DATABASE_URL = "postgresql+psycopg://postgres:local@127.0.0.1:54320/fbagent"
    $env:SUPABASE_BUCKET = "fb-agent-media-dev"
    uv run uvicorn app.main:app --port 8000 --reload

A copy of the real Pages rather than sample rows, at the operator's choice
(2026-09-15): a fresh database with `seed_page.py`'s two Pages had nothing to
test a screen against - no feeds, no drafts, no pictures.

**Supabase's database is only read.** The source is `DATABASE_URL` from the
`.env` *file*, not the environment, so a shell already pointed at the local copy
still reads the real database - and it is only ever SELECTed. The target must be
a Postgres on this machine, or nothing runs.

**The pictures go into the dev bucket, and that is the safety, not a
convenience.** Rows hold bucket paths, and the app deletes the files a redraw
replaces and a deleted draft owned (`generate._discard`, `routes/drafts`,
`routes/pages`). A local API on the production bucket would delete production's
pictures for rows it had only copied. So the local API runs on
`fb-agent-media-dev`, and this copies exactly the files the copied rows point at:
upsert only, nothing deleted in either bucket.

Copied: the configuration whole - Pages, feeds, competitor assignments, layouts,
publishing times, post styles, the CTA template, saved posts - and a window of
the work: the newest drafts, the source items they were written from, and the
newest source items for the grids. Ids are kept, so every reference still joins,
and sequences are moved past them so new local rows do not collide. Not copied:
Shorts jobs, whose videos live in their own bucket.

The target is migrated first and must hold no Pages: ids are copied, so a second
run would collide. Remove the container and start again to reseed.

Still real from a local API: Metricool, Gemini and Unsplash. Publishing from the
copy publishes.
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.engine import Connection, Engine, make_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import media  # noqa: E402
from app.settings import API_DIR, settings  # noqa: E402

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

CONFIG_TABLES = (
    "page",
    "feed",
    "page_competitor",
    "page_layout",
    "page_time_slot",
    "prompt_template",
    "cta_template",
)
"""Copied whole, in this order: every foreign key among them points up the list."""

DRAFT_FILES = ("hero_image_path", "composed_image_path", "inset_image_path")
PAGE_FILES = ("avatar_image_path", "watermark_upload_path")


def require_local(url: str) -> None:
    """Refuse any target that is not a Postgres on this machine."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError(f"--to must be a postgresql URL, not {parsed.drivername}")
    if parsed.host not in LOCAL_HOSTS:
        raise ValueError(f"--to must be a database on this machine, not {parsed.host!r}")


def source_url() -> str:
    """`DATABASE_URL` from the `.env` file - deliberately not the environment."""
    url = dotenv_values(API_DIR.parent / ".env").get("DATABASE_URL") or ""
    if not url:
        raise SystemExit("No DATABASE_URL in .env to copy from.")
    if make_url(url).host in LOCAL_HOSTS:
        raise SystemExit(".env's DATABASE_URL is local - there is nothing real to copy from.")
    return url


def migrate(url: str) -> None:
    """`alembic upgrade head` on the target. `alembic/env.py` reads ALEMBIC_URL first."""
    from alembic import command
    from alembic.config import Config

    os.environ["ALEMBIC_URL"] = url
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _insert(target: Connection, table, rows: list[dict]) -> int:
    if rows:
        target.execute(table.insert(), [{k: v for k, v in row.items() if k in table.c} for row in rows])
    return len(rows)


def copy_rows(source: Engine, target: Engine, drafts: int, source_items: int) -> dict[str, int]:
    """Read from `source`, write to `target`, in one transaction on the target."""
    meta = MetaData()
    meta.reflect(bind=target)
    tables = meta.tables
    counts: dict[str, int] = {}

    with source.connect() as src, target.begin() as dst:
        for name in CONFIG_TABLES:
            rows = [dict(row._mapping) for row in src.execute(select(tables[name]))]
            counts[name] = _insert(dst, tables[name], rows)

        draft = tables["draft"]
        draft_rows = [
            dict(row._mapping)
            for row in src.execute(select(draft).order_by(draft.c.id.desc()).limit(drafts))
        ]

        item = tables["source_item"]
        # The items the copied drafts were written from, so the drawer can name
        # its source, plus the newest items so the grids have something in them.
        wanted = {row["source_item_id"] for row in draft_rows if row["source_item_id"]}
        wanted |= set(
            src.execute(select(item.c.id).order_by(item.c.id.desc()).limit(source_items)).scalars()
        )
        item_rows = (
            [dict(row._mapping) for row in src.execute(select(item).where(item.c.id.in_(wanted)))]
            if wanted
            else []
        )
        counts["source_item"] = _insert(dst, item, item_rows)
        counts["draft"] = _insert(dst, draft, draft_rows)

        copied = {row["id"] for row in draft_rows}
        saved_rows = [dict(row._mapping) for row in src.execute(select(tables["saved_post"]))]
        for row in saved_rows:
            if row.get("draft_id") not in copied:
                row["draft_id"] = None
        counts["saved_post"] = _insert(dst, tables["saved_post"], saved_rows)

        # Ids were copied, so each sequence is still at 1. Moved past the copied
        # rows, or the first draft made locally collides with one of them.
        for name in counts:
            dst.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f'COALESCE((SELECT MAX(id) FROM "{name}"), 1))'
                )
            )

    return counts


def copy_files(target: Engine, from_bucket: str, to_bucket: str) -> tuple[int, int]:
    """Every bucket file the copied rows point at, into the dev bucket. Never deletes."""
    paths: set[str] = set()
    with target.connect() as connection:
        for column in DRAFT_FILES:
            paths |= set(connection.execute(text(f"SELECT {column} FROM draft")).scalars())
        for column in PAGE_FILES:
            paths |= set(connection.execute(text(f"SELECT {column} FROM page")).scalars())
    # `assets/...` is a committed watermark in the repo, not a bucket object.
    stored_paths = sorted(path for path in paths if path and not path.startswith("assets/"))

    root = settings.supabase_url.rstrip("/")
    auth = {"Authorization": f"Bearer {settings.supabase_service_key}"}
    copied = missing = 0
    with httpx.Client(timeout=media.TIMEOUT) as client:
        for stored in stored_paths:
            got = client.get(f"{root}/storage/v1/object/{from_bucket}/{stored}", headers=auth)
            if got.status_code in (400, 404):
                # A row pointing at a file that is gone is production's state,
                # not this copy's problem - counted, not fatal.
                missing += 1
                continue
            got.raise_for_status()
            client.post(
                f"{root}/storage/v1/object/{to_bucket}/{stored}",
                content=got.content,
                headers={**auth, "Content-Type": media._content_type(stored), "x-upsert": "true"},
            ).raise_for_status()
            copied += 1
    return copied, missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--to", required=True, help="the local postgresql URL to fill")
    parser.add_argument("--drafts", type=int, default=50, help="newest drafts to copy")
    parser.add_argument("--source-items", type=int, default=500, help="newest source items to copy")
    parser.add_argument("--from-bucket", default="fb-agent-media")
    parser.add_argument("--to-bucket", default="fb-agent-media-dev")
    args = parser.parse_args()

    try:
        require_local(args.to)
    except ValueError as error:
        print(error)
        return 1
    if args.from_bucket == args.to_bucket:
        print("--from-bucket and --to-bucket are the same; the local copy needs its own.")
        return 1
    if not settings.supabase_url or not settings.supabase_service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set, so pictures cannot be copied.")
        return 1

    source_db = source_url()
    target_url = make_url(args.to)
    # Hosts only - never a URL, which carries the password.
    print(f"source   {make_url(source_db).host} (read only)")
    print(f"target   {target_url.host}:{target_url.port}/{target_url.database}")

    migrate(args.to)
    source = create_engine(source_db)
    target = create_engine(args.to)

    source_revision, target_revision = revision(source), revision(target)
    if source_revision != target_revision:
        print(
            f"Supabase is at {source_revision} and this checkout migrates to "
            f"{target_revision}. Deploy or pull first, so the tables match."
        )
        return 1
    with target.connect() as connection:
        if connection.execute(text("SELECT COUNT(*) FROM page")).scalar():
            print("The target already has Pages. Remove the container and start again to reseed.")
            return 1

    print("\nrows")
    for name, count in copy_rows(source, target, args.drafts, args.source_items).items():
        print(f"  {name:16} {count}")

    copied, missing = copy_files(target, args.from_bucket, args.to_bucket)
    print(f"\npictures  {copied} copied into {args.to_bucket}, {missing} missing in {args.from_bucket}")
    print(
        "\nRun the API against it with both set in the shell:\n"
        f'  $env:DATABASE_URL = "{args.to}"\n'
        f'  $env:SUPABASE_BUCKET = "{args.to_bucket}"\n'
        "  uv run uvicorn app.main:app --port 8000 --reload"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
