"""Insert the one page. Idempotent — safe to re-run after deleting the db file.

The values below were read from the old system's `facebook_post_templates` row
for page 569035169625026 and cross-checked live against Metricool
`/admin/simpleProfiles`. There is nothing left to migrate: the prompts are files
(`api/prompts/`), the layout is `config/layout.yml`, and the watermark is a
committed asset under `api/assets/watermarks/`.

    uv run python scripts/seed_page.py
"""

import sys
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_engine, init_db  # noqa: E402
from app.models import Page  # noqa: E402

PAGE = {
    "name": "History Retraced",
    "facebook_page_id": "569035169625026",
    "metricool_blog_id": "4605385",
    # Relative to API_DIR. Committed, unlike media/, because the current
    # Supabase project 404s every watermark path — this one was recovered from
    # the *previous* project. See docs/decisions.md, "The watermark becomes a
    # committed file".
    #
    # The stacked wordmark, not the single-line one: on a 138px cap
    # "HistoryRetraced" across one line renders too small to read, which is what
    # the real posts show it stacked for. Transparent and white-on-red, derived
    # from the committed JPEG — that original is opaque white paper with black
    # ink, so pasting it would put a card over the hero.
    "watermark_image_path": "assets/watermarks/history-retraced-stacked.png",
}


def main() -> None:
    init_db()
    with Session(get_engine()) as session:
        existing = session.exec(
            select(Page).where(Page.facebook_page_id == PAGE["facebook_page_id"])
        ).first()
        if existing is not None:
            print(f"already seeded: id={existing.id} {existing.name}")
            return

        page = Page(**PAGE)
        session.add(page)
        session.commit()
        session.refresh(page)
        print(f"created: id={page.id} {page.name}")


if __name__ == "__main__":
    main()
