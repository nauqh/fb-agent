"""Publishing a draft's article to the client's WordPress site.

Two calls: upload the featured image, then create the post as `publish`. Never
`draft` or `future`: a draft has no permalink yet (only `?p=<id>`), and the
link this returns goes into the post's first comment, so it has to be the real
one and live before Metricool has the post (website articles PRD).
"""

import httpx

from app.http import shared as http_shared
from app.settings import settings

TIMEOUT = 60.0


class WordPressError(RuntimeError):
    """The article did not go up. The post is then not scheduled either."""


def _call(client: httpx.Client, path: str, **kwargs) -> dict:
    try:
        response = client.post(
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


def publish(
    title: str, html: str, image: bytes | None, client: httpx.Client | None = None
) -> str:
    """Publish the article now. Returns its permalink."""
    if not (
        settings.wordpress_url and settings.wordpress_user and settings.wordpress_app_password
    ):
        raise WordPressError("WordPress is not configured (URL, user and application password)")

    client = client or http_shared(TIMEOUT)
    post = {"title": title, "content": html, "status": "publish"}
    if image:
        uploaded = _call(
            client,
            "media",
            content=image,
            headers={
                "Content-Type": "image/jpeg",
                "Content-Disposition": 'attachment; filename="article.jpg"',
            },
        )
        post["featured_media"] = uploaded["id"]
    return _call(client, "posts", json=post)["link"]
