"""Competitor posts, from Metricool's competitor analytics.

The one source kind written on arrival. Competitors are configured in Metricool, not
here, so there is nothing live to browse and nothing to tick — a sync either
found posts or it did not (see data-model.md, "What was considered and
rejected", for why there is no `competitor` table).

One endpoint does the work. `/v2/analytics/competitors/facebook/posts` is
already scoped to a blog's competitor set, so a single call returns every
competitor's posts for one of our Pages — the old client fetched the same payload and
then filtered it down to one competitor at a time, because its UI browsed them
individually (`metricoolService.ts:1046`). Ours does not, so it keeps them all.
"""

from datetime import datetime, timedelta, timezone

import httpx

from app.models import Page, SourceItemBase, SourceKind
from app.settings import settings, sources

BASE = "https://app.metricool.com/api"
"""Not configurable. Changing it means changing the response parsing below, so
exposing it would offer an edit that cannot safely be made."""

FETCH_LIMIT = 500
"""What we ask Metricool for — the window, not the grid. Bounds the request
rather than the display, so it belongs with the code that makes the request."""


class MetricoolError(RuntimeError):
    """Raised loudly. A sync that quietly returns nothing looks like a quiet week."""


def _headers() -> dict[str, str]:
    return {"X-Mc-Auth": settings.metricool_api_token}


def _params(blog_id: str, days: int) -> dict[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return {
        # Metricool wants naive local datetimes plus the timezone as a separate
        # parameter; it rejects an offset suffix.
        "from": f"{start:%Y-%m-%d}T00:00:00",
        "to": f"{end:%Y-%m-%d}T23:59:59",
        "blogId": blog_id,
        "userId": settings.metricool_user_id,
        "limit": str(FETCH_LIMIT),
        "timezone": settings.timezone,
    }


def _get(client: httpx.Client, path: str, blog_id: str, days: int) -> list[dict]:
    try:
        response = client.get(
            f"{BASE}/v2/analytics/competitors/facebook{path}",
            params=_params(blog_id, days),
            headers=_headers(),
        )
    except httpx.HTTPError as error:
        # A timeout or a refused connection is still "the sync failed", and the
        # route turns MetricoolError into a 502. Without this it escapes as an
        # unhandled ReadTimeout and the operator gets a 500 stack trace instead
        # of a sentence. This endpoint does time out in practice — it moves
        # 1.6MB and takes ~5.5s on a good day.
        raise MetricoolError(
            f"Metricool {path or '/'} did not answer: {type(error).__name__}"
        ) from error

    if response.is_error:
        raise MetricoolError(
            f"Metricool {path or '/'} failed ({response.status_code}): "
            f"{response.text[:200]}"
        )
    return response.json().get("data") or []


def _published_at(row: dict) -> datetime | None:
    """From `created`, the epoch, never from `creationDate`.

    `creationDate.dateTime` is a *naive* local timestamp in whatever zone the
    Metricool account reports — Europe/Madrid on this one, regardless of the
    `timezone` parameter we send. Reading it as UTC puts every competitor post two
    hours out, which is invisible until the grid sorts wrongly. `created` is
    epoch milliseconds and has no such ambiguity.
    """
    epoch_ms = row.get("created") or row.get("timestamp")
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)


def _to_source_item(row: dict, page_id: int) -> SourceItemBase:
    return SourceItemBase(
        kind=SourceKind.COMPETITOR_POST,
        external_id=str(row.get("postId") or ""),
        # The competitor's own providerId, which is what an assignment
        # names. Measured to match: all 15 distinct pageId values in a
        # window are providerIds from the competitor list, none unmatched.
        competitor_page_id=str(row.get("pageId") or "") or None,
        author=row.get("ownerDisplayName") or row.get("ownerScreenName"),
        synced_for_page_id=page_id,
        text=(row.get("text") or "").strip(),
        url=row.get("link"),
        image_url=row.get("picture"),
        published_at=_published_at(row),
        reactions=row.get("reactions"),
        comments=row.get("comments"),
        shares=row.get("shares"),
    )


def fetch_competitor_posts(
    page: Page, days: int | None = None, timeout: float = 20.0
) -> list[SourceItemBase]:
    """Every competitor post in the window, for one Page's competitor set.

    Ordered by reactions, which is the Competitors tab's default sort and the only
    metric populated on effectively every row.

    Raises:
        MetricoolError: no `metricool_blog_id`, or the API refused.
    """
    if not page.metricool_blog_id:
        raise MetricoolError(f"{page.name} has no metricool_blog_id to sync against")

    with httpx.Client(timeout=timeout) as client:
        rows = _get(
            client,
            "/posts",
            page.metricool_blog_id,
            days if days is not None else sources.competitors.lookback_days,
        )

    assert page.id is not None
    items = [
        _to_source_item(row, page.id)
        for row in rows
        # A post with no text is nothing to borrow a voice from, and postId is
        # the dedup key — without it the row cannot be stored at all.
        if (row.get("text") or "").strip() and row.get("postId")
    ]
    items.sort(key=lambda item: item.reactions or 0, reverse=True)
    return items


def fetch_competitors(page: Page, timeout: float = 20.0) -> list[dict]:
    """The competitor list itself. Read live, never stored (ADR-0001's logic).

    Not on the HTTP surface — the Sources screen shows posts, not pages. It is
    here because it is the one call that answers "is this Page's Metricool
    competitor set actually configured", which is otherwise indistinguishable
    from a quiet week.
    """
    if not page.metricool_blog_id:
        raise MetricoolError(f"{page.name} has no metricool_blog_id to sync against")

    with httpx.Client(timeout=timeout) as client:
        rows = _get(client, "", page.metricool_blog_id, sources.competitors.lookback_days)

    return [
        {
            "provider_id": str(row.get("providerId") or ""),
            "name": row.get("displayName") or row.get("screenName") or "Competitor",
            "followers": row.get("followers"),
            # Facebook's CDN, signed and expiring — the `oe` parameter runs
            # about four days out. Safe to hand to the browser only because
            # this list is read live on every request and never stored, which
            # is exactly the opposite of what `routes/sources.VOLATILE` exists
            # to work around for competitor *posts*. Store this and the logos
            # go dead within the week.
            "picture": row.get("picture"),
        }
        for row in rows
    ]
