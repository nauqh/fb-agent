"""Sources: browse three kinds, persist the ticked ones.

The rule this module enforces is **browsing does not write**. Every `GET` here
returns items without touching the database; `POST /sources` is the only thing
that creates a row. Competitor posts are the one exception, and they are the
exception because they arrive by sync rather than by browsing — there is no live
competitor grid to page through.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Page, SourceItem, SourceItemBase, SourceKind
from app.settings import sources as sources_config
from app.sources import metricool, rss, x

router = APIRouter(prefix="/sources", tags=["sources"])


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


@router.get("")
def list_sources(
    ids: str = Query("", description="Comma-separated row ids"),
    session: Session = Depends(get_session),
) -> list[SourceItem]:
    """Resolve Cart ids back to rows.

    The Cart is client-side and holds nothing but ids (data-model.md, "A cart
    table. Rejected."), so something has to turn them back into rows to display.
    Returned in the order asked for, because that is the order they were ticked
    in and the Cart shows it.
    """
    wanted = [int(part) for part in ids.split(",") if part.strip().isdigit()]
    if not wanted:
        return []

    rows = session.exec(select(SourceItem).where(SourceItem.id.in_(wanted))).all()  # type: ignore[union-attr]
    by_id = {row.id: row for row in rows}
    # Silently drops an id with no row. The Cart is client state and can outlive
    # a deleted row; failing the whole panel over one stale id helps nobody.
    return [by_id[row_id] for row_id in wanted if row_id in by_id]


@router.get("/competitors")
def get_competitor_posts(
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> list[SourceItem]:
    """Sync this Page's competitor set from Metricool, then return the rows.

    Syncing on every read, with no cooldown. The old client cached for 60
    seconds (`competitorMetricoolSyncService.ts:22`); one operator opening one
    tab does not need it, and a cooldown is a thing to add when a bill or a rate
    limit says so, not before.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    try:
        fetched = metricool.fetch_competitor_posts(page)
    except metricool.MetricoolError as error:
        # 502: the failure is upstream, and saying so is what stops the operator
        # reading an empty grid as "no competitor posted this week".
        raise HTTPException(status_code=502, detail=str(error)) from error

    _upsert(session, fetched, refresh_volatile=True)
    session.commit()

    rows = session.exec(
        select(SourceItem)
        .where(SourceItem.kind == SourceKind.COMPETITOR_POST)
        .where(SourceItem.synced_for_page_id == page_id)
        .order_by(SourceItem.reactions.desc())  # type: ignore[union-attr]
        .limit(sources_config.competitors.grid_limit)
    ).all()
    return list(rows)


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


@router.post("", status_code=201)
def save_sources(
    items: list[SourceItemBase],
    session: Session = Depends(get_session),
) -> list[SourceItem]:
    """Persist ticked items, returning one row per item in the order given.

    Idempotent by `UNIQUE (kind, external_id)`: ticking the same item twice
    returns the existing row rather than creating a second one.
    """
    for item in items:
        if item.kind == SourceKind.RSS and not rss.is_curated_url(item.url):
            # The RSS tab is live, so the client posts the body back rather than
            # an id the server can look up. Without this the endpoint takes
            # arbitrary text and hands it to the writer, and "fully curated"
            # stops being a property of the system.
            raise HTTPException(
                status_code=422,
                detail=f"Not from a curated feed: {item.url}",
            )
        if not item.external_id:
            raise HTTPException(
                status_code=422, detail="A source item needs an external_id to dedup on"
            )

    rows = _upsert(session, items)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


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
    # Items within one call can collide too (the same story in two feeds), and
    # the flush that would surface it has not happened yet.
    pending: dict[tuple[SourceKind, str], SourceItem] = {}

    for item in items:
        key = (item.kind, item.external_id)
        if key in pending:
            rows.append(pending[key])
            continue

        existing = session.exec(
            select(SourceItem)
            .where(SourceItem.kind == item.kind)
            .where(SourceItem.external_id == item.external_id)
        ).first()
        if existing is None:
            existing = SourceItem(**item.model_dump())
            session.add(existing)
        elif refresh_volatile:
            for field in VOLATILE:
                setattr(existing, field, getattr(item, field))
            session.add(existing)

        pending[key] = existing
        rows.append(existing)

    return rows
