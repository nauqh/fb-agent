"""Browsing does not write.

Every route here reads. What used to be tested against `POST /sources` — the
curated-feed guard, dedup, and not rewriting an existing row — moved to
tests/test_generate.py when generate became the only write point.
"""

from sqlmodel import Session, func, select

from app.models import SourceItem, SourceItemBase, SourceKind
from app.routes import sources as routes
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


def test_competitor_posts_are_written_on_arrival_and_sorted_by_reactions(
    client, engine, monkeypatch
):
    """The one kind that browsing *does* write — they arrive by sync."""
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="quiet",
                synced_for_page_id=page.id,
                reactions=12,
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="loud",
                synced_for_page_id=page.id,
                reactions=9_000,
                text="…",
            ),
        ],
    )

    rows = client.get("/sources/competitors", params={"page_id": 1}).json()

    assert [row["external_id"] for row in rows] == ["loud", "quiet"]
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
