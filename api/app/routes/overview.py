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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app import generate
from app.db import get_session
from app.models import Draft, DraftStatus, Page, SavedPost
from app.publish import repost
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
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> list[PostStats]:
    """This Page's published posts and how they did, best first.

    **Sorted here, not by Metricool.** Their `sortcolumn` parameter is accepted
    and ignored: asking for `reactions` returned the same order as asking for
    nothing, with a zero-reaction post first while the window held one with
    160,282.

    30 days by default. An earlier version used 90 on the theory that their lag
    made shorter windows read as a dead Page; measured, that is false — over 7
    days only 1 post of 28 had no reactions, and over 30 it was 1 of 219. The
    belief came from the sorting bug above, where the unsorted first row
    happened to be a recent zero.
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


@router.post("/overview/saved/{saved_id}/reuse", status_code=202)
def reuse_saved(
    saved_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> list[int]:
    """Write the saved post's story again, from scratch.

    The point of keeping a top performer — "save the top-performing posts for
    future reference/reuse". The operator confirmed the reading: **the same
    story, written fresh**, not a copy and not a style sample. Their own data
    already shows them doing it by hand; the best post in the 90-day window
    appears twice, three weeks apart.

    It runs as a **topic** rather than a Source Item, which is what makes the
    subject bind without the writer treating our own prose as an article to
    summarise. `start_run` takes it from there, so this is the ordinary generate
    path — same prompts, same brand rules, same card — and answers 202 with ids
    to poll like every other run.

    The stored text is the *published caption*, which is the fullest description
    of the story we have. The hook is not stored: it was drawn into the image
    and never existed as a column on anything but our own drafts, most of which
    these posts are not.
    """
    row = session.get(SavedPost, saved_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No saved post {saved_id}")

    topic = (row.text or "").strip()
    if not topic:
        raise HTTPException(
            status_code=409,
            detail="That saved post has no text to write from.",
        )

    try:
        draft_ids = generate.start_run(session, [row.page_id], [], topic)
    except generate.GenerateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    background.add_task(generate.run_drafts, draft_ids)
    return draft_ids


@router.post("/overview/saved/{saved_id}/repost", status_code=201)
def repost_saved(saved_id: int, session: Session = Depends(get_session)) -> Draft:
    """Put the original post back in the queue, caption and picture as published.

    The client's ask, verbatim: "would it be easy to include a button to just
    repost the original?" — distinct from **Write again**, which sends the story
    back through the writer for a fresh hook, caption and image. This one copies
    what went out. The whole difficulty — finding the original in the planner and
    copying its picture into our bucket — lives in `app.publish.repost`;
    everything here is row lookup, shaping and HTTP statuses.

    **It creates a Draft rather than publishing.** Every other route to an
    audience in this app goes through Review and one of the three publish
    buttons, and a button that reached Facebook directly would be the only
    exception — on a post whose image may have expired since it was saved. So
    the repost lands in the queue at `review`, and the operator publishes it the
    way they publish everything else.

    No model call, no cost, and deliberately no compositing: `composed_image_path`
    is the copied original, so publish hands Metricool that file rather than a
    new card built from today's layout.

    **The picture and the first comment come from the planner, not from the
    saved row.** The saved row holds what the stats call returns, and that is a
    130×163 thumbnail with no first comment anywhere on it — see
    `repost.original_for` for the measurements. Reposting from the saved row
    alone published a pixelated image and dropped the first comment silently,
    which is two ways of not being the post it claims to be repeating.

    A post whose original cannot be found is **refused**, not reposted from the
    thumbnail. That is 382 of this account's 2,197 published posts: everything
    the old tool put out, whose image links have lapsed. The thumbnail is a real
    picture and would publish without complaint, and looking wrong on the page
    is worse than a button that says why it will not.
    """
    row = session.get(SavedPost, saved_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No saved post {saved_id}")

    page = session.get(Page, row.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {row.page_id}")

    caption = (row.text or "").strip()
    if not caption:
        raise HTTPException(
            status_code=409,
            detail="That saved post has no text, so there is nothing to repost.",
        )

    original = repost.original_for(page, row)
    media_urls = (original or {}).get("media") or []
    if not media_urls:
        raise HTTPException(
            status_code=409,
            detail=(
                "The original picture could not be found in Metricool's "
                "planner, and the only other copy is a 130-pixel thumbnail that "
                "would look wrong published. “Write again” writes the story "
                "fresh with a new picture."
            ),
        )

    # The planner's caption over the saved one where both exist: the saved copy
    # has been through Facebook and back, and this is the string we sent.
    caption = (original or {}).get("text", "").strip() or caption
    first_comment = ((original or {}).get("firstCommentText") or "").strip() or None

    draft = Draft(
        page_id=row.page_id,
        # The published caption verbatim — `_post_text` sends `caption` and
        # `first_comment`, so what went out last time is what goes out again.
        caption=caption,
        first_comment=first_comment,
        status=DraftStatus.REVIEW,
        progress_step="reposted",
        progress_pct=100,
        # Named so the queue says what this row is. There is no Source Item and
        # no hook: the hook was drawn into the picture that is being reused.
        topic=f"Repost — {caption[:60]}",
        warnings=[
            "A repost: the caption, first comment and picture are the ones "
            "already published. Redrawing the image would replace it with a new "
            "card, which is not what a repost is."
        ],
    )
    session.add(draft)
    # The id is wanted for the filename and nothing else. Flushed rather than
    # committed so that a failed copy below rolls the row back — a draft with a
    # caption and no picture is worse than no draft, because it looks publishable.
    session.flush()

    try:
        draft.composed_image_path = repost.copy_original_image(
            media_urls[0], draft.id or 0
        )
    except repost.RepostError as error:
        session.rollback()
        raise HTTPException(status_code=error.status, detail=str(error)) from error

    session.commit()
    session.refresh(draft)
    return draft


@router.delete("/overview/saved/{saved_id}", status_code=204)
def unsave_post(saved_id: int, session: Session = Depends(get_session)) -> None:
    """Stop keeping it. Nothing points at a saved post, so this cascades nowhere."""
    row = session.get(SavedPost, saved_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No saved post {saved_id}")
    session.delete(row)
    session.commit()
