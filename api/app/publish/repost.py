"""Reproducing a post that already went out: the Repost.

Distinct from **Write again**, which sends the saved post's story back through
the writer for a fresh hook, caption and picture. A Repost copies what was
published — the caption, the first comment and the picture, as they went out —
and lands in the Review queue as a Draft with no hook and no hero, because the
hook was drawn into the picture that is being reused.

The whole difficulty is the picture, in two separate steps:

1. **Finding the original.** The saved row holds what the stats call returns,
   and that is a 130×163 thumbnail with no first comment anywhere on it. The
   planner row for the same post carries the 896×1120 file *we* handed
   Metricool at publish time and the `firstCommentText` the stats call does not
   expose at all. So the real content is looked up in the planner, and matching
   is by caption and time because the two systems share no id — measured on
   2026-08-19: 596 of 633 stats posts matched exactly one planner row, 30
   matched more than one (resolved by nearest publication time), 7 matched none.

2. **Copying the image into our bucket.** Metricool stores a *link* and
   Facebook fetches it when the post is due, days later — so handing them the
   URL we found publishes whatever it resolves to *then*. The old app's URLs
   were signed and have expired: of the media links in this account's planner,
   315 point at `chonkycatlabs.com` and 67 at its Vercel host, and both answer
   403 today — 0 of 382 still working. Copying the bytes makes the URL *ours*,
   in a public bucket, with no expiry: the same reasoning as `hero.from_url`.

A copy that cannot be made is a **refusal**, not a degraded repost. The
thumbnail is a real picture and would publish without complaint; publishing it
is the one outcome worse than a button that says why it will not.
"""

import re
from datetime import datetime, timedelta, timezone

import httpx

from app import media
from app.models import Page, SavedPost
from app.publish import metricool as publisher

REPOST_TIMEOUT = 20.0

MAX_REPOST_BYTES = 10 * 1024 * 1024
"""The buckets' own cap. Checked here so an oversized file fails with a sentence
rather than as a storage error three calls later."""


PLANNER_MATCH_CHARS = 120
"""How much of a caption has to agree for a planner row to be the same post.

The whole caption would be safer and is not available: the planner's `text` and
the stats row's `text` are the same string in principle, and in practice one of
them has been through Facebook and back. 120 characters is past the hook and
into the recap on every post measured, which is enough to separate posts and
short enough to survive that round trip.
"""

PLANNER_WINDOW = timedelta(days=2)
"""How far either side of the published time to look.

The planner is keyed by *scheduled* time and the stats row by when Facebook says
it went out; they agree to the minute on the posts measured, but a post moved by
hand in Metricool's UI would not. Two days is generous enough for that and
narrow enough that the read stays small — the alternative, asking for the whole
history, is 2,197 rows to find one.
"""


class RepostError(RuntimeError):
    """The original post cannot be reproduced.

    `status` is the HTTP status the route should answer with, because the two
    failure shapes are different and both are already load-bearing for the
    client: **502** is "we could not check" (the image host did not answer),
    **409** is "we checked and it is unusable" (expired, not an image, too
    big, or the planner has no original at all).
    """

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def original_for(page: Page, row: SavedPost) -> dict | None:
    """The planner row this saved post was published from, if it can be found.

    **This is where a repost's real content lives, and the stats row is not.**
    Measured on 2026-08-19 against History Retraced:

    - `SavedPost.picture_url` comes from the stats call, and it is a *thumbnail*
      — the URL carries `stp=dst-jpg_p130x130_tt6` and answers a **130×163**
      JPEG. Reposting it publishes that. Its `fullPicture` sibling is empty on
      all 633 posts in the window, and rewriting the size in the URL, or
      dropping it, answers 403: the URL is signed over its parameters.
    - The planner row for the same post carries `media`, and that image is the
      **896×1120** original at about 1.2MB, because it is the file *we* handed
      Metricool at publish time. It also carries `firstCommentText`, which the
      stats call does not expose at all and no column here has ever held.

    So this is not an optimisation. Without it a repost cannot reproduce the
    post it is reposting, in two separate ways.

    **Matching is by caption and time, because there is no shared id.** The
    planner's `providers[].id` and the stats row's `postId` are different id
    spaces — 2,102 against 633 with a zero-length intersection, so joining on
    them silently matches nothing. On caption, 596 of 633 stats posts match
    exactly one planner row and every one of those carries media; 30 match more
    than one, which is what a caption published twice looks like and is resolved
    here by taking the nearest publication time; 7 match none.

    Returns `None` for "checked and it is not there" *and* for "could not
    check" — a planner that is unreachable reads as no original, because the
    caller's next move is the same either way, and distinguishing would turn
    "we could not look" into a different error from "we looked and there is
    nothing".
    """
    if not page.metricool_blog_id or not row.published_at or not row.text.strip():
        return None

    when = row.published_at
    # Naive local, like every other date sent to Metricool — an offset suffix is
    # rejected outright (see `publish.metricool.publication_date`).
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)

    try:
        rows = publisher.list_scheduled(
            page.metricool_blog_id, when - PLANNER_WINDOW, when + PLANNER_WINDOW
        )
    except publisher.PublishError:
        return None

    wanted = _match_key(row.text)
    hits = [item for item in rows if _match_key(item.get("text")) == wanted]
    if not hits:
        return None
    # A caption published twice is a post that has already been reposted, so the
    # nearest one in time is the one being asked for.
    return min(hits, key=lambda item: abs(_planner_time(item) - when))


