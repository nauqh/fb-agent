"""The Phase 2 contract: browsing does not write, and ticking is idempotent."""

import pytest
from sqlmodel import Session, func, select

from app.models import SourceItem, SourceItemBase, SourceKind
from app.routes import sources as routes
from app.sources import rss


def _live(kind: SourceKind, external_id: str, **overrides) -> dict:
    """A Source Item as the client posts one — no id, no created_at."""
    item = SourceItemBase(
        kind=kind,
        external_id=external_id,
        author=overrides.pop("author", "Someone"),
        text=overrides.pop("text", "Body"),
        url=overrides.pop("url", None),
        **overrides,
    )
    return item.model_dump(mode="json")


def _count(engine, kind: SourceKind | None = None) -> int:
    with Session(engine) as session:
        query = select(func.count()).select_from(SourceItem)
        if kind is not None:
            query = query.where(SourceItem.kind == kind)
        return session.exec(query).one()


CURATED_RSS_URL = "https://www.smithsonianmag.com/history/a-story-180987410/"


@pytest.fixture
def cart() -> list[dict]:
    """One of each kind, which is what the phase is measured on."""
    return [
        _live(
            SourceKind.COMPETITOR_POST,
            "117997197937838_989827367419507",
            author="TerrifyingMyths",
            synced_for_page_id=1,
            reactions=16,
        ),
        _live(
            SourceKind.RSS,
            CURATED_RSS_URL,
            author="Smithsonian Magazine",
            url=CURATED_RSS_URL,
        ),
        _live(
            SourceKind.TWEET,
            "1817449230118928441",
            author="@qikipedia",
            url="https://x.com/qikipedia/status/1817449230118928441",
        ),
    ]


def test_ticking_one_of_each_kind_creates_three_rows(client, engine, cart):
    response = client.post("/sources", json=cart)
    assert response.status_code == 201

    rows = response.json()
    assert [row["kind"] for row in rows] == ["competitor_post", "rss", "tweet"]
    assert [row["author"] for row in rows] == [
        "TerrifyingMyths",
        "Smithsonian Magazine",
        "@qikipedia",
    ]
    # Only a competitor post belongs to a Page's competitor set.
    assert [row["synced_for_page_id"] for row in rows] == [1, None, None]
    assert _count(engine) == 3


def test_reticking_creates_none(client, engine, cart):
    first = client.post("/sources", json=cart).json()
    second = client.post("/sources", json=cart).json()

    assert [row["id"] for row in second] == [row["id"] for row in first]
    assert _count(engine) == 3


def test_the_same_item_twice_in_one_cart_is_one_row(client, engine, cart):
    """Two feeds carrying one story arrive as two ticks in a single POST.

    The unique constraint would not have surfaced this — nothing has flushed
    yet when the second copy is looked up.
    """
    rows = client.post("/sources", json=[cart[1], cart[1]]).json()

    assert rows[0]["id"] == rows[1]["id"]
    assert _count(engine) == 1


def test_an_rss_item_from_outside_the_curated_list_is_refused(client, engine, cart):
    """The RSS tab is live, so the client posts the body back.

    Without this the endpoint takes arbitrary text and hands it to the writer.
    """
    smuggled = _live(
        SourceKind.RSS,
        "https://evil.example/post",
        url="https://evil.example/post",
    )
    response = client.post("/sources", json=[smuggled])

    assert response.status_code == 422
    assert "curated" in response.json()["detail"]
    assert _count(engine) == 0


def test_an_item_with_no_external_id_is_refused(client, engine):
    response = client.post("/sources", json=[_live(SourceKind.TWEET, "")])

    assert response.status_code == 422
    assert _count(engine) == 0


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

    def sync(image_url: str, reactions: int, text: str):
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
        return client.get("/sources/competitors", params={"page_id": 1}).json()

    sync("https://cdn.example/a.jpg?oe=68000000", 10, "As posted")
    rows = sync("https://cdn.example/a.jpg?oe=69999999", 4_200, "Edited upstream")

    assert len(rows) == 1, "a re-sync must not create a second row"
    assert rows[0]["image_url"] == "https://cdn.example/a.jpg?oe=69999999"
    assert rows[0]["reactions"] == 4_200
    assert rows[0]["text"] == "As posted"
    assert _count(engine) == 1


def test_ticking_does_not_rewrite_an_existing_row(client, engine, cart):
    """`POST /sources` hands back a body it was shown, not a fresh vendor read."""
    first = client.post("/sources", json=cart).json()

    tampered = [{**item, "text": "rewritten", "reactions": 999} for item in cart]
    client.post("/sources", json=tampered)

    rows = client.get("/sources", params={"ids": first[0]["id"]}).json()
    assert rows[0]["text"] == "Body"


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
