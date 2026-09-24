"""One web page, resolved from a pasted URL.

Same shape as the Tweets tab: never a browsable list, one paste box, one lookup
at a time. This module reads the page server-side with stdlib HTMLParser only -
`<meta>` tags for the stub, and the `<p>` text for the body. That body **is**
the source: the writer does not fetch a WEB item's URL, because Gemini's reader
is refused by robots.txt on whole publisher networks (Australian Community
Media, the BBC) that serve plain HTML to this module.

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
# Text of these never reads as article prose.
_SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside", "form"})
# A paragraph shorter than this is a byline, a caption or a menu item.
_MIN_PARAGRAPH = 40
# The writer's prompt carries this; a full longread is past 40k characters and
# the model needs the story, not every sentence of it.
_MAX_BODY_CHARS = 12_000
# Below this the page is not an article: a JS shell, a cookie or paywall notice.
# Real articles measured 3,900+ characters; those non-articles 0-80.
_MIN_BODY_CHARS = 500


class WebError(RuntimeError):
    """A URL that is not a fetchable web page, or a page with nothing usable."""


class _Page(HTMLParser):
    """One parse pass for everything the adapter needs: `<meta>`, `<title>`,
    and the text of the `<p>` tags, skipping chrome. Stdlib, so no new
    dependency for a job BeautifulSoup would be one meta tag too many for."""

    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title = ""
        self.paragraphs: list[str] = []
        self._in_title = False
        self._in_p = False
        self._skip_depth = 0
        self._chunks: list[str] = []

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
        elif tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "p" and not self._skip_depth:
            self._in_p = True
            self._chunks = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "p" and self._in_p:
            self._in_p = False
            # Collapse whitespace the HTML carries; the writer reads this text.
            text = " ".join("".join(self._chunks).split())
            if len(text) >= _MIN_PARAGRAPH:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_p and not self._skip_depth:
            self._chunks.append(data)


def fetch_article(url: str, client: httpx.Client | None = None) -> SourceItemBase:
    """Raises:
    WebError: on a non-http URL, a refused page, or one with no title at all.
    """
    value = url.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise WebError(f"That does not look like a web URL: {url!r}")

    try:
        with client or httpx.Client(
            timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as session:
            response = session.get(value, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        # 401/403 is a bot wall (AP, NYT, Smithsonian); a browser user agent
        # does not get past it either, so the message says so rather than retry.
        code = error.response.status_code
        if code in (401, 403):
            raise WebError(
                f"The site refused the request ({code}) - it blocks automated "
                "readers. Try another source for the story."
            ) from error
        raise WebError(f"The page did not answer ({code}).") from error
    except httpx.HTTPError as error:
        raise WebError(f"The page did not answer: {type(error).__name__}") from error

    page = _Page()
    page.feed(response.text)

    # What the redirects landed on, not what was pasted - trackers, shorteners
    # and syndication hosts otherwise give one article several identities, and
    # `(kind, external_id)` is unique.
    final_url = urldefrag(str(response.url)).url

    title = page.meta.get("og:title") or page.title.strip()
    if not title:
        raise WebError(f"No title found on {final_url} - it may not be an article")

    published_at = None
    stamp = page.meta.get("article:published_time")
    if stamp:
        try:
            published_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            pass

    body = "\n\n".join(page.paragraphs)
    # Refused on screen, not handed to the writer as a headline it would invent
    # a post around.
    if len(body) < _MIN_BODY_CHARS:
        raise WebError(
            f"Could not read the article text on {final_url} - the page may need "
            "JavaScript or a login. Try another source for the story."
        )
    if len(body) > _MAX_BODY_CHARS:
        body = body[:_MAX_BODY_CHARS]

    return SourceItemBase(
        kind=SourceKind.WEB,
        external_id=final_url,
        author=page.meta.get("og:site_name") or parts.netloc,
        text="\n\n".join(
            part
            for part in (title, page.meta.get("og:description"), body)
            if part
        ),
        url=final_url,
        image_url=page.meta.get("og:image"),
        published_at=published_at,
    )
