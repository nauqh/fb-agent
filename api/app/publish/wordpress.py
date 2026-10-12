"""Publishing a draft's article to the client's WordPress site.

Two calls: upload the picture, then create the post as `publish`. Never
`draft` or `future`: a draft has no permalink yet (only `?p=<id>`), and the
link this returns goes into the post's first comment, so it has to be the real
one and live before Metricool has the post (website articles PRD).
"""

from html import escape

import httpx

from app.http import shared as http_shared
from app.settings import settings

TIMEOUT = 60.0


class WordPressError(RuntimeError):
    """The article did not go up. The post is then not scheduled either."""


def _configured() -> None:
    if not (
        settings.wordpress_url and settings.wordpress_user and settings.wordpress_app_password
    ):
        raise WordPressError("WordPress is not configured (URL, user and application password)")


def _call(client: httpx.Client, path: str, method: str = "POST", **kwargs) -> dict | list:
    try:
        response = client.request(
            method,
            f"{settings.wordpress_url.rstrip('/')}/wp-json/wp/v2/{path}",
            auth=(settings.wordpress_user, settings.wordpress_app_password),
            **kwargs,
        )
    except httpx.HTTPError as error:
        raise WordPressError(f"WordPress did not answer: {type(error).__name__}") from error
    if response.is_error:
        raise WordPressError(
            f"WordPress refused the {path} ({response.status_code}): {response.text[:300]}"
        )
    return response.json()


def categories(client: httpx.Client | None = None) -> list[dict]:
    """The site's categories, read live: they are kept in WordPress, not here.
    Uncategorized is left out, since an article filed there gets
    `/uncategorized/` in its address."""
    _configured()
    rows = _call(
        client or http_shared(TIMEOUT),
        "categories",
        method="GET",
        params={"per_page": 100, "orderby": "name", "_fields": "id,name,slug"},
    )
    return [{"id": row["id"], "name": row["name"]} for row in rows if row["slug"] != "uncategorized"]


def _figure(uploaded: dict, caption: str | None) -> str:
    """The uploaded image as a full-size image block, captioned when there is one."""
    details = uploaded.get("media_details") or {}
    size = (
        f' width="{details["width"]}" height="{details["height"]}"'
        if details.get("width") and details.get("height")
        else ""
    )
    text = escape(caption or "")
    return (
        '<figure class="wp-block-image size-full">'
        f'<img src="{escape(uploaded["source_url"])}" alt="{text}"{size}'
        f' class="wp-image-{uploaded["id"]}"/>'
        + (f'<figcaption class="wp-element-caption">{text}</figcaption>' if text else "")
        + "</figure>\n"
    )


def publish(
    title: str,
    html: str,
    image: bytes | None,
    category: int | None,
    caption: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Publish the article now. Returns its permalink, which carries the
    category once the site's permalinks are `/%category%/%postname%/`."""
    _configured()

    client = client or http_shared(TIMEOUT)
    post = {"title": title, "content": html, "status": "publish"}
    if category:
        post["categories"] = [category]
    if image:
        # Multipart, so the caption and alt text go up with the file.
        uploaded = _call(
            client,
            "media",
            files={"file": ("article.jpg", image, "image/jpeg")},
            data={"caption": caption or "", "alt_text": caption or ""},
        )
        # In the body only, never as the featured image: SmartMag crops that to
        # a 788x438 banner, which cut the face off a tall hero (2026-10-13), and
        # shows a picture in the body whole. The cost is no thumbnail in the
        # site's listings, like the site's own posts (client, 2026-10-13).
        post["content"] = _figure(uploaded, caption) + html
    return _call(client, "posts", json=post)["link"]
