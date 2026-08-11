"""feeds for the eight pages that had none

Data only — no schema change. The eight Pages `import_metricool_pages.py`
created came in with zero feeds, so their RSS tab was empty and the only Source
Items they could ever get were competitor posts.

**Every URL here was probed before it was written**, the same `rss.probe` the add
form runs, on 2026-08-11: 105 candidates across the eight beats, then a title
sample over the survivors because the numbers can look right while the beat is
wrong (Addicted2Success is 30 fresh items of B2B marketing copy; Pool & Spa News
is trade press about COO appointments). `note` carries the measurement, as it
does for the twelve seeded in 103581b4d2f1 — items / imaged / median chars /
age of the newest entry at probe time.

The window did most of the rejecting. `sources.yml` sets `since_days: 7`, so a
feed whose newest item is older than 168h contributes nothing at all, ever, and
looks identical to a healthy one from every other number. It killed every hot tub
manufacturer blog (Master Spas 977h, Arctic Spas 757h, Bullfrog 17,962h), the
whole motivation lane (James Clear 57,801h — six and a half years), and Self,
which has 30 imaged items and last published 73 days ago.

**Three Pages share one feed set.** Bodybuilding Tips N Tricks and both GYM
Motivation Pages get the same four rows, because the motivation beat has no
feed: quotes and gym-motivation posts are made, not published to RSS. Their
grids will be identical until someone finds a source that is actually distinct.

**Hot Tub Timeout gets one feed, not four.** That is the finding rather than a
gap — see the comment above its entry.

Idempotent by (page, url), matching Pages by name, exactly as 103581b4d2f1 does.
Downgrade removes only the pairs listed here.

Revision ID: 5cac274859ce
Revises: 24109305dae9
Create Date: 2026-08-11 05:52:14.183926

"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5cac274859ce'
down_revision: Union[str, Sequence[str], None] = '24109305dae9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The bodybuilding four, shared by three Pages. Every one imaged except Boxrox,
# which is here for freshness: at 0.8h it is what puts something on the grid on a
# day the magazines are quiet. It is also the CrossFit desk rather than the
# bodybuilding one, which is the trade.
_GYM: list[tuple[str, str, str | None]] = [
    (
        "Muscle & Fitness",
        "https://www.muscleandfitness.com/feed/",
        "25 items, every one imaged, 404-char summaries — the spine of this grid.",
    ),
    (
        "Generation Iron",
        "https://generationiron.com/feed/",
        "10 items, every one imaged, 302 chars. Competition results and records "
        "rather than training advice, which is the half of the beat the magazines "
        "under-serve.",
    ),
    (
        "Fitness Volt",
        "https://fitnessvolt.com/feed/",
        "10 items, every one imaged, 203 chars. Thinner than the other two and "
        "kept for volume on the same beat.",
    ),
    (
        "Boxrox",
        "https://www.boxrox.com/feed/",
        "10 items, 317 chars, and no images at all — but the freshest source "
        "probed anywhere at 0.8h. CrossFit rather than bodybuilding.",
    ),
]

SEED: dict[str, list[tuple[str, str, str | None]]] = {
    "Bible Focus": [
        (
            "Our Daily Bread",
            "https://odb.org/feed/",
            "1342-char devotionals, 30 items, 3.3h fresh — the richest text of "
            "anything probed for this Page. Carries no images at all, which the "
            "other three cover for.",
        ),
        (
            "Bible Study Magazine",
            "https://www.logos.com/grow/feed/",
            "25 items, every one imaged, 377 chars. Logos' teaching blog — "
            "exegesis and Old Testament background, the closest thing to "
            "scripture study that answers a fetch.",
        ),
        (
            "Christian Headlines",
            "https://www.christianheadlines.com/rss/",
            "10 items, every one imaged, 332 chars, 6.8h. Faith *news* — "
            "testimony and politics rather than scripture. The one entry here "
            "that is a judgement about what the Page posts, not a measurement.",
        ),
        (
            "Crosswalk",
            "https://www.crosswalk.com/rss/",
            "Only 8 items, but all imaged and listicle-shaped ('5 Verses I Return "
            "to When My Body Feels Like the Enemy'), which is post material "
            "with no rewriting.",
        ),
    ],
    "Bodybuilding Tips N Tricks": _GYM,
    "GYM Motivation": _GYM,
    "GYM Motivation | quotes | videos | tips|": _GYM,
    "Fitness Girls": [
        (
            "Women's Health",
            "https://www.womenshealthmag.com/rss/all.xml/",
            "50 items, every one imaged, 4.1h — the only fresh volume this beat "
            "has, and it both swamps the other two and dilutes: the titles run to "
            "skincare and Amazon reviews as often as to training.",
        ),
        (
            "PopSugar Fitness",
            "https://www.popsugar.com/fitness/feed",
            "25 items, every one imaged, 4590-char bodies. Slower at 81h but by "
            "far the richest fuel on this Page.",
        ),
        (
            "Nourish Move Love",
            "https://www.nourishmovelove.com/feed/",
            "10 items, 5 imaged, 195 chars, 118h — near the 168h window edge and "
            "kept anyway: it is the only source here that is actually workouts.",
        ),
    ],
    # Three feeds, not four. Peanut Butter Fingers was the fourth candidate and
    # is fresh (15.4h) and fully imaged, at 64-char summaries — thinner than
    # Archaeology Magazine, which sources.yml rejected at 101. Self measures well
    # on everything except the number that matters: newest item 73 days old.
    "Fitness Recipes": [
        (
            "Skinnytaste",
            "https://www.skinnytaste.com/feed/",
            "10 items, every one imaged, 384 chars, 10.1h. Light cooking, which is "
            "this Page's beat exactly.",
        ),
        (
            "Ambitious Kitchen",
            "https://www.ambitiouskitchen.com/feed/",
            "12 items, every one imaged, 429-char summaries — the longest of the "
            "four.",
        ),
        (
            "The Big Man's World",
            "https://thebigmansworld.com/feed/",
            "12 items, every one imaged, 356 chars. High-protein recipes: 'Air "
            "Fryer Chicken Shawarma', 'Baked Blackened Chicken'.",
        ),
        (
            "Fit Foodie Finds",
            "https://fitfoodiefinds.com/feed/",
            "12 items, every one imaged, 268 chars. Slowest of the four at 42h.",
        ),
    ],
    # One feed, and it is the answer rather than an unfinished job. Fifteen
    # candidates were probed for this beat and WhatSpa is the only one that is
    # simultaneously alive, on-topic and consumer-facing:
    #   Master Spas 977h,       manufacturer blogs, all abandoned years ago and
    #     Arctic Spas 757h,     so all outside the 168h window — zero items each
    #     Bullfrog Spas 17962h
    #   Hot Spring, Caldera     200, parses to nothing
    #   Jacuzzi 410, Spa Depot  gone
    #     503, Superior no DNS
    #   Pool & Spa News         alive at 132h and the wrong readership: it is the
    #                           trade desk. 'Poolwerx appoints new COO', 'Why
    #                           Builders Overlook Financing Fees'
    #   Country Living UK       49 fresh imaged items and would swamp WhatSpa 4:1
    #                           with night-sky and home-decor stories
    # This Page runs on competitor posts. Raising `since_days` would revive the
    # manufacturer blogs, and it is global — it would loosen the other seven
    # Pages to buy stale marketing copy, which is not a trade worth making.
    "Hot Tub Timeout": [
        (
            "WhatSpa",
            "https://www.whatspa.co.uk/feed/",
            "12 items, 198 chars, 41.8h, and no images — kept despite that "
            "because it is the only feed probed anywhere that is genuinely about "
            "hot tubs: buying guides, privacy and landscaping ideas.",
        ),
    ],
    "House of Common Sense": [
        (
            "The Free Press",
            "https://www.thefp.com/feed",
            "20 items, 18 imaged, 217 chars, and the freshest of the four at 0.9h.",
        ),
        (
            "Reason",
            "https://reason.com/feed/",
            "48 items but only half imaged, 156 chars. The volume is the caveat: "
            "it is nearly the whole 50-item cap on its own, so it crowds the "
            "other three. Delete it first if the grid reads monotonous.",
        ),
        (
            "National Review",
            "https://www.nationalreview.com/feed/",
            "20 items, every one imaged, 145 chars, 6.3h.",
        ),
        (
            "The Hill Opinion",
            "https://thehill.com/opinion/feed/",
            "15 items, every one imaged, 240 chars. The opinion feed, not the news "
            "one The Fact Feed already reads.",
        ),
    ],
}
# UnHerd was the obvious fifth and is not here: 30 items, 4.2h, and 69-char
# summaries with no images — the thinnest fuel measured in the entire sweep.


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    now = datetime.now(timezone.utc)

    for page_name, feeds in SEED.items():
        page_id = connection.execute(
            sa.text("SELECT id FROM page WHERE name = :name"), {"name": page_name}
        ).scalar()
        if page_id is None:
            # A database seeded with different Pages is not a broken migration —
            # this revision adds no schema, so there is nothing for it to leave
            # half-done.
            continue

        for name, url, note in feeds:
            already = connection.execute(
                sa.text("SELECT 1 FROM feed WHERE page_id = :page_id AND url = :url"),
                {"page_id": page_id, "url": url},
            ).scalar()
            if already:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO feed (page_id, name, url, note, created_at) "
                    "VALUES (:page_id, :name, :url, :note, :created_at)"
                ),
                {
                    "page_id": page_id,
                    "name": name,
                    "url": url,
                    "note": note,
                    "created_at": now,
                },
            )


def downgrade() -> None:
    """Downgrade schema."""
    connection = op.get_bind()

    # By (page, url), never by page: a Page here may have gained feeds the
    # operator added from Settings, and those are not this revision's to remove.
    for page_name, feeds in SEED.items():
        page_id = connection.execute(
            sa.text("SELECT id FROM page WHERE name = :name"), {"name": page_name}
        ).scalar()
        if page_id is None:
            continue
        for _name, url, _note in feeds:
            connection.execute(
                sa.text("DELETE FROM feed WHERE page_id = :page_id AND url = :url"),
                {"page_id": page_id, "url": url},
            )
