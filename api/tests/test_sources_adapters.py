"""Normalisation, over recorded payloads. No network.

Each adapter's job is turning one vendor's shape into a `SourceItemBase`, so
that is what these test — the traps, not the happy path.
"""

from datetime import datetime, timezone

import pytest

from app.models import SourceKind
from app.settings import sources
from app.sources import metricool, rss, x

# --- Metricool -------------------------------------------------------------

# One real row from /v2/analytics/competitors/facebook/posts, trimmed.
COMPETITOR_ROW = {
    "pageId": "117997197937838",
    "postId": "117997197937838_989827367419507",
    "text": "  Gander, Newfoundland, before the war.  ",
    "link": "https://www.facebook.com/519574217778160/posts/989827367419507",
    "picture": "https://scontent.xx.fbcdn.net/v/t39.30808-6/762446395.jpg",
    "ownerDisplayName": "TerrifyingMyths",
    "ownerScreenName": "TerrifyingMyths",
    "reactions": 16,
    "comments": 0,
    "shares": 0,
    "created": 1785814399000,
    "timestamp": 1785814399000,
    "creationDate": {"dateTime": "2026-08-04T05:33:19", "timezone": "Europe/Madrid"},
}


def test_a_competitor_post_maps_onto_the_shared_shape():
    item = metricool._to_source_item(COMPETITOR_ROW, page_id=1)

    assert item.kind is SourceKind.COMPETITOR_POST
    assert item.external_id == "117997197937838_989827367419507"
    assert item.author == "TerrifyingMyths"
    assert item.synced_for_page_id == 1
    assert item.text == "Gander, Newfoundland, before the war."
    assert item.reactions == 16


def test_published_at_comes_from_the_epoch_not_the_local_string():
    """`creationDate.dateTime` is naive local time in the *account's* zone.

    It reads 05:33:19 with a `timezone` of Europe/Madrid regardless of the
    timezone parameter the request sends. Taking it as UTC puts every competitor post
    two hours out, which is invisible until the grid sorts wrongly.
    """
    item = metricool._to_source_item(COMPETITOR_ROW, page_id=1)

    assert item.published_at == datetime(2026, 8, 4, 3, 33, 19, tzinfo=timezone.utc)


def test_a_page_with_no_blog_id_fails_loudly():
    from app.models import Page

    page = Page(name="X", facebook_page_id="1", metricool_blog_id=None)
    with pytest.raises(metricool.MetricoolError, match="metricool_blog_id"):
        metricool.fetch_competitor_posts(page)


# --- RSS -------------------------------------------------------------------

FEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>History | smithsonianmag.com</title>
    <item>
      <title>The woman who mapped the ocean floor</title>
      <description><![CDATA[<p>Marie Tharp drew the ridge by hand &amp; was told it was
        girl talk.</p> The post The woman who mapped the ocean floor appeared first on Smithsonian.]]></description>
      <link>https://www.smithsonianmag.com/history/ocean-floor-180987410/</link>
      <guid isPermaLink="false">tag:smithsonianmag.com,2026:180987410</guid>
      <pubDate>Mon, 03 Aug 2026 09:15:00 +0000</pubDate>
      <media:content url="https://cdn.smithsonianmag.com/tharp.jpg" />
    </item>
    <item>
      <title>A headline with no summary</title>
      <description>A headline with no summary</description>
      <link>https://www.smithsonianmag.com/history/no-summary-180987411/</link>
      <pubDate>Sun, 02 Aug 2026 09:15:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def entries():
    import feedparser

    return feedparser.parse(FEED_XML).entries


def test_an_rss_item_carries_its_headline_and_summary(entries):
    item = rss._to_source_item(entries[0], "Smithsonian Magazine")

    assert item.kind is SourceKind.RSS
    # The link, not the guid — the guid here is an opaque internal tag that the
    # operator cannot open and `is_curated_url` cannot check.
    assert item.external_id == "https://www.smithsonianmag.com/history/ocean-floor-180987410/"
    assert item.author == "Smithsonian Magazine"
    assert item.text.startswith("The woman who mapped the ocean floor\n\n")
    assert "girl talk" in item.text
    assert item.image_url == "https://cdn.smithsonianmag.com/tharp.jpg"
    assert item.published_at == datetime(2026, 8, 3, 9, 15, tzinfo=timezone.utc)


def test_markup_entities_and_wordpress_boilerplate_are_stripped(entries):
    text = rss._to_source_item(entries[0], "Smithsonian Magazine").text

    assert "<p>" not in text
    assert "&amp;" not in text and " & " in text
    # WordPress appends this to every summary; unstripped it reaches the model
    # as content.
    assert "appeared first on" not in text


def test_a_summary_that_only_restates_the_headline_is_dropped(entries):
    """Otherwise the writer gets the same sentence twice and reads it as detail."""
    item = rss._to_source_item(entries[1], "Smithsonian Magazine")

    assert item.text == "A headline with no summary"


