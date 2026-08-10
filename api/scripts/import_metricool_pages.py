"""Create a Page for every Metricool brand that has a Facebook page connected.

    uv run python scripts/import_metricool_pages.py --dry-run
    uv run python scripts/import_metricool_pages.py

Separate from `seed_page.py`, which carries two hand-checked rows with their
watermarks and exists to stand up a fresh database. This one reads whatever the
account currently has, so it is a sync rather than a seed and its output depends
on Metricool rather than on the file.

Idempotent by `facebook_page_id`, which is unique on `page` and is the same
identifier Metricool reports. A brand already imported is skipped, so this can
be re-run after connecting a new page.

**A brand with no Facebook page is skipped**, not imported with a placeholder.
`facebook_page_id` is what `publish` targets and what the competitor join reads;
a Page carrying a fake one would look configured and fail at publish time.

Imported Pages have **no watermark and no avatar**. That is legal — the column
is nullable and null means "render the page name as text" — but it is a
deliberate gap rather than a finished state: the composite will print the name
where the logo belongs until someone commits an asset and points the row at it.
"""

import argparse
import sys
from pathlib import Path

import httpx
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_engine
from app.models import Page
from app.settings import settings
from app.sources import metricool


def brands() -> list[dict]:
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{metricool.BASE}/admin/simpleProfiles",
            params={"userId": settings.metricool_user_id},
            headers=metricool._headers(),
        )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        existing = {
            page.facebook_page_id: page
            for page in session.exec(select(Page)).all()
        }

        added = skipped = missing = 0
        for brand in sorted(brands(), key=lambda one: str(one.get("label") or "")):
            label = str(brand.get("label") or brand.get("title") or "").strip()
            blog_id = str(brand.get("id") or "")
            facebook_page_id = brand.get("facebookPageId") or brand.get("facebook")

            if not facebook_page_id:
                print(f"  skip     {label:<32} no Facebook page connected")
                missing += 1
                continue

            facebook_page_id = str(facebook_page_id)
            logo = brand.get("facebookPicture") or brand.get("picture") or None

            if facebook_page_id in existing:
                # Re-runnable: an existing Page still takes a logo it is missing,
                # so this backfills rather than only importing. Nothing else on
                # the row is touched — name and blog id may have been corrected
                # by hand, and Metricool is not the authority on those.
                page = existing[facebook_page_id]
                if logo and page.avatar_url != logo:
                    page.avatar_url = logo
                    session.add(page)
                    print(f"  logo     {label:<32} avatar refreshed")
                else:
                    print(f"  have     {label:<32} already a Page")
                skipped += 1
                continue

            print(f"  {'would add' if args.dry_run else 'add':<8} {label:<32} fb={facebook_page_id} blog={blog_id}")
            added += 1
            if args.dry_run:
                continue

            session.add(
                Page(
                    name=label,
                    facebook_page_id=facebook_page_id,
                    metricool_blog_id=blog_id,
                    avatar_url=logo,
                )
            )

        if not args.dry_run:
            session.commit()

        print()
        print(f"  {added} {'to add' if args.dry_run else 'added'}, {skipped} already present, {missing} without a Facebook page")
        if added and not args.dry_run:
            print("  New Pages have no feeds and no watermark. Add feeds on Settings;")
            print("  commit a watermark asset and point the row at it before publishing.")


if __name__ == "__main__":
    main()
