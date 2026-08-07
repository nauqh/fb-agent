"""Sources: browse three kinds. Reads only.

**Browsing does not write.** Nothing here creates a Source Item — the Cart
carries what the operator ticked and `POST /generate` writes only what a run
uses, so an item that is browsed and abandoned leaves nothing behind.

Competitor posts are the standing exception, and stay one: the Metricool sync
writes them on arrival, because they are synced rather than browsed. Storage is
also what makes them checkable — there is no `is_curated_url` equivalent for a
Facebook post, so `POST /generate` takes a competitor by id and resolves it
against a row the sync owns. Phase 3 planned to drop the storage and re-fetch at
generate instead; that was reversed, because it would put a vendor call that has
already 502'd twice at the front of a 60-second run. See docs/plan.md, "But
competitor posts stay stored".
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.db import get_session
from app.models import Draft, Page, SourceItem, SourceItemBase, SourceKind
from app.settings import sources as sources_config
from app.sources import metricool, rss, x

router = APIRouter(prefix="/sources", tags=["sources"])


class StoredSourceItem(SourceItemBase):
    """A stored Source Item, plus whether a Draft has already used it.

    `used` is derived per request rather than stored, for the same reason
    `SourceKind.is_factual` is: a stored copy is a second truth, and when it
    drifts the grid quietly offers the operator a post they already published.
    """

    id: int
    used: bool = False


class FeedFailureOut(BaseModel):
    feed_url: str
    error: str


class RssFeedOut(BaseModel):
    """Items and failures together.

    The failures are part of the response, not a log line: a feed that rots is
    invisible off-screen, and the grid getting quieter looks exactly like a slow
    news week.
    """

    items: list[SourceItemBase]
    failures: list[FeedFailureOut]


@router.get("/competitors")
def get_competitor_posts(
    page_id: int = Query(...),
    refresh: bool = Query(False, description="Force a Metricool sync"),
    session: Session = Depends(get_session),
) -> list[StoredSourceItem]:
    """Stored competitor posts. Syncs when there are none, or when asked.

    It used to sync on every read, which cost **5.5s and 1.6MB** for 500 posts
    to display 60 — against a seven-day window that gains roughly three posts an
    hour. Two reads ten minutes apart paid six seconds to learn nothing, and the
    grid was hostage to a vendor API that does sometimes time out.

    So the sync is explicit, matching the Refresh button the RSS tab already
    has. The empty case still syncs by itself, because a first-run operator
    should not have to know that a button is what makes the grid work.

    No time-based cooldown. A cooldown guesses at how stale is too stale; the
    operator looking at the grid knows, and the button is right there.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    stored = session.exec(
        select(func.count())
        .select_from(SourceItem)
        .where(SourceItem.kind == SourceKind.COMPETITOR_POST)
        .where(SourceItem.synced_for_page_id == page_id)
    ).one()

    if refresh or stored == 0:
        try:
            fetched = metricool.fetch_competitor_posts(page)
        except metricool.MetricoolError as error:
            # 502: the failure is upstream, and saying so is what stops the
            # operator reading an empty grid as "no competitor posted this week".
            raise HTTPException(status_code=502, detail=str(error)) from error

        _upsert(session, fetched, refresh_volatile=True)
        session.commit()

    rows = session.exec(
        select(SourceItem)
        .where(SourceItem.kind == SourceKind.COMPETITOR_POST)
        .where(SourceItem.synced_for_page_id == page_id)
        # Newest first, not most-reacted.
        #
        # This tab exists to find something *new* to write from, and reactions
        # are a stable ranking: the same winners sit at the top every day, so
        # the operator reads the same grid every morning. Worse, nothing prunes
        # this table — rows accumulate week after week — so once sixty older
        # posts out-performed this week's, `limit` meant a genuinely new post
        # could never enter the grid at all.
        #
        # Reactions are still on the card, where they inform a choice rather
        # than deciding what is visible.
        .order_by(SourceItem.published_at.desc())  # type: ignore[union-attr]
        .limit(sources_config.competitors.grid_limit)
    ).all()

    return _with_used(session, rows)