def test_an_entry_with_no_link_is_skipped(entries):
    entry = dict(entries[0])
    entry.pop("link")

    assert rss._to_source_item(entry, "Smithsonian Magazine") is None


def test_only_curated_hosts_pass_the_guard():
    assert rss.is_curated_url("https://www.smithsonianmag.com/history/x/")
    assert rss.is_curated_url("https://allthatsinteresting.com/y")
    assert not rss.is_curated_url("https://evil.example/z")
    assert not rss.is_curated_url(None)


def test_every_curated_feed_host_is_one_an_item_can_come_from():
    """The guard compares an *item* URL against *feed* hosts.

    That only holds while each publisher serves both from one host — a feed
    moved to feedburner would silently start refusing its own items.
    """
    for feeds in sources.feeds.values():
        for feed in feeds:
            assert rss.is_curated_url(feed.url), feed.name


def test_a_page_with_no_feeds_configured_raises():
    """Rather than returning an empty grid, which reads as a quiet week."""
    with pytest.raises(KeyError, match="No feeds configured"):
        sources.feeds_for("A Page That Does Not Exist")


def test_merge_drops_stale_items_and_duplicate_stories():
    from app.models import SourceItemBase

    now = datetime.now(timezone.utc)
    old = now.replace(year=now.year - 1)

    merged = rss._merge(
        [
            SourceItemBase(kind=SourceKind.RSS, external_id="a", text="Same story\n\none", published_at=now),
            # Same story, different URL — routine across these seven feeds.
            SourceItemBase(kind=SourceKind.RSS, external_id="b", text="Same story\n\ntwo", published_at=now),
            SourceItemBase(kind=SourceKind.RSS, external_id="c", text="Ancient", published_at=old),
        ]
    )

    assert [item.external_id for item in merged] == ["a"]


# --- X ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "https://x.com/qikipedia/status/1816003348871142219",
        "https://twitter.com/qikipedia/statuses/1816003348871142219?s=20",
        "1816003348871142219",
    ],
)
def test_a_tweet_id_is_parsed_from_the_forms_people_paste(value):
    assert x.parse_tweet_id(value) == "1816003348871142219"


def test_a_url_with_no_tweet_id_is_refused():
    with pytest.raises(x.XError, match="status"):
        x.parse_tweet_id("https://x.com/qikipedia")


class _Response:
    """Stands in for httpx's, so the paid API is not called."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def x_api(monkeypatch):
    """Serve one canned payload, and record that exactly one read happened."""
    calls: list[str] = []

    def serve(payload: dict, status_code: int = 200):
        class Client:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def get(self, url, **_):
                calls.append(url)
                return _Response(payload, status_code)

        monkeypatch.setattr(x.httpx, "Client", lambda **_: Client())
        monkeypatch.setattr(x.settings, "x_bearer_token", "test-token")
        return calls

    return serve


TWEET_PAYLOAD = {
    "data": {
        "id": "1816003348871142219",
        "text": "The last man executed in the Tower of London was shot in 1941, in a…",
        "created_at": "2026-08-03T09:15:00.000Z",
        "note_tweet": {
            "text": "The last man to be executed in the Tower of London was shot in 1941, "
            "in a miniature rifle range, sitting in an ordinary wooden chair."
        },
    },
    "includes": {
        "users": [{"name": "QI", "username": "qikipedia"}],
        "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}],
    },
}


def test_a_tweet_maps_onto_the_shared_shape(x_api):
    calls = x_api(TWEET_PAYLOAD)

    item = x.fetch_tweet("https://x.com/qikipedia/status/1816003348871142219")

    assert item.kind is SourceKind.TWEET
    assert item.external_id == "1816003348871142219"
    assert item.author == "@qikipedia"
    assert item.url == "https://x.com/qikipedia/status/1816003348871142219"
    assert item.image_url == "https://pbs.twimg.com/media/abc.jpg"
    # X sends "…Z"; the column is a datetime, so the coercion has to hold.
    assert item.published_at == datetime(2026, 8, 3, 9, 15, tzinfo=timezone.utc)
    # Paid per read. One tweet, one request.
    assert len(calls) == 1


def test_the_full_text_of_a_long_tweet_wins_over_the_truncated_one(x_api):
    x_api(TWEET_PAYLOAD)

    text = x.fetch_tweet("1816003348871142219").text

    assert text.endswith("ordinary wooden chair.")
    assert "…" not in text


def test_a_deleted_tweet_raises_even_though_x_answers_200(x_api):
    """v2 returns 200 with an `errors` array, so status alone says nothing."""
    x_api({"errors": [{"detail": "Could not find post with id: [1]."}]})

    with pytest.raises(x.XError, match="Could not find post"):
        x.fetch_tweet("1")


def test_no_token_is_refused_before_the_request(monkeypatch):
    monkeypatch.setattr(x.settings, "x_bearer_token", "")

    with pytest.raises(x.XError, match="X_BEARER_TOKEN"):
        x.fetch_tweet("https://x.com/a/status/1")
