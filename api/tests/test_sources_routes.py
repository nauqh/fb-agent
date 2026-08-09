"""Browsing does not write.

Every route here reads. What used to be tested against `POST /sources` — the
curated-feed guard, dedup, and not rewriting an existing row — moved to
tests/test_generate.py when generate became the only write point.
"""

from datetime import datetime, timezone

from sqlmodel import Session, func, select

from app.models import Page, SourceItem, SourceItemBase, SourceKind
from app.routes import sources as routes
from app.settings import sources as sources_config
from app.sources import rss


def _count(engine, kind: SourceKind | None = None) -> int:
    with Session(engine) as session:
        query = select(func.count()).select_from(SourceItem)
        if kind is not None:
            query = query.where(SourceItem.kind == kind)
        return session.exec(query).one()


CURATED_RSS_URL = "https://www.smithsonianmag.com/history/a-story-180987410/"


def test_browsing_rss_writes_nothing(client, engine, monkeypatch):
    monkeypatch.setattr(
        rss,
        "fetch_rss",
        lambda _page_name: rss.RssFeed(
            items=[SourceItemBase(kind=SourceKind.RSS, external_id=CURATED_RSS_URL)],
            failures=[rss.FeedFailure("http://dead.example/feed", "504")],
        ),
    )

    response = client.get("/sources/rss", params={"page_id": 1})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    # Surfaced, not logged: a feed that rots is invisible off-screen.
    assert response.json()["failures"] == [
        {"feed_url": "http://dead.example/feed", "error": "504"}
    ]
    assert _count(engine) == 0


def test_competitor_posts_are_written_on_arrival_and_sorted_newest_first(
    client, engine, monkeypatch
):
    """The one kind that browsing *does* write — they arrive by sync.

    Newest first, not most-reacted. Reactions are a stable ranking, so the same
    winners sat at the top every day and the tab exists to find something new;
    and because nothing prunes this table, `grid_limit` applied to a
    reaction-sorted set meant a fresh post could never enter the grid at all.
    """
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="older-but-louder",
                synced_for_page_id=page.id,
                reactions=9_000,
                published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="newer-but-quieter",
                synced_for_page_id=page.id,
                reactions=12,
                published_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
                text="…",
            ),
        ],
    )

    rows = client.get("/sources/competitors", params={"page_id": 1}).json()

    assert [row["external_id"] for row in rows] == [
        "newer-but-quieter",
        "older-but-louder",
    ]
    assert _count(engine, SourceKind.COMPETITOR_POST) == 2


def test_a_resync_refreshes_the_image_url_and_metrics_but_not_the_text(
    client, engine, monkeypatch
):
    """Facebook's CDN URLs are signed and expire in about four days.

    The competitor window is seven, so a URL frozen at first sync breaks while
    the post is still on screen. Metrics move with it. The text does not: it is
    what the operator chose, and a Draft's provenance must not drift.
    """

    def sync(image_url: str, reactions: int, text: str, **params):
        monkeypatch.setattr(
            routes.metricool,
            "fetch_competitor_posts",
            lambda page, **_: [
                SourceItemBase(
                    kind=SourceKind.COMPETITOR_POST,
                    external_id="same_post",
                    synced_for_page_id=page.id,
                    image_url=image_url,
                    reactions=reactions,
                    text=text,
                )
            ],
        )
        return client.get(
            "/sources/competitors", params={"page_id": 1, **params}
        ).json()

    # The first read syncs by itself — there is nothing stored yet.
    sync("https://cdn.example/a.jpg?oe=68000000", 10, "As posted")
    rows = sync(
        "https://cdn.example/a.jpg?oe=69999999", 4_200, "Edited upstream", refresh=True
    )

    assert len(rows) == 1, "a re-sync must not create a second row"
    assert rows[0]["image_url"] == "https://cdn.example/a.jpg?oe=69999999"
    assert rows[0]["reactions"] == 4_200
    assert rows[0]["text"] == "As posted"
    assert _count(engine) == 1


def test_a_plain_read_does_not_sync(client, monkeypatch):
    """5.5s and 1.6MB, for a window that gains ~3 posts an hour.

    The first read has nothing stored and syncs anyway, because a first-run
    operator should not have to discover that a button is what fills the grid.
    """
    calls: list[int] = []

    def counted(page, **_):
        calls.append(1)
        return [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="p1",
                synced_for_page_id=page.id,
                text="…",
            )
        ]

    monkeypatch.setattr(routes.metricool, "fetch_competitor_posts", counted)

    client.get("/sources/competitors", params={"page_id": 1})  # empty -> syncs
    client.get("/sources/competitors", params={"page_id": 1})  # stored -> does not
    client.get("/sources/competitors", params={"page_id": 1})
    assert len(calls) == 1

    client.get("/sources/competitors", params={"page_id": 1, "refresh": True})
    assert len(calls) == 2


