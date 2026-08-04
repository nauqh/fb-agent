"""One tweet, resolved from a pasted URL.

Never a browsable list, which is why the Tweets tab is a paste box and not a
grid: the X API is paid per read, so this makes exactly one request per tweet
and the caller is expected to have deduplicated by id first.
"""

import re

import httpx

from app.models import SourceItemBase, SourceKind
from app.settings import settings

BASE = "https://api.x.com/2"

_TWEET_ID = re.compile(r"status(?:es)?/(\d+)")

_PARAMS = {
    # note_tweet carries the full text of a long-form tweet; `text` truncates it.
    "tweet.fields": "created_at,note_tweet,attachments",
    "expansions": "author_id,attachments.media_keys",
    "media.fields": "type,url,preview_image_url",
    "user.fields": "name,username",
}


class XError(RuntimeError):
    """A bad URL, an unconfigured token, or a tweet X will not serve."""


def parse_tweet_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    if value.isdigit():
        return value
    match = _TWEET_ID.search(value)
    if not match:
        raise XError(
            f"That does not look like a tweet URL — expected .../status/<id>, got {url_or_id!r}"
        )
    return match.group(1)


def fetch_tweet(url_or_id: str, timeout: float = 15.0) -> SourceItemBase:
    """Raises:
    XError: on a bad URL, a missing token, or a tweet X declines to serve.
    """
    if not settings.x_bearer_token:
        raise XError("missing X_BEARER_TOKEN")

    tweet_id = parse_tweet_id(url_or_id)

    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            f"{BASE}/tweets/{tweet_id}",
            params=_PARAMS,
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.is_error:
        raise XError(f"tweet fetch failed ({response.status_code}): {response.text[:200]}")

    data = payload.get("data")
    if not data:
        # v2 answers 200 with an `errors` array for a deleted, protected or
        # non-existent tweet, so status alone does not tell you it worked.
        errors = payload.get("errors") or payload
        detail = errors[0].get("detail") if isinstance(errors, list) and errors else errors
        raise XError(f"tweet not available: {detail}")

    author = (payload.get("includes", {}).get("users") or [{}])[0]
    username = author.get("username") or ""

    image_url = None
    for media in payload.get("includes", {}).get("media") or []:
        if media.get("type") == "photo" and media.get("url"):
            image_url = media["url"]
            break
        if media.get("type") in ("video", "animated_gif") and media.get(
            "preview_image_url"
        ):
            image_url = media["preview_image_url"]
            break

    return SourceItemBase(
        kind=SourceKind.TWEET,
        external_id=str(data["id"]),
        author=f"@{username}" if username else None,
        text=(data.get("note_tweet") or {}).get("text") or data.get("text") or "",
        url=f"https://x.com/{username or 'i'}/status/{data['id']}",
        image_url=image_url,
        published_at=data.get("created_at"),
    )