def _match_key(text: str | None) -> str:
    """A caption reduced to what survives a round trip through Facebook."""
    return re.sub(r"\s+", " ", text or "").strip().lower()[:PLANNER_MATCH_CHARS]


def _planner_time(item: dict) -> datetime:
    """A planner row's publication time, naive local. Far future if unparseable,
    so a malformed row loses the `min` above rather than raising in it."""
    stamp = (item.get("publicationDate") or {}).get("dateTime")
    try:
        return datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return datetime.max


def copy_original_image(source_url: str, draft_id: int) -> str:
    """Take the post's picture off its host and into our bucket.

    **This is the whole difficulty of reposting, and it is not optional.**
    Metricool stores a *link* to what we publish and Facebook fetches it when
    the post is due, days later — so handing them the URL we found publishes
    whatever that URL resolves to *then*, not now. The old app's URLs were
    signed and have expired: of the media links in this account's planner, 315
    point at `chonkycatlabs.com` and 67 at its Vercel host, and both answer 403
    today. That is 0 of 382 still working, which is the same trap the competitor
    thumbnails and the old app's 105 dead published images document.

    Copying it here makes the URL we hand Metricool *ours*, in a public bucket,
    with no expiry — the same reasoning and nearly the same code as
    `hero.from_url`, which fetches a feed's photograph rather than hot-linking
    it for exactly this reason.

    Kept as the original bytes rather than re-encoded. A repost is meant to be
    the same post; putting it through the compositor would produce a *new* card
    from our current layout, which is the one thing this button is not for.
    """
    try:
        with httpx.Client(timeout=REPOST_TIMEOUT, follow_redirects=True) as client:
            response = client.get(source_url)
    except httpx.HTTPError as error:
        raise RepostError(
            f"The image host did not answer ({type(error).__name__}). "
            "The original picture cannot be copied, so this post cannot be "
            "reposted with its image.",
            status=502,
        ) from error

    if response.is_error:
        # The expected end state, not a bug: the old app's links are signed and
        # have already rotted. Every one of them is a post we cannot repost.
        raise RepostError(
            f"The original image has expired — its host answered "
            f"{response.status_code}. Posts published by the old tool kept "
            "their images behind links that have since lapsed. \u201cWrite "
            "again\u201d will write the story fresh with a new picture."
        )

    kind = response.headers.get("content-type", "")
    if not kind.startswith("image/"):
        raise RepostError(
            f"That URL answered {kind or 'an unknown type'} rather than an "
            "image, so there is nothing to repost."
        )
    if len(response.content) > MAX_REPOST_BYTES:
        raise RepostError(
            f"The original image is {len(response.content) // 1024}KB, over the 10MB bucket cap."
        )

    suffix = "png" if "png" in kind else "jpg"
    return media.store.save(response.content, media.filename(draft_id, "repost", suffix))
