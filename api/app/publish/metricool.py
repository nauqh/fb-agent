"""Handing a post to Metricool's planner.

Two calls: normalize the image URL, then schedule. Metricool owns everything
after that — it publishes to Facebook and posts the first comment itself
(`autoPublish: true`, `firstCommentText`), so this repo never touches the Graph
API and never has to come back to finish the job.

The auth shape is duplicated from `sources/metricool.py` rather than shared, and
deliberately: that module talks to competitor *analytics*, which takes a date
window and a blog id, while this one talks to the *scheduler*, which takes a
`userToken` in the query string as well as the `X-Mc-Auth` header. The overlap
is two dict literals; a shared helper covering both would take a mode flag,
which is not an abstraction.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.settings import settings

BASE = "https://app.metricool.com/api"

TIMEOUT = 60.0

MIN_MINUTES_AHEAD = 2
"""Metricool rejects a publication date in the past, and the request itself
takes seconds. The old system used one minute; two costs nothing and removes a
race with its own clock."""


class PublishError(RuntimeError):
    """The post did not reach the planner. Lands on the row, never swallowed."""


def _params(blog_id: str, **extra: str) -> dict[str, str]:
    return {
        "userToken": settings.metricool_api_token,
        "userId": settings.metricool_user_id,
        "blogId": blog_id,
        **extra,
    }


def _headers(json_body: bool = False) -> dict[str, str]:
    """No `Accept` unless a JSON body is going out.

    Sending `Accept: application/json` on the GET answers **500 "No acceptable
    representation"** — normalize returns a bare URL as text/plain and content
    negotiation fails. Found by watching it fail against the live API; the old
    client omits the header on GET for the same reason
    (`metricoolService.ts:72`).
    """
    headers = {"X-Mc-Auth": settings.metricool_api_token}
    if json_body:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    return headers


def normalize_image(url: str, blog_id: str, client: httpx.Client | None = None) -> str:
    """Register the image with Metricool, and return the URL to attach.

    **Metricool does not take its own copy.** Their help centre says this
    endpoint "ensures the file is hosted on Metricool's servers and returns a
    valid mediaId"; tested against the live API with both a JPEG and a PNG, it
    echoed each URL back unchanged and returned no id at all. So the bucket URL
    is what ends up in the post, and it has to still resolve when Facebook
    fetches it at publish time — which is why the bucket is public and unsigned.

    It is still called, because their own troubleshooting page says a post
    scheduled without normalizing first silently loses its media.
    """
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        response = client.get(
            f"{BASE}/actions/normalize/image/url",
            params=_params(blog_id, url=url),
            headers=_headers(),
        )
    except httpx.HTTPError as error:
        raise PublishError(
            f"Metricool did not answer the image normalize: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise PublishError(
            f"Metricool rejected the image ({response.status_code}): "
            f"{response.text[:200]}"
        )

    normalized = response.text.strip().strip('"')
    if not normalized.startswith("http"):
        raise PublishError(
            f"Metricool returned no usable image URL: {response.text[:200]}"
        )
    return normalized


def publication_date(when: datetime | None = None) -> str:
    """Naive local time in the page's timezone, which is what Metricool wants.

    It takes the timezone as a separate field and **rejects an offset suffix**,
    so this must not be an ISO instant. The same trap on the read side is
    already recorded in plan.md:116 — Metricool's `creationDate.dateTime` is
    naive local time in the account's own timezone, not UTC.
    """
    zone = ZoneInfo(settings.timezone)
    earliest = datetime.now(zone) + timedelta(minutes=MIN_MINUTES_AHEAD)

    if when is None:
        local = earliest
    else:
        local = when.astimezone(zone) if when.tzinfo else when.replace(tzinfo=zone)
        local = max(local, earliest)

    return local.strftime("%Y-%m-%dT%H:%M:%S")


def build_body(
    text: str,
    first_comment: str | None,
    image_url: str | None,
    when: datetime | None = None,
) -> dict:
    """The scheduler payload, shaped as the old system shaped it.

    `media` is a **list**, not `{"mediaId": ...}`. Metricool's docs recommend the
    id form, but the id only exists when normalize re-hosts the file, which it
    does not do for ours — and the old client carried a comment saying Facebook
    photo posts are more reliable with URL arrays either way.

    `autoPublish` and `firstCommentText` are what make Metricool the publisher
    rather than us: it posts to the page and adds the first comment on its own.
    """
    body = {
        "text": text,
        "firstCommentText": first_comment or "",
        "autoPublish": True,
        "draft": settings.metricool_publish_as_draft,
        "providers": [{"network": "facebook", "facebookData": {"type": "POST"}}],
        "publicationDate": {
            "dateTime": publication_date(when),
            "timezone": settings.timezone,
        },
    }
    # Omitted rather than sent empty for a text-only post. `"media": []` and
    # `"media": [null]` are both a media field Metricool then has to interpret,
    # and the type stays `POST` either way — a Facebook status update is a post
    # with no attachment, not a different kind of publication.
    if image_url:
        body["media"] = [image_url]
    return body


def list_scheduled(
    blog_id: str,
    start: datetime,
    end: datetime,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Everything in Metricool's planner for a window. The whole schedule screen.

    Read live, every time, because **there is no local copy to read instead**
    (ADR-0001). The old system mirrored this into a `facebook_schedules` table
    and production held 0 rows against 237 approved drafts; the planner is where
    posts are actually scheduled, rescheduled and cancelled, including by hand
    in Metricool's own UI. A mirror could only ever be wrong.

    Dates go out in the same naive-local form as everything else here. Asking
    for `20260801` answers 400 with the accepted format spelled out, which is
    how this one was got right.
    """
    if not settings.metricool_api_token or not settings.metricool_user_id:
        raise PublishError("Metricool is not configured (token and user id)")

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        response = client.get(
            f"{BASE}/v2/scheduler/posts",
            params=_params(
                blog_id,
                start=start.strftime("%Y-%m-%dT%H:%M:%S"),
                end=end.strftime("%Y-%m-%dT%H:%M:%S"),
                timezone=settings.timezone,
            ),
            headers=_headers(),
        )
    except httpx.HTTPError as error:
        raise PublishError(
            f"Metricool did not answer the planner: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise PublishError(
            f"Metricool refused the planner read ({response.status_code}): "
            f"{response.text[:200]}"
        )

    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    return rows or []


