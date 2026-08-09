"""Copy every picture a Draft points at from one bucket into another.

    uv run python scripts/seed_media_bucket.py --from fb-agent-media-dev --to fb-agent-media
    uv run python scripts/seed_media_bucket.py --from ... --to ... --copy

Run it from `api/`, like `seed_page.py`.

This replaces `migrate_media_to_supabase.py`, which read `api/media/` and moved
files off local disk. That directory is gone and so is `settings.media_root`, so
the only remaining copy of anything is in a bucket — which makes the job
bucket-to-bucket. It exists for one moment: seeding production the first time a
database reaches it.

**No row is rewritten.** A stored path is `<yyyy-mm>/<name>` and means the same
thing in either bucket, so the same rows work against whichever bucket
`SUPABASE_BUCKET` names. That is the whole reason rows hold a path and not a URL.

Read → write → verify, and it never deletes from the source. Re-runnable:
uploads use `x-upsert`, and verification fetches the destination's *public* URL
unauthenticated, the way Facebook will.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import media  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402
from app.models import Draft  # noqa: E402
from app.settings import settings  # noqa: E402

COLUMNS = ("hero_image_path", "composed_image_path", "inset_image_path")


def stored_paths() -> list[tuple[int, str]]:
    """Every (draft id, path) the database still points at."""
    init_db()
    found: list[tuple[int, str]] = []
    with Session(get_engine()) as session:
        for draft in session.exec(select(Draft)).all():
            for column in COLUMNS:
                path = getattr(draft, column)
                if path:
                    found.append((draft.id or 0, path))
    return found


def object_url(bucket: str, stored: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{stored}"


def public_url(bucket: str, stored: str) -> str:
    root = settings.supabase_url.rstrip("/")
    return f"{root}/storage/v1/object/public/{bucket}/{stored}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("--to", dest="target", required=True)
    parser.add_argument("--copy", action="store_true", help="actually copy")
    args = parser.parse_args()

    if args.source == args.target:
        print("Source and target are the same bucket.")
        return 1
    if not settings.supabase_url or not settings.supabase_service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.")
        return 1

    paths = stored_paths()
    print(f"{args.source} -> {args.target}")
    print(f"{len(paths)} paths on {len({d for d, _ in paths})} drafts\n")

    if not args.copy:
        print("Dry run. Re-run with --copy.")
        return 0

    auth = {"Authorization": f"Bearer {settings.supabase_service_key}"}
    failed = 0

    with httpx.Client(timeout=media.TIMEOUT) as client:
        for draft_id, stored in paths:
            try:
                got = client.get(object_url(args.source, stored), headers=auth)
                got.raise_for_status()
                data = got.content

                put = client.post(
                    object_url(args.target, stored),
                    content=data,
                    headers={
                        **auth,
                        "Content-Type": media._content_type(stored),
                        "x-upsert": "true",
                    },
                )
                put.raise_for_status()

                # Unauthenticated, and the size checked as well as the status: a
                # bucket will serve an error document with a 200 if the path is
                # wrong in the right way.
                back = client.get(public_url(args.target, stored))
                back.raise_for_status()
                if len(back.content) != len(data):
                    raise RuntimeError(
                        f"copied {len(data)} bytes, fetched {len(back.content)}"
                    )
            except Exception as error:  # noqa: BLE001 — report all, stop for none
                failed += 1
                print(f"  FAILED  draft {draft_id}  {stored}  {error}")
                continue

            print(f"  copied  draft {draft_id}  {stored}  ({len(data)} bytes)")

    print(
        f"\n{failed} failed."
        if failed
        else f"\nAll {len(paths)} verified in {args.target}. Nothing was deleted from "
        f"{args.source}."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
