"""The YouTube tool's overview — what a channel put out and how it landed.

Reads Metricool's video stats, which are a different endpoint from the Facebook
post stats (`/stats/youtube/videos` rather than `/stats/facebook/posts`) but the
same bare-list envelope. Two facts about the read shape the screen:

- **It returns the whole channel catalog.** The `start`/`end` window is accepted
  and ignored — every window we tried against Bible Focus returned the same ~80
  videos, newest 2026-06-16. So the date split happens in the route, on the
  `publishedAt` each row carries, never in the query.
- **Views are the honest rank, not engagement.** These channels draw near-zero
  likes/comments/shares (0–13 on real rows) while views span orders of
  magnitude. Ranking by engagement would sort noise; the screen ranks by views
  and carries engagement as secondary figures.

The fetch functions take an injectable `client` so the suite can drive them
through `httpx.MockTransport` exactly as `test_publish.py` does.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.settings import settings

BASE = "https://app.metricool.com/api"


class OverviewError(RuntimeError):
    """The read failed. The screen says so rather than showing an empty grid
    that reads as a channel with nothing on it."""


def _headers() -> dict[str, str]:
    return {"X-Mc-Auth": settings.metricool_api_token}


@dataclass
class Brand:
    """A Metricool profile with a YouTube channel connected — the overview's
    unit of "brand", the way a Page row is the facebook tool's."""

    id: str
    label: str
    channel_id: str


def youtube_brands(client: httpx.Client | None = None) -> list[Brand]:
    """Every profile whose `youtube` field holds a channel id.

    The profile read comes from `app.sources.metricool.fetch_profiles`'s data;
    it is re-fetched here so the overview is self-contained and offline-testable,
    and because the profiles endpoint is the one place Metricool says which brand
    owns which channel.

    Verified live: 11 profiles, two with `youtube` set — Bible Focus and
    BibleFocusIO.
    """
    if not settings.metricool_api_token or not settings.metricool_user_id:
        raise OverviewError("Metricool is not configured (token and user id)")

    owned = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        response = client.get(
            f"{BASE}/admin/simpleProfiles",
            params={"userId": settings.metricool_user_id},
            headers=_headers(),
        )
    except httpx.HTTPError as error:
        raise OverviewError(
            f"Metricool did not answer the profile read: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise OverviewError(
            f"Metricool refused the profile read ({response.status_code}): "
            f"{response.text[:200]}"
        )

    out: list[Brand] = []
    for profile in response.json() or []:
        channel_id = profile.get("youtube")
        if not channel_id:
            continue
        out.append(
            Brand(
                id=str(profile.get("id") or ""),
                label=profile.get("label") or profile.get("id") or "?",
                channel_id=channel_id,
            )
        )
    return out


def youtube_videos(brand_id: str, client: httpx.Client | None = None) -> list[dict]:
    """Every video the channel has, with its metrics.

    The response rows carry `publishedAt` as epoch milliseconds and the stats as
    floats (13.0 views, not 13) — both normalised at the boundary where they are
    read, never downstream.
    """
    if not settings.metricool_api_token or not settings.metricool_user_id:
        raise OverviewError("Metricool is not configured (token and user id)")

    owned = client is None
    client = client or httpx.Client(timeout=60.0)
    try:
        # `YYYYMMDD`, the same bare form `/stats/facebook/posts` wants — the
        # window is ignored by Metricool, but sending a wide one keeps the call
        # honest if that ever changes.
        start = "20190101"
        end = "21000101"
        response = client.get(
            f"{BASE}/stats/youtube/videos",
            params={
                "userId": settings.metricool_user_id,
                "blogId": brand_id,
                "start": start,
                "end": end,
            },
            headers=_headers(),
        )
    except httpx.HTTPError as error:
        raise OverviewError(
            f"Metricool did not answer the video stats: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise OverviewError(
            f"Metricool refused the video stats ({response.status_code}): "
            f"{response.text[:200]}"
        )

    payload = response.json()
    return payload if isinstance(payload, list) else (payload.get("data") or [])
