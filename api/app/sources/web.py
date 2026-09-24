"""One web page, resolved from a pasted URL.

Same shape as the Tweets tab: never a browsable list, one paste box, one lookup
at a time. The page's own `<head>` is all this module reads - title, description,
og:image, publish time - because the article body is fetched by the writer
itself, through the same URL-context mechanism an RSS link uses. A second body
extractor here would be a parser to maintain for text the model throws away.

Browsing does not write, like every adapter here: the item becomes a row only
when a run uses it.
"""

from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urlsplit

import httpx

from app.models import SourceItemBase, SourceKind
from app.sources.rss import USER_AGENT

FETCH_TIMEOUT = 20.0
# og:image can be set per size; the plain one is the full-resolution image.
_META_KEYS = ("og:title", "og:description", "og:site_name", "og:image")


class WebError(RuntimeError):
    """A URL that is not a fetchable web page, or a page with nothing usable."""


class _Head(HTMLParser):
    """The `<meta>` tags and `<title>` of one page. Stdlib, so no new dependency
    for a job BeautifulSoup would be one meta tag too many for."""

    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            pairs = dict(attrs)
            key = pairs.get("property") or pairs.get("name")
            content = pairs.get("content")
            if key and content:
                # First one wins: og tags repeat per locale and per crop.
                self.meta.setdefault(key, content)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def fetch_article(url: str, client: httpx.Client | None = None) -> SourceItemBase:
    """Raises:
    WebError: on a non-http URL, a refused page, or one with no title at all.
    """
    value = url.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise WebError(f"That does not look like a web URL: {url!r}")

    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            response = client.get(value, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise WebError(f"The page did not answer: {error}") from error

    head = _Head()
    head.feed(response.text)

    # What the redirects landed on, not what was pasted - trackers, shorteners
    # and syndication hosts otherwise give one article several identities, and
    # `(kind, external_id)` is unique.
    final_url = urldefrag(str(response.url)).url

    title = head.meta.get("og:title") or head.title.strip()
    if not title:
        raise WebError(f"No title found on {final_url} - it may not be an article")

    published_at = None
    stamp = head.meta.get("article:published_time")
    if stamp:
        try:
            published_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            pass

    return SourceItemBase(
        kind=SourceKind.WEB,
        external_id=final_url,
        author=head.meta.get("og:site_name") or parts.netloc,
        text="\n\n".join(
            part for part in (title, head.meta.get("og:description")) if part
        ),
        url=final_url,
        image_url=head.meta.get("og:image"),
        published_at=published_at,
    )