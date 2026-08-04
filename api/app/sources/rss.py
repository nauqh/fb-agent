"""RSS items, from a Page's curated feeds.

Which feeds, and how wide a window, live in
[`config/sources.yml`](../../config/sources.yml) — curated rather than managed
in a UI, because the list churns slowly and every candidate has to be probed
before it earns a place, which is not a thing to do from a form. There is no
`feed` table for the same reason nothing points at one; see data-model.md,
"What was considered and rejected".

Browsing does not write. This module only ever *returns* items; they become rows
when the operator ticks them, which is what keeps `source_item` from filling
with hundreds of unread items.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from urllib.parse import urlsplit

import feedparser
import httpx

from app.models import SourceItemBase, SourceKind
from app.settings import Feed, sources

USER_AGENT = "Mozilla/5.0 (compatible; fb-agent/1.0)"
"""Several publisher feeds 403 a request that sends none. Not configurable: it
is part of how the fetch works, not a thing an operator would tune."""


@dataclass
class FeedFailure:
    feed_url: str
    error: str


@dataclass
class RssFeed:
    """Items, *and* the feeds that did not answer.

    The failures are returned rather than logged because a feed that rots is
    invisible off-screen: the grid simply gets quieter, which looks like a slow
    news week for as long as nobody checks. One 403 must not empty the grid, and
    it must not pass unnoticed either.
    """

    items: list[SourceItemBase] = field(default_factory=list)
    failures: list[FeedFailure] = field(default_factory=list)


_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_BOILERPLATE = [
    # WordPress appends a self-referential tail to every summary, which would
    # otherwise reach the model as content.
    re.compile(r"\s*The post .*? appeared first on .*?\.?\s*$", re.I),
    re.compile(r"\s*Continue reading\b.*$", re.I),
    re.compile(r"\s*\[…\]\s*$"),
    re.compile(r"\s*Read more\s*$", re.I),
]


def _plain(value: str | None) -> str:
    """Feed markup down to text."""
    if not value:
        return ""
    return _SPACE.sub(" ", unescape(_TAGS.sub(" ", value))).strip()


def _summary(entry) -> str:
    text = _plain(entry.get("summary"))
    if not text and entry.get("content"):
        text = _plain(entry.content[0].get("value"))
    for pattern in _BOILERPLATE:
        text = pattern.sub("", text)
    return text.strip()


def _comparable(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _published_at(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _image_url(entry) -> str | None:
    for media in entry.get("media_content") or []:
        if media.get("url"):
            return media["url"]
    for thumb in entry.get("media_thumbnail") or []:
        if thumb.get("url"):
            return thumb["url"]
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith(
            "image"
        ):
            return link.get("href")
    inline = re.search(
        r"<img[^>]+src=[\"']([^\"']+)[\"']", entry.get("summary") or "", re.I
    )
    return inline.group(1) if inline else None


def _to_source_item(entry, publisher: str | None) -> SourceItemBase | None:
    title = _plain(entry.get("title"))
    link = entry.get("link")
    if not title or not link:
        return None

    summary = _summary(entry)
    # A summary that merely restates the headline adds nothing.
    if _comparable(summary) == _comparable(title):
        summary = ""

    return SourceItemBase(
        kind=SourceKind.RSS,
        # The link, not the feed's guid. It is what the operator can open, and
        # what `is_curated_url` is checked against on the way back in — a guid
        # is often an opaque internal id that answers neither.
        external_id=link,
        author=publisher,
        text=f"{title}\n\n{summary}" if summary else title,
        url=link,
        image_url=_image_url(entry),
        published_at=_published_at(entry),
    )


def _fetch_one(client: httpx.Client, feed: Feed) -> list[SourceItemBase]:
    response = client.get(feed.url)
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    items = (_to_source_item(entry, feed.name) for entry in parsed.entries)
    return [item for item in items if item is not None]


def fetch_rss(page_name: str, timeout: float = 10.0) -> RssFeed:
    """Every feed configured for this Page, merged, deduplicated, newest first.

    Feeds break often — dead paths, 403s and hangs are all routine — so a
    failing feed is collected rather than raised, and never sinks the batch.

    Raises:
        KeyError: the Page has no feeds in `config/sources.yml`. Loud, because
            an empty grid is indistinguishable from a quiet week.
    """
    feeds = sources.feeds_for(page_name)
    results: list[SourceItemBase] = []
    failures: list[FeedFailure] = []

    def load(feed: Feed) -> tuple[Feed, list[SourceItemBase] | Exception]:
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                return feed, _fetch_one(client, feed)
        except Exception as error:  # noqa: BLE001 — one bad feed must not sink the rest
            return feed, error

    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        for feed, outcome in pool.map(load, feeds):
            if isinstance(outcome, Exception):
                failures.append(FeedFailure(feed.url, _describe(outcome)))
            else:
                results.extend(outcome)

    return RssFeed(items=_merge(results), failures=failures)


def _describe(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"{error.response.status_code} {error.response.reason_phrase}"
    if isinstance(error, httpx.TimeoutException):
        return "timed out"
    return f"{type(error).__name__}: {error}"


def _merge(items: list[SourceItemBase]) -> list[SourceItemBase]:
    """Windowed, deduplicated, newest first, capped.

    Deduplicated on url *and* again on normalised title, because the same story
    routinely runs in several of these feeds under different URLs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=sources.rss.since_days)
    seen: set[str] = set()
    merged: list[SourceItemBase] = []

    for item in items:
        if item.published_at and item.published_at < cutoff:
            continue
        keys = (f"u:{item.external_id}", f"t:{_comparable(item.text.split(chr(10))[0])}")
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        merged.append(item)

    merged.sort(
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return merged[: sources.rss.max_items]


def is_curated_url(url: str | None) -> bool:
    """Whether a posted item actually came from a configured feed.

    The RSS tab is live, so the client posts the item body back when one is
    ticked — the server holds no copy to compare against. Without this check
    `POST /sources` accepts arbitrary text and hands it to the writer, and
    "fully curated" is an intention rather than a property.

    Checked against every Page's hosts, not one Page's, because an RSS item is
    not tied to a Page and `POST /sources` has none to check against. The
    question it answers is "is this one of ours".
    """
    return bool(url) and urlsplit(url).hostname in sources.curated_hosts