def _with_used(session: Session, rows) -> list[StoredSourceItem]:
    """Flag the ones a Draft already came from, so the grid stops re-offering them."""
    spent = set(
        session.exec(
            select(Draft.source_item_id).where(Draft.source_item_id.is_not(None))  # type: ignore[union-attr]
        ).all()
    )
    return [
        StoredSourceItem(**row.model_dump(), used=row.id in spent) for row in rows
    ]


@router.get("/rss")
def get_rss(
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> RssFeedOut:
    """This Page's curated feeds, live. Nothing is written.

    Takes a `page_id` because the feed list is per-page — the beats do not
    overlap, and hot tub news is noise on a history grid.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    try:
        feed = rss.fetch_rss(page.name)
    except KeyError as error:
        # A Page with no feeds configured is a misconfiguration, not an empty
        # week, and the two are indistinguishable from the grid.
        raise HTTPException(status_code=500, detail=str(error.args[0])) from error

    return RssFeedOut(
        items=feed.items,
        failures=[
            FeedFailureOut(feed_url=failure.feed_url, error=failure.error)
            for failure in feed.failures
        ],
    )


@router.get("/tweet")
def get_tweet(url: str = Query(...)) -> SourceItemBase:
    """One live lookup. Nothing is written, and the X API is paid per read."""
    try:
        return x.fetch_tweet(url)
    except x.XError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


VOLATILE = ("image_url", "reactions", "comments", "shares")
"""Facts the vendor owns and keeps changing, as opposed to the content chosen.

`image_url` is the reason this list exists. Facebook's CDN URLs are *signed and
expire* — the `oe` parameter on a freshly synced one is about four days out,
while the competitor window is seven. Frozen at first sync, every image in the
grid would break before it left the window. The old system refreshed these on
every sync (`competitorMetricoolSyncService.ts:203`), and it was right to.

`text` is deliberately not here. Metrics and a CDN URL are the vendor's; the
words are what the operator chose, and rewriting them under a Draft that already
used them would make the Draft's provenance a moving target.
"""


def _upsert(
    session: Session,
    items: list[SourceItemBase],
    refresh_volatile: bool = False,
) -> list[SourceItem]:
    """One row per item, existing or new. Does not commit.

    Existing rows keep their content. `refresh_volatile` additionally updates
    `VOLATILE` — set by the competitor sync, which is re-reading the same posts
    from the vendor, and not by `POST /sources`, where the client is handing
    back a body it was shown rather than a fresh read.
    """
    rows: list[SourceItem] = []
    # Looked up in one query, not one per item. A competitor sync carries 500
    # posts, and a lookup each made this route 502 statements.
    pending = _existing_by_key(session, items)

    for item in items:
        key = (item.kind, item.external_id)
        existing = pending.get(key)

        if existing is None:
            existing = SourceItem(**item.model_dump())
            session.add(existing)
            # Items within one call can collide too — the same story in two
            # feeds — and the flush that would surface it has not happened yet.
            pending[key] = existing
        elif refresh_volatile:
            for field in VOLATILE:
                setattr(existing, field, getattr(item, field))
            session.add(existing)

        rows.append(existing)

    return rows


_CHUNK = 500
"""SQLite caps host parameters per statement. The modern default is 32766, but
older builds ship 999 and this runs on whatever Python bundles."""


def _existing_by_key(
    session: Session, items: list[SourceItemBase]
) -> dict[tuple[SourceKind, str], SourceItem]:
    """Rows that already exist, keyed by `(kind, external_id)`.

    Filtered on `external_id` alone and paired up in Python: one indexed `IN`
    beats a composite match, and an `external_id` colliding across two kinds is
    not a thing that happens — a Facebook post id is not a feed URL.
    """
    wanted = sorted({item.external_id for item in items if item.external_id})
    found: dict[tuple[SourceKind, str], SourceItem] = {}

    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start : start + _CHUNK]
        for row in session.exec(
            select(SourceItem).where(SourceItem.external_id.in_(chunk))  # type: ignore[union-attr]
        ).all():
            found[(row.kind, row.external_id)] = row

    return found
