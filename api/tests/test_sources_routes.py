"""Browsing does not write.

Every route here reads. What used to be tested against `POST /sources` — the
curated-feed guard, dedup, and not rewriting an existing row — moved to
tests/test_generate.py when generate became the only write point.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, func, select

from app.models import (
    Draft,
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


WATCHED = "101151834965447"
"""A competitor providerId, ticked by `_assign` wherever a grid read is asserted."""


def _assign(session, page_id: int, *competitor_page_ids: str) -> None:
    """Tick these competitors for this Page.

    Every grid read goes through the tick list and only the tick list —
    `_visible_to` has no provenance fallback — so a fixture that writes posts
    without assigning their competitors builds a pool no Page can see. Writing
    the assignment is now part of arranging a competitor test, the same way
    writing the post is.
    """
    session.add_all(
        PageCompetitor(page_id=page_id, competitor_page_id=competitor)
        for competitor in competitor_page_ids
    )
    session.commit()


def _two_posts(monkeypatch, session, *, apart_days: int = 4):
    """One old-and-loud post, one new-and-quiet, `apart_days` apart.

    The pair the ordering tests need: whichever way the grid is sorted, the two
    answers are different, so an assertion cannot pass by accident.

    Both sit under one competitor, which is what these tests are about — the
    round-robin in the reactions sort ranks *within* a competitor before taking
    a second from any, so a pair split across two competitors would come back
    interleaved and test the interleaving rather than the order.
    """
    louder = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _assign(session, 1, WATCHED)
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="older-but-louder",
                synced_for_page_id=page.id,
                competitor_page_id=WATCHED,
                reactions=9_000,
                published_at=louder,
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="newer-but-quieter",
                synced_for_page_id=page.id,
                competitor_page_id=WATCHED,
                reactions=12,
                published_at=louder + timedelta(days=apart_days),
                text="…",
            ),
        ],
    )


def test_competitor_posts_are_written_on_arrival_and_ranked_by_reactions(
    client, engine, session, monkeypatch
):
    """The one kind that browsing *does* write — they arrive by sync.

    Reactions by default (client feedback G1, 2026-08-16). It is what
    Metricool's own Competitors tab shows and what `fetch_competitor_posts`
    already sorted by before this read discarded that order. Newest-first was
    surfacing the weakest posts: on the real pool the newest 60 topped out at
    2,031 reactions while the same week held one at 42,738.
    """
    _two_posts(monkeypatch, session)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert [row["external_id"] for row in rows] == [
        "older-but-louder",
        "newer-but-quieter",
    ]
    assert _count(engine, SourceKind.COMPETITOR_POST) == 2


def test_newest_is_still_available_and_really_reorders(client, session, monkeypatch):
    """Both orders, because the client asked to keep the old one beside the new."""
    _two_posts(monkeypatch, session)

    rows = client.get(
        "/sources/competitors", params={"page_ids": 1, "sort": "newest"}
    ).json()

    assert [row["external_id"] for row in rows] == [
        "newer-but-quieter",
        "older-but-louder",
    ]


def test_a_reactions_sort_cannot_be_frozen_by_an_old_viral_post(
    client, session, monkeypatch
):
    """The reason the old order existed, and the reason the window has to stay.

    Nothing prunes `source_item`, so ranking the whole table by reactions and
    taking `grid_limit` would pin the top of the grid to whatever went viral
    weeks ago — measured on History Retraced's real pool, 42 of the top 60
    unwindowed were already older than the window. A genuinely new post could
    never enter the grid again.

    Fifty days apart is well outside `lookback_days`, so the loud one is out of
    the window and must not be shown *despite* having 750x the reactions.
    """
    _two_posts(monkeypatch, session, apart_days=50)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert [row["external_id"] for row in rows] == ["newer-but-quieter"]
    assert "older-but-louder" not in [row["external_id"] for row in rows]

    # …and it is still reachable by asking for recency, which is unwindowed.
    everything = client.get(
        "/sources/competitors", params={"page_ids": 1, "sort": "newest"}
    ).json()
    assert len(everything) == 2, "the window hides a row from one order, not from the table"


def test_a_stale_pool_still_ranks_rather_than_answering_empty(client, session, monkeypatch):
    """The window is anchored to the newest post in scope, not to the clock.

    Subtracting the window from `now()` is the obvious version and it returns an
    **empty grid** for a Page nobody has synced this week — trading a stale
    ranking for no ranking at all. An unexplained empty grid is the failure this
    module already guards against twice elsewhere.

    Both fixtures here are dated 2026-08 and the suite runs long after that, so
    a clock-anchored window would return nothing.
    """
    _two_posts(monkeypatch, session)

    rows = client.get("/sources/competitors", params={"page_ids": 1}).json()

    assert rows, "a pool older than the window still has a best post"
    assert rows[0]["external_id"] == "older-but-louder"


def test_a_resync_refreshes_the_image_url_and_metrics_but_not_the_text(
    client, engine, session, monkeypatch
):
    """Facebook's CDN URLs are signed and expire in about four days.

    The competitor window is seven, so a URL frozen at first sync breaks while
    the post is still on screen. Metrics move with it. The text does not: it is
    what the operator chose, and a Draft's provenance must not drift.
    """

    _assign(session, 1, WATCHED)

    def sync(image_url: str, reactions: int, text: str, **params):
        monkeypatch.setattr(
            routes.metricool,
            "fetch_competitor_posts",
            lambda page, **_: [
                SourceItemBase(
                    kind=SourceKind.COMPETITOR_POST,
                    external_id="same_post",
                    synced_for_page_id=page.id,
                    competitor_page_id=WATCHED,
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


def test_a_sync_fetches_the_brand_that_hosts_what_this_page_reads(
    client, session, monkeypatch
):
    """Sync the brands that *feed* the scope, not the brands the scope *is*.

    `fetch_competitor_posts` is per-`blogId`, so a competitor's posts arrive only
    through the brand it sits under — and which brand that is was decided by
    where the 100-competitor allowance had room, not by who reads it. Measured
    2026-09-06 on Bodybuilding Tips N Tricks: seven assigned competitors, its own
    Metricool set empty, three of the seven hosted by Fitness Girls. Pressing
    Sync there asked for Bodybuilding's set, was told it has none, and left the
    grid 27 days stale with 241 current posts waiting under another brand.

    Page 1 here is Bodybuilding: it ticks a competitor whose only stored post
    arrived under Page 2, so a sync scoped to Page 1 must reach Page 2's brand.
    """
    other = Page(
        name="Hosts The Competitors",
        facebook_page_id="603815099479680",
        metricool_blog_id="6307776",
    )
    session.add(other)
    session.commit()
    session.refresh(other)

    # The one stored post is what records where this competitor is hosted.
    session.add(
        SourceItem(
            kind=SourceKind.COMPETITOR_POST,
            external_id="hosted-elsewhere",
            competitor_page_id=WATCHED,
            synced_for_page_id=other.id,
            published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            text="…",
        )
    )
    session.commit()
    _assign(session, 1, WATCHED)

    fetched_for: list[str] = []
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: fetched_for.append(page.name) or [],
    )

    client.get("/sources/competitors", params={"page_ids": 1, "refresh": True})

    assert other.name in fetched_for


def test_a_sync_leaves_brands_this_page_does_not_read_alone(
    client, session, monkeypatch
):
    """The other half: reaching the hosts is not an excuse to sync everything.

    A full-account sync is 1,677 posts and 31.4s across ten brands (measured
    2026-09-06), most of it for brands the Page in scope reads nothing from.
    Page 2 here hosts nothing Page 1 ticks, so it is not fetched.
    """
    other = Page(
        name="Unrelated Brand",
        facebook_page_id="603815099479680",
        metricool_blog_id="6307776",
    )
    session.add(other)
    session.commit()
    _assign(session, 1, WATCHED)

    fetched_for: list[str] = []
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: fetched_for.append(page.name) or [],
    )

    client.get("/sources/competitors", params={"page_ids": 1, "refresh": True})

    assert fetched_for == ["History Retraced"]


def test_an_empty_brand_set_does_not_resync_on_every_read(
    client, session, monkeypatch
):
    """The auto-sync asks "has a sync ever run", not "has this Page's set filled".

    Those came apart the moment a brand held no competitors of its own. The
    count used to be scoped to the Pages being read, and for such a Page it is
    zero permanently — so `stored == 0` held on *every* read and fired a vendor
    call that fetched nothing, every time. Six of ten brands were in that state
    when this was written.

    Page 2 here is one of them: nothing ever arrives under its own id. Once the
    pool has been filled by anything at all, reading it must stop syncing.
    """
    other = Page(
        name="Empty Metricool Set",
        facebook_page_id="603815099479680",
        metricool_blog_id="6307776",
    )
    session.add(other)
    session.commit()
    session.refresh(other)

    calls: list[str] = []

    def only_page_one(page, **_):
        calls.append(page.name)
        if page.id != 1:
            return []  # This brand's set is empty upstream.
        return [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="p1",
                synced_for_page_id=page.id,
                competitor_page_id=WATCHED,
                text="…",
            )
        ]

    monkeypatch.setattr(routes.metricool, "fetch_competitor_posts", only_page_one)

    client.get("/sources/competitors", params={"page_ids": 1})  # fills the pool
    calls.clear()

    client.get("/sources/competitors", params={"page_ids": other.id})
    client.get("/sources/competitors", params={"page_ids": other.id})
    assert calls == []  # its own set is empty, but the pool is not


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

    _assign(session, 1, WATCHED)
    monkeypatch.setattr(
        routes.metricool,
        "fetch_competitor_posts",
        lambda page, **_: [
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="spent",
                synced_for_page_id=page.id,
                competitor_page_id=WATCHED,
                text="…",
            ),
            SourceItemBase(
                kind=SourceKind.COMPETITOR_POST,
                external_id="fresh",
                synced_for_page_id=page.id,
                competitor_page_id=WATCHED,
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
    provenance only — it grants nothing — so each Page here is ticked for the
    competitor its own post came from, and the default scope is the union of
    every Page's tick list rather than a bypass of them.
    """
    other = Page(name="The Fact Feed", facebook_page_id="603815099479680",
                 metricool_blog_id="5600362")
    session.add(other)
    session.commit()
    session.refresh(other)

    watched_by_two = "104188601272158"
    _assign(session, 1, WATCHED)
    _assign(session, other.id, watched_by_two)

    session.add_all(
        [
            SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="a",
                       author="Watched By One", synced_for_page_id=1,
                       competitor_page_id=WATCHED,
                       published_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
            SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="b",
                       author="Watched By Two", synced_for_page_id=other.id,
                       competitor_page_id=watched_by_two,
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

    assert reach == {
        "assigned": 0,
        "own_set_posts": 0,
        "visible_posts": 0,
        "used_posts": 0,
    }


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

    assert reach == {
        "assigned": 1,
        "own_set_posts": 1,
        "visible_posts": 0,
        "used_posts": 0,
    }


def test_reach_counts_used_sources_the_grid_window_is_hiding(client, session):
    """The marker is right and almost never on screen.

    `_with_used` flags used sources across the rows the grid returns — 60, out of
    History Retraced's 808 visible. Measured 2026-08-17: Bodybuilding Tips N
    Tricks had 3 drafts generated from chosen posts and **zero** used markers in
    its grid; History Retraced, 31 against 2. Ticking a post, generating, and
    coming back to no marker anywhere reads as "it did not use it", which is the
    client's sentence almost word for word.

    Counted from this Page's drafts rather than from the visible pool. The first
    version intersected the two and answered **0** for Bodybuilding Tips N
    Tricks — the Page the complaint is about — because its three used sources are
    no longer visible to it. Distinct, because two drafts from one post is one
    used source, which is what the marker means.
    """
    _assign(session, 1, WATCHED)
    used, unused = (
        SourceItem(
            kind=SourceKind.COMPETITOR_POST,
            external_id=name,
            synced_for_page_id=1,
            competitor_page_id=WATCHED,
            published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        for name in ("already-written-from", "never-touched")
    )
    session.add_all([used, unused])
    session.commit()
    session.refresh(used)

    session.add_all(
        [
            Draft(page_id=1, source_item_id=used.id),
            Draft(page_id=1, source_item_id=used.id),
            Draft(page_id=1, topic="no source at all"),
        ]
    )
    session.commit()

    reach = client.get("/sources/competitors/reach", params={"page_ids": 1}).json()

    assert reach["visible_posts"] == 2
    assert reach["used_posts"] == 1, "two drafts from one post is one used source"

    # A source the Page can no longer see still counts, which is the whole point:
    # Bodybuilding Tips N Tricks generated three drafts from posts that have since
    # left its visible set, and a count intersected with the pool called that 0.
    invisible = SourceItem(
        kind=SourceKind.COMPETITOR_POST,
        external_id="out-of-this-pages-reach",
        synced_for_page_id=None,
    )
    session.add(invisible)
    session.commit()
    session.refresh(invisible)
    session.add(Draft(page_id=1, source_item_id=invisible.id))
    session.commit()

    reach = client.get("/sources/competitors/reach", params={"page_ids": 1}).json()

    assert reach["visible_posts"] == 2, "still not something the grid may show"
    assert reach["used_posts"] == 2, "but it was still generated from"