def _post_id(payload: object) -> str | None:
    """Dig the id out of whatever shape came back.

    The old client searched `data`, `result`, `response`, `payload` and `post`
    before giving up and matching against recent planner posts by text prefix
    and scheduled time. The nesting is real; the fuzzy matching is not ported —
    guessing which planner row is ours from a 64-character prefix is a way to
    write the wrong id onto a Draft, and a missing id is the more honest answer.
    """
    if isinstance(payload, list):
        for item in payload:
            found = _post_id(item)
            if found:
                return found
        return None

    if not isinstance(payload, dict):
        return None

    for key in ("id", "postId", "schedulerPostId"):
        value = payload.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()

    for key in ("data", "result", "response", "payload", "post"):
        nested = payload.get(key)
        if isinstance(nested, (dict, list)):
            found = _post_id(nested)
            if found:
                return found

    return None


def schedule(
    blog_id: str,
    text: str,
    first_comment: str | None,
    image_url: str | None,
    when: datetime | None = None,
    client: httpx.Client | None = None,
) -> str | None:
    """Queue the post. Returns Metricool's id for it, if it gave one.

    `None` is not a failure — the call succeeded and the post is in the planner;
    Metricool simply did not name it in the response. The Draft records what it
    can and the planner remains the source of truth either way (ADR-0001).
    """
    if not settings.metricool_api_token or not settings.metricool_user_id:
        raise PublishError("Metricool is not configured (token and user id)")

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        response = client.post(
            f"{BASE}/v2/scheduler/posts",
            params=_params(blog_id),
            headers=_headers(json_body=True),
            json=build_body(text, first_comment, image_url, when),
        )
    except httpx.HTTPError as error:
        raise PublishError(
            f"Metricool did not answer the schedule: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise PublishError(
            f"Metricool refused the post ({response.status_code}): "
            f"{response.text[:300]}"
        )

    try:
        return _post_id(response.json())
    except ValueError:
        return None
