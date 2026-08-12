"""Post performance, and the posts worth keeping.

Two halves that look alike and are not. **Performance is read live from
Metricool** and stored nowhere — the same reasoning as the schedule screen
(ADR-0001): their stats are the truth, they move every day as Facebook counts
catch up, and a local copy could only ever be stale. **A saved post is a
decision** and needs a row, because Metricool's stats call takes a date range
and a post falls out of every read once it is old enough. A reference that
vanishes on a rolling window is not a reference.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Page, SavedPost
from app.sources import metricool

router = APIRouter(tags=["overview"])


class PostStats(BaseModel):
    """One published post, flattened out of Metricool's stats row."""

    post_id: str
    text: str = ""
    permalink_url: str | None = None
    picture_url: str | None = None
    published_at: str | None = None

    reactions: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0
    impressions: int = 0

    engagement: int = 0
    """reactions + comments + shares, computed here.

    Metricool returns an `engagement` field and it is **null on every row we
    have seen**, so it is not read. Three numbers that are populated beat one
    that is not."""

    saved: bool = False
    """Whether this post is already in `saved_post`, so the screen can show a
    toggle rather than offering to save something twice."""


def _int(row: dict, key: str) -> int:
    value = row.get(key)
    return int(value) if isinstance(value, (int, float)) else 0


def _flatten(row: dict, saved: set[str]) -> PostStats:
    post_id = str(row.get("postId") or "")
    created = row.get("created")
    published = None
    if isinstance(created, (int, float)):
        # Epoch milliseconds. Rendered in the Page's zone by the client, like
        # every other time in this app.
        published = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()

    reactions = _int(row, "reactions")
    comments = _int(row, "comments")
    shares = _int(row, "shares")
    return PostStats(
        post_id=post_id,
        text=row.get("text") or "",
        permalink_url=row.get("permalinkUrl") or row.get("link"),
        picture_url=row.get("picture") or row.get("fullPicture"),
        published_at=published,
        reactions=reactions,
        comments=comments,
        shares=shares,
        clicks=_int(row, "clicks"),
        impressions=_int(row, "impressions"),
        engagement=reactions + comments + shares,
        saved=post_id in saved,
    )


@router.get("/overview/performance")
def performance(
    page_id: int = Query(1),
    days: int = Query(90, ge=1, le=365),
    session: Session = Depends(get_session),
) -> list[PostStats]:
    """This Page's published posts and how they did, best first.

    **Sorted here, not by Metricool.** Their `sortcolumn` parameter is accepted
    and ignored: asking for `reactions` returned the same order as asking for
    nothing, with a zero-reaction post first while the window held one with
    160,282.

    90 days by default because their stats lag Facebook by a day or so, so the
    newest posts legitimately read as zeros — over a 30-day window that was most
    of the response, and the screen looked like a dead Page.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    if not page.metricool_blog_id:
        raise HTTPException(
            status_code=409,
            detail=f"{page.name} has no metricool_blog_id to read stats from.",
        )

    try:
        rows = metricool.page_posts(page.metricool_blog_id, days)
    except metricool.StatsError as error:
        # 502, like the schedule screen: the failure is upstream, and saying so
        # is better than an empty grid that reads as a Page with no posts.
        raise HTTPException(status_code=502, detail=str(error)) from error

    saved = {
        row.metricool_post_id
        for row in session.exec(
            select(SavedPost).where(SavedPost.page_id == page_id)
        ).all()
    }
    posts = [_flatten(row, saved) for row in rows]
    posts.sort(key=lambda post: post.engagement, reverse=True)
    return posts


class SaveRequest(BaseModel):
    """What the screen sends to keep a post. The metrics come with it.

    Sent by the client rather than re-fetched, because they are a *snapshot* —
    what this post scored when it was saved. Re-reading them later would need
    the post to still be inside a window it has by definition left.
    """

    page_id: int
    post_id: str
    text: str = ""
    permalink_url: str | None = None
    picture_url: str | None = None
    published_at: datetime | None = None
    reactions: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    note: str | None = None


@router.get("/overview/saved")
def list_saved(
    page_id: int = Query(1), session: Session = Depends(get_session)
) -> list[SavedPost]:
    """Kept posts, newest first."""
    return list(
        session.exec(
            select(SavedPost)
            .where(SavedPost.page_id == page_id)
            .order_by(SavedPost.created_at.desc())  # type: ignore[union-attr]
        ).all()
    )


@router.post("/overview/saved", status_code=201)
def save_post(request: SaveRequest, session: Session = Depends(get_session)) -> SavedPost:
    """Keep a post. Saving one twice is the same decision, so it is refused."""
    if session.get(Page, request.page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {request.page_id}")

    existing = session.exec(
        select(SavedPost)
        .where(SavedPost.page_id == request.page_id)
        .where(SavedPost.metricool_post_id == request.post_id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="That post is already saved.")

    row = SavedPost(
        page_id=request.page_id,
        metricool_post_id=request.post_id,
        text=request.text,
        permalink_url=request.permalink_url,
        picture_url=request.picture_url,
        published_at=request.published_at,
        reactions=request.reactions,
        comments=request.comments,
        shares=request.shares,
        impressions=request.impressions,
        note=request.note,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.delete("/overview/saved/{saved_id}", status_code=204)
def unsave_post(saved_id: int, session: Session = Depends(get_session)) -> None:
    """Stop keeping it. Nothing points at a saved post, so this cascades nowhere."""
    row = session.get(SavedPost, saved_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No saved post {saved_id}")
    session.delete(row)
    session.commit()
