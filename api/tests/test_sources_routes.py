"""Browsing does not write.

Every route here reads. What used to be tested against `POST /sources` — the
curated-feed guard, dedup, and not rewriting an existing row — moved to
tests/test_generate.py when generate became the only write point.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, func, select

from app.models import (
    Feed,
    Page,
    PageCompetitor,
    SourceItem,
    SourceItemBase,
    SourceKind,
)
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


def _two_posts(monkeypatch, *, apart_days: int = 4):
    """One old-and-loud post, one new-and-quiet, `apart_days` apart.

    The pair the ordering tests need: whichever way the grid is sorted, the two
    answers are different, so an assertion cannot pass by accident.
    """
    louder = datetime(2026, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="older-but-louder",
                synced_for_page_id=page.id,
                reactions=9_000,
                published_at=louder,
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="newer-but-quieter",
                synced_for_page_id=page.id,
                reactions=12,
                published_at=louder + timedelta(days=apart_days),
                text="…",
            ),
        ],
    )


def test_competitor_posts_are_written_on_arrival_and_ranked_by_reactions(
    client, engine, monkeypatch
):
    """The one kind that browsing *does* write — they arrive by sync.

    Reactions by default (client feedback G1, 2026-08-16). It is what
    Metricool's own Competitors tab shows and what `fetch_competitor_posts`
    already sorted by before this read discarded that order. Newest-first was
    surfacing the weakest posts: on the real pool the newest 60 topped out at
    2,031 reactions while the same week held one at 42,738.
    """
    _two_posts(monkeypatch)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert [row["external_id"] for row in rows] == [
        "older-but-louder",
        "newer-but-quieter",
    ]
    assert _count(engine, SourceKind.COMPETITOR_POST) == 2


def test_newest_is_still_available_and_really_reorders(client, monkeypatch):
    """Both orders, because the client asked to keep the old one beside the new."""
    _two_posts(monkeypatch)

    rows = client.get(
        "/sources/competitors", params={"page_ids": 1, "sort": "newest"}
    ).json()

    assert [row["external_id"] for row in rows] == [
        "newer-but-quieter",
        "older-but-louder",
    ]


def test_a_reactions_sort_cannot_be_frozen_by_an_old_viral_post(client, monkeypatch):
    """The reason the old order existed, and the reason the window has to stay.

    Nothing prunes `source_item`, so ranking the whole table by reactions and
    taking `grid_limit` would pin the top of the grid to whatever went viral
    weeks ago — measured on History Retraced's real pool, 42 of the top 60
    unwindowed were already older than the window. A genuinely new post could
    never enter the grid again.

    Fifty days apart is well outside `lookback_days`, so the loud one is out of
    the window and must not be shown *despite* having 750x the reactions.
    """
    _two_posts(monkeypatch, apart_days=50)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert [row["external_id"] for row in rows] == ["newer-but-quieter"]
    assert "older-but-louder" not in [row["external_id"] for row in rows]

    # …and it is still reachable by asking for recency, which is unwindowed.
    everything = client.get(
        "/sources/competitors", params={"page_ids": 1, "sort": "newest"}
    ).json()
    assert len(everything) == 2, "the window hides a row from one order, not from the table"


def test_a_stale_pool_still_ranks_rather_than_answering_empty(client, monkeypatch):
    """The window is anchored to the newest post in scope, not to the clock.

    Subtracting the window from `now()` is the obvious version and it returns an
    **empty grid** for a Page nobody has synced this week — trading a stale
    ranking for no ranking at all. An unexplained empty grid is the failure this
    module already guards against twice elsewhere.

    Both fixtures here are dated 2026-08 and the suite runs long after that, so
    a clock-anchored window would return nothing.
    """
    _two_posts(monkeypatch)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert rows, "a pool older than the window still has a best post"
    assert rows[0]["external_id"] == "older-but-louder"


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
            "/sources/competitors", params={"page_ids": 1, **params}
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

    client.get("/sources/competitors", params={"page_ids": 1})  # empty -> syncs
    client.get("/sources/competitors", params={"page_ids": 1})  # stored -> does not
    client.get("/sources/competitors", params={"page_ids": 1})
    assert len(calls) == 1

    client.get("/sources/competitors", params={"page_ids": 1, "refresh": True})
    assert len(calls) == 2


def test_a_metricool_failure_is_502_not_an_empty_grid(client, monkeypatch):
    """An empty grid reads as "no competitor posted this week"."""

    def boom(page, **_):
        raise routes.metricool.MetricoolError("token expired")

    monkeypatch.setattr(routes.metricool, "fetch_competitor_posts", boom)

    response = client.get("/sources/competitors", params={"page_ids": 1})

    assert response.status_code == 502
    assert "token expired" in response.json()["detail"]


def test_competitors_for_an_unknown_page_is_404(client):
    assert client.get("/sources/competitors", params={"page_ids": 99}).status_code == 404


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
    client.get("/sources/competitors", params={"page_ids": 1})

    spent = session.exec(
        select(SourceItem).where(SourceItem.external_id == "spent")
    ).one()
    session.add(Draft(page_id=1, source_item_id=spent.id))
    session.commit()

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()
    used = {row["external_id"]: row["used"] for row in rows}

    assert used == {"spent": True, "fresh": False}


def test_sources_config_reads_the_source_rather_than_a_copy_of_it(client, session):
    """Settings shows what a run is configured with, so it reads it back.

    Two sources now, not one: the windows are still `config/sources.yml`, the
    feeds are rows. Both are read here rather than described again on the
    client, which is the point — a screen whose job is to show the
    configuration must not show a hand-kept copy that can disagree with it.
    """
    body = client.get("/sources/config", params={"page_id": 1}).json()

    assert [feed["name"] for feed in body["feeds"]] == [
        feed.name
        for feed in session.exec(select(Feed).order_by(Feed.name)).all()
    ]
    assert body["since_days"] == sources_config.rss.since_days
    assert body["max_items"] == sources_config.rss.max_items
    assert body["lookback_days"] == sources_config.competitors.lookback_days
    assert body["grid_limit"] == sources_config.competitors.grid_limit


def test_a_page_with_no_feeds_reads_as_empty_not_broken(client, session):
    """A new Page has no feeds by definition, and must still be usable.

    This asserted a 500 until Pages became something you add rather than seed.
    The 500 made a new Page's Settings screen unreachable — including the form
    that adds its first feed — so the empty state has to be legible instead:
    the screen says "no feeds yet" and offers the form.

    The rule it replaced was protecting against silence, and that protection
    moved rather than vanished: a feed that *fails* is still surfaced, per
    `RssFeedOut.failures`.
    """
    session.add(Page(name="Brand New", facebook_page_id="1", metricool_blog_id="2"))
    session.commit()
    fresh = session.exec(select(Page).where(Page.name == "Brand New")).one()

    body = client.get("/sources/config", params={"page_id": fresh.id})

    assert body.status_code == 200
    assert body.json()["feeds"] == []

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

    rows = client.get("/sources/competitors/pages", params={"page_ids": 1}).json()

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

    response = client.get("/sources/competitors/pages", params={"page_ids": 1})

    assert response.status_code == 502
    assert "Metricool" in response.json()["detail"]


def test_the_competitor_pool_spans_every_page_by_default(client, session, monkeypatch):
    """Omitting `page_ids` returns every Page's competitor posts, not one Page's.

    This is the whole of the shared pool. Metricool caps an account at 100
    competitors *in total*, so five Pages that should each watch the same twenty
    sources cannot each be given them — the twenty are added once, under
    whichever Page, and read by all of them.

    `synced_for_page_id` still records which set a post arrived through. It is
    provenance now, not ownership.
    """
    other = Page(name="The Fact Feed", facebook_page_id="603815099479680",
                 metricool_blog_id="5600362")
    session.add(other)
    session.commit()
    session.refresh(other)

    session.add_all(
        [
            SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="a",
                       author="Watched By One", synced_for_page_id=1,
                       published_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
            SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="b",
                       author="Watched By Two", synced_for_page_id=other.id,
                       published_at=datetime(2026, 8, 2, tzinfo=timezone.utc)),
        ]
    )
    session.commit()

    both = client.get("/sources/competitors").json()
    assert {row["external_id"] for row in both} == {"a", "b"}

    # And narrowing still works, for looking at one set specifically.
    narrowed = client.get("/sources/competitors", params={"page_ids": other.id}).json()
    assert {row["external_id"] for row in narrowed} == {"b"}


def test_a_draft_can_name_the_source_it_came_from(client, session):
    """One stored Source Item by id, which is how a Draft says where it came from.

    Client feedback G2 (2026-08-16): "I have no idea which source or which
    competitor posts the tool gens content from." `Draft.source_item_id` was
    already on the wire on 35 of 38 drafts — there was simply no route that
    turned the id into a name, so no screen could render one.
    """
    item = SourceItem(
        kind=SourceKind.COMPETITOR_POST,
        external_id="the-one-it-came-from",
        author="Historic Vids",
        text="In 1889 a Kansas farmer traded his last mule for a broken windmill.",
        url="https://www.facebook.com/1225577819_10160418822",
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    body = client.get(f"/sources/items/{item.id}").json()

    assert body["author"] == "Historic Vids"
    assert body["kind"] == "competitor_post"
    # The link is the point: naming the competitor without a way back to the post
    # answers half the question.
    assert body["url"] == "https://www.facebook.com/1225577819_10160418822"


def test_an_unknown_source_item_says_so(client):
    """404, not an empty body.

    The drawer renders this row as provenance. A 200 with nothing in it would
    draw an empty box that looks exactly like a source with no author.
    """
    assert client.get("/sources/items/424242").status_code == 404


def test_a_page_nothing_reaches_says_so_rather_than_showing_an_empty_grid(
    client, session
):
    """The grid's three empty states are one blank screen without this.

    Client feedback G2 (2026-08-16), sent about two Pages that have zero
    competitors configured in Metricool: six of the ten do. The grid renders an
    empty div for all of them, so "nobody is configured" is indistinguishable
    from "quiet week" — and the operator's next move is different.
    """
    other = Page(
        name="Bodybuilding Tips N Tricks",
        facebook_page_id="100064861479386",
        metricool_blog_id="5600363",
    )
    session.add(other)
    session.commit()
    session.refresh(other)

    reach = client.get(
        "/sources/competitors/reach", params={"page_ids": other.id}
    ).json()

    assert reach == {"assigned": 0, "own_set_posts": 0, "visible_posts": 0}


def test_an_assigned_page_with_a_quiet_week_is_a_different_empty(client, session):
    """Assignments exist, posts do not. Pressing Sync is the right move here.

    The state above it is the one where Sync cannot help, and telling them apart
    is the whole reason this reads `assigned` from the local table instead of
    asking Metricool who is configured.
    """
    session.add(PageCompetitor(page_id=1, competitor_page_id="1225577819", name="Historic Vids"))
    session.commit()

    reach = client.get("/sources/competitors/reach", params={"page_ids": 1}).json()

    assert reach["assigned"] == 1
    assert reach["visible_posts"] == 0


def test_reach_shows_a_pool_hidden_by_its_own_assignment(client, session):
    """The empty state that looks like a quiet week and is not.

    Measured on Bible Focus, 2026-08-17: one assignment, zero visible posts, and
    **430 posts sitting in its own Metricool set**. A Page reads its own set only
    until its first assignment lands — after that it reads exactly what is
    ticked, and one assignment to a competitor that never posts hides everything.

    Both numbers are reported because the screen needs both to say that: `0
    visible` alone is indistinguishable from having nothing at all.
    """
    session.add(
        PageCompetitor(page_id=1, competitor_page_id="silent-one", name="Publishes Nothing")
    )
    session.add(
        SourceItem(
            kind=SourceKind.COMPETITOR_POST,
            external_id="in-the-set-but-unassigned",
            competitor_page_id="1225577819",
            synced_for_page_id=1,
            published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()

    reach = client.get("/sources/competitors/reach", params={"page_ids": 1}).json()

    assert reach == {"assigned": 1, "own_set_posts": 1, "visible_posts": 0}
