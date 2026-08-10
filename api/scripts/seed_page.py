"""Insert the pages. Idempotent — it checks before every insert, so re-running
it against the live database is a no-op rather than a duplicate.

The values below were read from the old system's `facebook_post_templates` rows
and cross-checked live against Metricool `/admin/simpleProfiles`. There is
nothing left to migrate: the prompts are files (`api/prompts/`), the layout
defaults are `config/layout.yml`, and the watermarks are committed assets under
`api/assets/watermarks/`.

No avatar. That comes from Metricool — `page.avatar_url`, filled by
`import_metricool_pages.py` — because it is the Facebook profile picture and
follows the page when it changes. A committed copy went stale instead. The
watermark stays a committed file for the opposite reason: it is drawn into
published images, where a missing one fails silently.

Pages are seeded by a committed script rather than inserted by hand so that the
two rows are reproducible: a row that only ever existed as a manual `INSERT`
against one database is a row nobody can rebuild. That mattered more when the
database was disposable, and still matters — this is what stands up a Page on a
new Supabase project.

    uv run python scripts/seed_page.py
"""

import sys
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_engine, init_db  # noqa: E402
from app.models import Page  # noqa: E402

PAGES = [
    {
        "name": "History Retraced",
        "facebook_page_id": "569035169625026",
        "metricool_blog_id": "4605385",
        # Relative to API_DIR. Committed, unlike media/, because the current
        # Supabase project 404s every watermark path — this one was recovered
        # from the *previous* project. See docs/decisions.md, "The watermark
        # becomes a committed file".
        #
        # The stacked wordmark, not the single-line one: on a 138px cap
        # "HistoryRetraced" across one line renders too small to read, which is
        # what the real posts show it stacked for. Transparent and white-on-red,
        # derived from the committed JPEG — that original is opaque white paper
        # with black ink, so pasting it would put a card over the hero.
        "watermark_image_path": "assets/watermarks/history-retraced-stacked.png",
    },
    {
        "name": "The Fact Feed",
        "facebook_page_id": "603815099479680",
        "metricool_blog_id": "5600362",
        # Derived from the brand's profile picture — the 720x720 original from
        # the previous Supabase project
        # (`brand-assets/tff/watermark-1782060128654-*.jpg`, uploaded three
        # times, byte-identical, and referenced by no row in the old system), which is a *square*: 720x720
        # of opaque #1977F3 with the wordmark on it, where "THE" is a darker
        # #0D5CC3 that exists only while the background does — so thresholding
        # the background away deletes the first word. Each pixel was decomposed
        # against the background instead, which also keeps the antialiasing, and
        # "THE" repainted in the brand blue: at #0D5CC3 it is nearly invisible
        # on a dark photograph, and the accent is the point.
        #
        # The result matches History Retraced's mark in construction —
        # accent-coloured lettering plus white, transparent, stacked, 210px wide
        # so both hit the same 138px cap. Neither reads well on a pale hero;
        # that is the watermark contract here, not this file's doing.
        "watermark_image_path": "assets/watermarks/the-fact-feed-stacked.png",
    },
]


def main() -> None:
    init_db()
    with Session(get_engine()) as session:
        for values in PAGES:
            existing = session.exec(
                select(Page).where(Page.facebook_page_id == values["facebook_page_id"])
            ).first()
            if existing is not None:
                print(f"already seeded: id={existing.id} {existing.name}")
                continue

            page = Page(**values)
            session.add(page)
            session.commit()
            session.refresh(page)
            print(f"created: id={page.id} {page.name}")


if __name__ == "__main__":
    main()
