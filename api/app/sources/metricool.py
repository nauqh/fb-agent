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

from dataclasses import dataclass
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
            # Metricool's own row id, which is what DELETE takes — *not* the
            # providerId, which is Facebook's. Confirmed by adding a page and
            # removing it: `competitorId=342033` worked, the providerId did not.
            "id": row.get("id"),
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


def add_competitor(page: Page, facebook_page_id: str, timeout: float = 20.0) -> None:
    """Add a Facebook page to this Metricool profile's competitor set.

    Their list stays authoritative — this drives it rather than keeping a copy
    beside it, which is what `CONTEXT.md` means by the list being configured in
    Metricool and never stored here.

    Verified against the live account: `POST` with `id` set to the Facebook page
    id answers `{"data": true}` and the page appears in the next `GET`. `PUT` is
    not supported at all, so there is no edit — remove and re-add.

    Remember the ceiling. A Metricool account may hold **100 competitors in
    total**, across every profile, which is the whole reason competitors are a
    shared pool here rather than a per-Page list.
    """
    if not page.metricool_blog_id:
        raise MetricoolError(f"{page.name} has no metricool_blog_id")

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{BASE}/v2/analytics/competitors/facebook",
            params={
                **_params(page.metricool_blog_id, sources.competitors.lookback_days),
                "id": facebook_page_id,
            },
            headers=_headers(),
        )

    if response.is_error:
        raise MetricoolError(
            f"Metricool refused that competitor ({response.status_code}): "
            f"{response.text[:200]}"
        )


def remove_competitor(page: Page, competitor_id: int, timeout: float = 20.0) -> None:
    """Remove one from the set. `competitor_id` is Metricool's row id.

    Not the `providerId`: their DELETE names the parameter `competitorId` and
    means their own primary key, which is why `fetch_competitors` carries `id`
    alongside `provider_id`.
    """
    if not page.metricool_blog_id:
        raise MetricoolError(f"{page.name} has no metricool_blog_id")

    with httpx.Client(timeout=timeout) as client:
        response = client.request(
            "DELETE",
            f"{BASE}/v2/analytics/competitors/facebook",
            params={
                **_params(page.metricool_blog_id, sources.competitors.lookback_days),
                "competitorId": competitor_id,
            },
            headers=_headers(),
        )

    if response.is_error:
        raise MetricoolError(
            f"Metricool would not remove that competitor ({response.status_code}): "
            f"{response.text[:200]}"
        )


@dataclass
class ProfileUsage:
    """One Metricool profile and how many competitors it holds."""

    blog_id: str
    label: str
    competitors: int
    managed: bool
    """Whether this app has a Page for it. Most of the account is not ours."""


@dataclass
class Allowance:
    """How much of the account's competitor limit is spent.

    **The limit is per account, not per profile**, which is the fact the whole
    shared-pool design rests on. Counting only the profiles this app manages
    would understate it badly: measured on this account, 92 of 100 were in use
    and 44 of those sat on profiles with no Page here at all — so an operator
    reading "48 configured" would think they had 52 slots and actually have 8.
    """

    used: int
    limit: int
    profiles: list[ProfileUsage]

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


COMPETITOR_LIMIT = 100
"""Metricool's cap, per account. Not discoverable from their API — it is a plan
limit, and the only way it announces itself is a refusal on the 101st add."""


def fetch_profiles(timeout: float = 30.0) -> list[dict]:
    """Every profile on the account, not just the ones with a Page here."""
    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            f"{BASE}/admin/simpleProfiles",
            params={"userId": settings.metricool_user_id},
            headers=_headers(),
        )
    if response.is_error:
        raise MetricoolError(
            f"Metricool profiles failed ({response.status_code}): {response.text[:200]}"
        )
    # A bare list, not the `{"data": …}` envelope the analytics endpoints use.
    return response.json()


def fetch_allowance(managed_blog_ids: set[str], timeout: float = 40.0) -> Allowance:
    """Count competitors across every profile on the account.

    One request per profile — eleven on this account — because there is no
    endpoint that answers the total. Slow enough to be worth knowing about
    (several seconds), which is why it is its own call rather than folded into
    the competitor list.

    A profile that errors is counted as zero rather than failing the whole
    reading: a partial total with the rest of the screen working beats no number
    at all, and the count is a budget indicator rather than an invariant.
    """
    profiles = fetch_profiles(timeout=timeout)

    usage: list[ProfileUsage] = []
    with httpx.Client(timeout=timeout) as client:
        for profile in profiles:
            blog_id = str(profile.get("id") or "")
            response = client.get(
                f"{BASE}/v2/analytics/competitors/facebook",
                params=_params(blog_id, sources.competitors.lookback_days),
                headers=_headers(),
            )
            count = (
                len(response.json().get("data") or []) if not response.is_error else 0
            )
            usage.append(
                ProfileUsage(
                    blog_id=blog_id,
                    label=str(profile.get("label") or profile.get("title") or blog_id),
                    competitors=count,
                    managed=blog_id in managed_blog_ids,
                )
            )

    # Spent first: the profiles with none are not what anyone is looking for.
    usage.sort(key=lambda one: (-one.competitors, one.label))
    return Allowance(
        used=sum(one.competitors for one in usage),
        limit=COMPETITOR_LIMIT,
        profiles=usage,
    )