def test_a_metricool_failure_is_502_not_an_empty_grid(client, monkeypatch):
    """An empty grid reads as "no competitor posted this week"."""

    def boom(page, **_):
        raise routes.metricool.MetricoolError("token expired")

    monkeypatch.setattr(routes.metricool, "fetch_competitor_posts", boom)

    response = client.get("/sources/competitors", params={"page_id": 1})

    assert response.status_code == 502
    assert "token expired" in response.json()["detail"]


def test_competitors_for_an_unknown_page_is_404(client):
    assert client.get("/sources/competitors", params={"page_id": 99}).status_code == 404


def test_a_competitor_post_already_written_from_is_flagged(
    client, engine, session, page, monkeypatch
):
    """Otherwise the grid keeps offering a post that has already been published.

    Derived per request rather than stored: a stored copy is a second truth, and
    when it drifts the operator writes the same story twice.
    """
    from app.models import Draft

    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="spent",
                synced_for_page_id=page.id,
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="fresh",
                synced_for_page_id=page.id,
                text="…",
            ),
        ],
    )
    client.get("/sources/competitors", params={"page_id": 1})

    spent = session.exec(
        select(SourceItem).where(SourceItem.external_id == "spent")
    ).one()
    session.add(Draft(page_id=1, source_item_id=spent.id))
    session.commit()

    rows = client.get("/sources/competitors", params={"page_id": 1}).json()
    used = {row["external_id"]: row["used"] for row in rows}

    assert used == {"spent": True, "fresh": False}


def test_sources_config_reads_the_file_rather_than_a_copy_of_it(client):
    """Settings shows what a run is configured with, so it reads it back."""
    body = client.get("/sources/config", params={"page_id": 1}).json()

    assert [feed["name"] for feed in body["feeds"]] == [
        feed.name for feed in sources_config.feeds_for("History Retraced")
    ]
    assert body["since_days"] == sources_config.rss.since_days
    assert body["max_items"] == sources_config.rss.max_items
    assert body["lookback_days"] == sources_config.competitors.lookback_days
    assert body["grid_limit"] == sources_config.competitors.grid_limit


def test_a_page_with_no_feeds_configured_is_loud(client, session):
    """An empty list would render as a tidy "no feeds" and look deliberate."""
    session.add(Page(name="Unconfigured", facebook_page_id="1", metricool_blog_id="2"))
    session.commit()
    unconfigured = session.exec(select(Page).where(Page.name == "Unconfigured")).one()

    response = client.get("/sources/config", params={"page_id": unconfigured.id})

    assert response.status_code == 500
    assert "No feeds configured for 'Unconfigured'" in response.json()["detail"]


def test_a_configured_competitor_that_published_nothing_is_visible_and_first(
    client, session, monkeypatch
):
    """The point of the list: silent and never-configured look identical
    everywhere else, which is how a competitor set rots unnoticed."""
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitors",
        lambda _page, **_: [
            {"provider_id": "1", "name": "Loud", "followers": 10},
            {"provider_id": "2", "name": "Silent", "followers": 9_000_000},
        ],
    )
    session.add(
        SourceItem(
            kind=SourceKind.COMPETITOR_POST,
            external_id="p1",
            author="Loud",
            synced_for_page_id=1,
            text="…",
        )
    )
    session.commit()

    rows = client.get("/sources/competitors/pages", params={"page_id": 1}).json()

    # Silent first, despite having 900,000x the followers — at the bottom of
    # twenty-six rows it would be as invisible as it is on every other screen.
    assert [(row["name"], row["posts_stored"]) for row in rows] == [
        ("Silent", 0),
        ("Loud", 1),
    ]


def test_the_competitor_list_failing_is_502_not_an_empty_set(client, monkeypatch):
    """It is somebody else's list. An empty one would read as "none configured"."""

    def boom(_page, **_):
        raise routes.metricool.MetricoolError("Metricool / failed (502)")

    monkeypatch.setattr(routes.metricool, "fetch_competitors", boom)

    response = client.get("/sources/competitors/pages", params={"page_id": 1})

    assert response.status_code == 502
    assert "Metricool" in response.json()["detail"]
