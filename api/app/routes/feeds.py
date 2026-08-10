"""A Page's RSS feeds, as rows an operator edits.

These were `config/sources.yml` until the API started running from a container
image on Railway. A file written into an image lasts until the next deploy and
disagrees with the committed copy in the meantime, so the one list that has to
change without a deploy could not stay a file.

**A feed still has to earn its place.** The old comment above each entry said
the list was curated "because every candidate has to be probed before it earns a
place, which is not a thing to do from a form". The probing was the real
requirement, and it moved into the form rather than being dropped: `POST /feeds`
runs `rss.probe` and refuses to write a row for a feed that does not answer,
does not parse, or parses to nothing. The measurements come back with the row so
the judgement is still made on evidence — it is just made on a screen.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Feed, Page
from app.sources import rss

router = APIRouter(prefix="/feeds", tags=["feeds"])


class FeedIn(BaseModel):
    page_id: int
    name: str
    url: str
    note: str | None = None


class ProbeOut(BaseModel):
    """`rss.Probe`, flattened for the client."""

    items: int
    with_images: int
    median_summary: int
    newest_hours: float | None


class FeedOut(BaseModel):
    """A stored feed. `probe` is present only on the response that created it.

    Not stored, and not re-measured on read: these numbers describe one fetch at
    one moment, and a stale copy of them shown beside a feed would be read as
    current. The add form is where they inform a decision.
    """

    feed: Feed
    probe: ProbeOut | None = None


@router.get("")
def list_feeds(
    page_id: int,
    session: Session = Depends(get_session),
) -> list[Feed]:
    if session.get(Page, page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return list(
        session.exec(
            select(Feed).where(Feed.page_id == page_id).order_by(Feed.name)  # type: ignore[arg-type]
        ).all()
    )


@router.post("", status_code=201)
def add_feed(
    body: FeedIn,
    session: Session = Depends(get_session),
) -> FeedOut:
    """Probe first, write second. A feed that does not answer is not a row."""
    if session.get(Page, body.page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {body.page_id}")

    existing = session.exec(
        select(Feed).where(Feed.page_id == body.page_id, Feed.url == body.url)
    ).first()
    if existing is not None:
        # 409 rather than the database's own uniqueness error, which surfaces as
        # a 500 the operator cannot act on.
        raise HTTPException(
            status_code=409, detail=f"{body.url} is already a feed on this Page."
        )

    try:
        measured = rss.probe(body.url)
    except ValueError as error:
        # 422: the URL is the problem, and the message is written for the toast
        # under the add form.
        raise HTTPException(status_code=422, detail=str(error)) from error

    feed = Feed(
        page_id=body.page_id,
        name=body.name.strip(),
        url=body.url.strip(),
        note=(body.note or "").strip() or None,
    )
    session.add(feed)
    session.commit()
    session.refresh(feed)

    return FeedOut(
        feed=feed,
        probe=ProbeOut(
            items=measured.items,
            with_images=measured.with_images,
            median_summary=measured.median_summary,
            newest_hours=measured.newest_hours,
        ),
    )


@router.delete("/{feed_id}", status_code=204)
def remove_feed(feed_id: int, session: Session = Depends(get_session)) -> None:
    """Removing a feed changes tomorrow's grid and nothing that already happened.

    Nothing points at a feed — a Source Item carries its publisher as `author`,
    not a foreign key — so this cannot cascade into published work. That was the
    argument for the shape of the table and this is where it pays off.
    """
    feed = session.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail=f"No feed {feed_id}")
    session.delete(feed)
    session.commit()
