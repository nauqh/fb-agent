"""Auto-drafts: `app.auto_draft` and `POST /generate/auto`.

What is asserted is the picking and the arithmetic - which post a run takes
and how many. The writing itself is `test_generate.py`, so the route test stubs
`run_drafts` rather than letting a background task reach the writer.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import col, select

from app import auto_draft, generate
from app.models import (
    AutoDraftRun,
    Draft,
    DraftStatus,
    Page,
    PageCompetitor,
    SourceItem,
    SourceItemBase,
    SourceKind,
)
from app.sources import rss
from app.writer import agent as writer

LOUD = "101151834965447"
QUIET = "1225577819"

NEWEST = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
"""Every fixture post is dated from here. The window is anchored to the newest
post in scope, not to the clock, so the suite does not rot."""


def _assign(session, page_id: int, *competitor_page_ids: str) -> None:
    """Tick these competitors for this Page. `_visible_to` reads nothing else."""
    session.add_all(
        PageCompetitor(page_id=page_id, competitor_page_id=competitor)
        for competitor in competitor_page_ids
    )
    session.commit()


def _post(
    session,
    external_id: str,
    reactions: int,
    *,
    competitor: str = LOUD,
    days_old: int = 0,
) -> SourceItem:
    item = SourceItem(
        kind=SourceKind.COMPETITOR_POST,
        external_id=external_id,
        competitor_page_id=competitor,
        author=competitor,
        text=f"A competitor post with {reactions} reactions.",
        reactions=reactions,
        published_at=NEWEST - timedelta(days=days_old),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _draft(session, page_id: int, status: DraftStatus, source_item_id=None) -> Draft:
    draft = Draft(page_id=page_id, status=status, source_item_id=source_item_id)
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


@pytest.fixture
def pool(session, page):
    """Three posts under one competitor, loudest first. 500 > 200 > 50."""
    _assign(session, page.id, LOUD)
    return {
        "loudest": _post(session, "post-a", 500),
        "middle": _post(session, "post-b", 200, days_old=1),
        "quietest": _post(session, "post-c", 50, days_old=2),
    }


# --- the pick rule -----------------------------------------------------------


def test_picks_the_loudest_first(session, page, pool):
    picked = auto_draft.pick(session, page, 2)

    assert [item.external_id for item in picked] == ["post-a", "post-b"]


def test_a_post_any_draft_used_is_never_picked_again(session, page, pool):
    _draft(session, page.id, DraftStatus.APPROVED, pool["loudest"].id)

    picked = auto_draft.pick(session, page, 2)

    assert [item.external_id for item in picked] == ["post-b", "post-c"]


def test_a_post_used_by_another_page_is_still_spent(session, page, pool):
    """"Used" is global. Ten Pages share one competitor pool, so per-Page would
    draft the same story once for every Page that shares the competitor."""
    other = Page(name="The Fact Feed", facebook_page_id="999", metricool_blog_id="1")
    session.add(other)
    session.commit()
    _draft(session, other.id, DraftStatus.REVIEW, pool["loudest"].id)

    picked = auto_draft.pick(session, page, 1)

    assert [item.external_id for item in picked] == ["post-b"]


def test_a_post_outside_the_window_is_not_picked(session, page, pool):
    _post(session, "ancient", 100_000, days_old=30)

    picked = auto_draft.pick(session, page, 3)

    assert "ancient" not in [item.external_id for item in picked]


def test_a_page_with_no_competitors_assigned_picks_nothing(session, pool):
    """Three of the ten live Pages were in this state when this was written."""
    unassigned = Page(name="Hot Tub Timeout", facebook_page_id="888")
    session.add(unassigned)
    session.commit()

    assert auto_draft.pick(session, unassigned, 2) == []


def test_a_competitor_nobody_ticked_is_invisible(session, page, pool):
    _post(session, "unticked", 99_999, competitor=QUIET)

    picked = auto_draft.pick(session, page, 3)

    assert "unticked" not in [item.external_id for item in picked]


# --- how many a run makes ----------------------------------------------------


def test_a_run_makes_exactly_the_target(session, page, pool):
    ids = auto_draft.run(session, page, target=2)

    assert len(ids) == 2


def test_drafts_already_in_review_are_ignored(session, page, pool):
    """`review` is not a queue on these Pages. Measured 2026-09-21, the seven
    Pages with competitors assigned held 9 to 247 unreviewed drafts, the oldest
    41 days, so subtracting them would generate nothing ever again."""
    for _ in range(5):
        _draft(session, page.id, DraftStatus.REVIEW)

    assert len(auto_draft.run(session, page, target=2)) == 2


def test_a_second_run_makes_different_drafts_not_the_same_ones(session, page, pool):
    """Nothing stops two runs both generating. What they cannot do is generate
    the same post twice - that is `pick`, not a count of the queue."""
    first = auto_draft.run(session, page, target=2)
    second = auto_draft.run(session, page, target=1)

    assert len(first) == 2
    assert len(second) == 1

    rows = session.exec(select(Draft).where(col(Draft.id).in_(first + second))).all()
    sources = [row.source_item_id for row in rows]
    assert len(set(sources)) == 3


def test_a_run_takes_what_is_left_when_the_pool_runs_short(session, page, pool):
    auto_draft.run(session, page, target=2)

    assert len(auto_draft.run(session, page, target=5)) == 1


def test_nothing_unused_left_is_an_ordinary_run(session, page):
    _assign(session, page.id, LOUD)

    assert auto_draft.run(session, page, target=2) == []


def test_the_drafts_point_at_the_posts_they_came_from(session, page, pool):
    ids = auto_draft.run(session, page, target=2)

    drafts = session.exec(select(Draft).where(Draft.id.in_(ids))).all()
    assert sorted(draft.source_item_id for draft in drafts) == sorted(
        [pool["loudest"].id, pool["middle"].id]
    )


# --- the route ---------------------------------------------------------------


@pytest.fixture
def queued(monkeypatch):
    """Record what the route hands the writer, without running it."""
    seen: list[list[int]] = []
    monkeypatch.setattr(generate, "run_drafts", lambda ids: seen.append(ids))
    return seen


def _switch(session, page, competitors=None, rss=None, instructions=None):
    page.auto_draft_competitor_count = competitors
    page.auto_draft_rss_count = rss
    page.auto_draft_rss_instructions = instructions
    session.add(page)
    session.commit()


def test_the_route_queues_the_drafts_it_created(client, session, page, pool, queued):
    _switch(session, page, competitors=2)

    response = client.post("/generate/auto", json={"page_ids": [page.id]})

    assert response.status_code == 202
    assert len(response.json()) == 2
    assert queued == [response.json()]


def test_the_route_refuses_an_unknown_page(client, session, page, pool, queued):
    response = client.post("/generate/auto", json={"page_ids": [page.id, 4242]})

    assert response.status_code == 404
    assert "4242" in response.json()["detail"]
    # Nothing ran for the good Page either: every id is resolved first, so a
    # bad one cannot leave committed drafts with no writer queued behind them.
    assert queued == []
    assert session.exec(select(Draft)).all() == []


def test_the_route_needs_at_least_one_page(client, queued):
    assert client.post("/generate/auto", json={"page_ids": []}).status_code == 422


def test_an_exhausted_pool_queues_no_background_work(client, session, page, queued):
    _assign(session, page.id, LOUD)
    _switch(session, page, competitors=2)

    response = client.post("/generate/auto", json={"page_ids": [page.id]})

    assert response.status_code == 202
    assert response.json() == []
    assert queued == []


# --- the run record and the monitor ------------------------------------------


def test_a_run_that_made_nothing_is_still_recorded(session, page):
    """The whole reason the table exists: a night the cron did not fire and a
    night it found nothing look identical in the Draft table."""
    _assign(session, page.id, LOUD)

    auto_draft.run(session, page, target=2)

    runs = session.exec(select(AutoDraftRun)).all()
    assert len(runs) == 1
    assert runs[0].drafts_created == 0
    assert "No unused competitor posts" in (runs[0].note or "")


def test_a_short_pool_says_so_on_the_run(session, page, pool):
    auto_draft.run(session, page, target=2)

    run = auto_draft.run(session, page, target=5)

    assert len(run) == 1
    latest = session.exec(
        select(AutoDraftRun).order_by(col(AutoDraftRun.id).desc())
    ).first()
    assert latest is not None
    assert "asked for 5" in (latest.note or "")


def test_a_clean_run_records_no_note(session, page, pool):
    auto_draft.run(session, page, target=2)

    run = session.exec(select(AutoDraftRun)).one()
    assert run.drafts_created == 2
    assert run.note is None


def test_available_counts_what_is_left(session, page, pool):
    assert auto_draft.available(session, page) == 3

    auto_draft.run(session, page, target=2)

    assert auto_draft.available(session, page) == 1


def test_the_monitor_reports_every_page_not_the_selected_one(client, session, page, pool):
    other = Page(name="Hot Tub Timeout", facebook_page_id="888")
    session.add(other)
    session.commit()

    body = client.get("/auto-drafts/status").json()

    names = [row["page_name"] for row in body["pages"]]
    assert "Hot Tub Timeout" in names
    assert page.name in names


def test_the_monitor_separates_no_competitors_from_nothing_left(
    client, session, page, pool
):
    """Both are zero available, and they need different actions."""
    bare = Page(name="Hot Tub Timeout", facebook_page_id="888")
    session.add(bare)
    session.commit()
    auto_draft.run(session, page, target=5)  # drain the pool

    rows = {row["page_name"]: row for row in client.get("/auto-drafts/status").json()["pages"]}

    assert rows["Hot Tub Timeout"]["available"] == 0
    assert rows["Hot Tub Timeout"]["assigned_competitors"] == 0
    assert rows[page.name]["available"] == 0
    assert rows[page.name]["assigned_competitors"] == 1


def test_the_monitor_carries_each_page_s_logo(client, session, page, pool):
    """The table draws the Page's mark like Review does, so the fields have to
    survive the response model - they were added to it and a stale server went
    on serving a schema without them for two screenshots."""
    page.avatar_url = "https://static.metricool.com/logo.png"
    session.add(page)
    session.commit()

    rows = {row["page_name"]: row for row in client.get("/auto-drafts/status").json()["pages"]}

    assert rows[page.name]["avatar_url"] == "https://static.metricool.com/logo.png"
    assert "avatar_image_path" in rows[page.name]


def test_the_monitor_carries_each_page_s_last_run(client, session, page, pool):
    auto_draft.run(session, page, target=2)

    rows = {row["page_name"]: row for row in client.get("/auto-drafts/status").json()["pages"]}

    assert rows[page.name]["last_run_drafts"] == 2
    assert rows[page.name]["last_run_at"] is not None


def test_the_monitor_s_log_is_a_week_but_the_last_run_is_not(client, session, page, pool):
    """A Page quiet for longer than the log still shows when it last ran."""
    auto_draft.run(session, page, target=2)
    run = session.exec(select(AutoDraftRun)).one()
    run.created_at = run.created_at - timedelta(days=10)
    session.commit()

    body = client.get("/auto-drafts/status").json()
    row = next(row for row in body["pages"] if row["page_name"] == page.name)

    assert body["runs"] == []
    assert row["last_run_drafts"] == 2


def test_a_run_s_drafts_point_at_the_run(session, page, pool):
    ids = auto_draft.run(session, page, target=2)

    run = session.exec(select(AutoDraftRun)).one()
    drafts = session.exec(select(Draft).where(col(Draft.id).in_(ids))).all()
    assert {draft.auto_draft_run_id for draft in drafts} == {run.id}


def test_the_monitor_lists_each_run_s_drafts(client, session, page, pool):
    ids = auto_draft.run(session, page, target=2)
    session.add(Draft(page_id=page.id, topic="Asked for by hand"))
    session.commit()

    body = client.get("/auto-drafts/status").json()

    assert sorted(draft["id"] for draft in body["drafts"]) == sorted(ids)
    assert {draft["auto_draft_run_id"] for draft in body["drafts"]} == {body["runs"][0]["id"]}


# --- per-Page settings -------------------------------------------------------


def test_a_reaction_floor_skips_quieter_posts(session, page, pool):
    page.auto_draft_competitor_min_reactions = 100
    session.add(page)
    session.commit()

    picked = auto_draft.pick(session, page, 3)

    assert [item.external_id for item in picked] == ["post-a", "post-b"]
    assert auto_draft.available(session, page) == 2


def test_the_count_comes_from_the_page(client, session, page, pool, queued):
    """An older cron still sends `target`. It is ignored, not honoured."""
    _switch(session, page, competitors=1)

    response = client.post("/generate/auto", json={"page_ids": [page.id], "target": 3})

    assert len(response.json()) == 1


def test_no_page_ids_runs_every_page_switched_on(client, session, page, pool, queued):
    off = Page(name="Hot Tub Timeout", facebook_page_id="888")
    session.add(off)
    session.commit()
    _assign(session, off.id, LOUD)
    _switch(session, page, competitors=1)

    response = client.post("/generate/auto", json={})

    assert response.status_code == 202
    drafts = session.exec(select(Draft).where(col(Draft.id).in_(response.json()))).all()
    assert {draft.page_id for draft in drafts} == {page.id}
    assert {run.page_id for run in session.exec(select(AutoDraftRun)).all()} == {page.id}


def test_a_page_with_both_sources_off_writes_nothing(session, page, pool):
    assert auto_draft.run_page(session, page) == []
    assert session.exec(select(AutoDraftRun)).all() == []


# --- RSS ---------------------------------------------------------------------


def _feed_item(n: int, headline: str) -> SourceItemBase:
    return SourceItemBase(
        kind=SourceKind.RSS,
        external_id=f"https://www.smithsonianmag.com/history/story-{n}/",
        url=f"https://www.smithsonianmag.com/history/story-{n}/",
        author="Smithsonian Magazine",
        text=headline,
        published_at=NEWEST - timedelta(hours=n),
    )


@pytest.fixture
def feed(monkeypatch):
    """Three live items, newest first, as `fetch_rss` returns them."""
    items = [
        _feed_item(1, "Parliament votes on the budget"),
        _feed_item(2, "A football final"),
        _feed_item(3, "The election result"),
    ]
    monkeypatch.setattr(rss, "fetch_rss", lambda feeds: rss.RssFeed(items=list(items)))
    return items


def _answer(monkeypatch, picks):
    seen = []

    def fake_ask(prompt, output_type, instructions, *args, **kwargs):
        seen.append(prompt)
        return SimpleNamespace(output=output_type(picks=picks))

    monkeypatch.setattr(writer, "ask", fake_ask)
    return seen


def _sources(session, ids):
    drafts = session.exec(select(Draft).where(col(Draft.id).in_(ids))).all()
    return [session.get(SourceItem, draft.source_item_id).external_id for draft in drafts]


def test_rss_without_instructions_takes_the_newest(session, page, feed):
    _switch(session, page, rss=2)

    ids = auto_draft.run_page(session, page)

    assert sorted(_sources(session, ids)) == sorted([feed[0].external_id, feed[1].external_id])
    run = session.exec(select(AutoDraftRun)).one()
    assert run.source == SourceKind.RSS
    assert run.available == 1


def test_rss_instructions_decide_what_is_picked(session, page, feed, monkeypatch):
    seen = _answer(monkeypatch, [3, 1])
    _switch(session, page, rss=1, instructions="Politics only, no sport")

    ids = auto_draft.run_page(session, page)

    assert _sources(session, ids) == [feed[2].external_id]
    assert "Politics only, no sport" in seen[0]
    assert session.exec(select(AutoDraftRun)).one().available == 1


def test_a_model_number_off_the_list_is_dropped(session, page, feed, monkeypatch):
    _answer(monkeypatch, [9, 2, 2])
    _switch(session, page, rss=3, instructions="Sport")

    ids = auto_draft.run_page(session, page)

    assert _sources(session, ids) == [feed[1].external_id]
    assert "Only 1 item(s) fit" in session.exec(select(AutoDraftRun)).one().note


def test_rss_never_drafts_the_same_link_twice(session, page, feed):
    _switch(session, page, rss=2)

    first = auto_draft.run_page(session, page)
    second = auto_draft.run_page(session, page)

    assert set(_sources(session, first)).isdisjoint(_sources(session, second))
    assert len(second) == 1


def test_nothing_fitting_is_recorded_not_raised(session, page, feed, monkeypatch):
    _answer(monkeypatch, [])
    _switch(session, page, rss=2, instructions="Hot tubs")

    assert auto_draft.run_page(session, page) == []
    assert session.exec(select(AutoDraftRun)).one().note == "No unused feed items fit"


def test_a_model_failure_is_recorded_and_the_other_source_still_runs(
    session, page, pool, feed, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("503 from the model")

    monkeypatch.setattr(writer, "ask", boom)
    _switch(session, page, competitors=1, rss=1, instructions="Anything")

    ids = auto_draft.run_page(session, page)

    assert len(ids) == 1
    runs = {run.source: run for run in session.exec(select(AutoDraftRun)).all()}
    assert runs[SourceKind.COMPETITOR_POST].drafts_created == 1
    assert "503 from the model" in runs[SourceKind.RSS].note


def test_the_monitor_carries_both_switches(client, session, page, feed):
    _switch(session, page, competitors=2, rss=1)
    auto_draft.run_rss(session, page, 1)

    body = client.get("/auto-drafts/status").json()
    row = next(row for row in body["pages"] if row["page_name"] == page.name)

    assert row["competitor_count"] == 2
    assert row["rss_count"] == 1
    assert row["feeds"] == 2
    assert row["rss_available"] == 2
    assert body["runs"][0]["source"] == "rss"


FLAGS = {
    "none": (True, False, False),
    "source": (False, True, False),
    "google": (False, False, True),
    "generate": (False, False, False),
}


def _flags(session, draft_id):
    draft = session.get(Draft, draft_id)
    return (draft.no_image, draft.hero_from_source, draft.hero_search)


@pytest.mark.parametrize("choice", ["none", "google", "generate"])
def test_the_page_chooses_a_competitor_draft_s_picture(session, page, pool, choice):
    page.auto_draft_competitor_picture = choice
    [draft_id] = auto_draft.run(session, page, target=1)

    assert _flags(session, draft_id) == FLAGS[choice]


@pytest.mark.parametrize("choice", list(FLAGS))
def test_the_page_chooses_an_rss_draft_s_picture(session, page, feed, choice):
    page.auto_draft_rss_picture = choice
    [draft_id] = auto_draft.run_rss(session, page, 1)

    assert _flags(session, draft_id) == FLAGS[choice]


def test_each_source_takes_its_own_picture_choice(session, page, pool, feed):
    """Client, 2026-10-07: no picture for Facebook posts, the feed's for RSS."""
    page.auto_draft_competitor_picture = "none"
    page.auto_draft_rss_picture = "source"

    [competitor] = auto_draft.run(session, page, target=1)
    [from_feed] = auto_draft.run_rss(session, page, 1)

    assert _flags(session, competitor) == FLAGS["none"]
    assert _flags(session, from_feed) == FLAGS["source"]


def test_a_competitor_picture_cannot_be_the_source_s(client, page):
    response = client.patch(f"/pages/{page.id}", json={"auto_draft_competitor_picture": "source"})

    assert response.status_code == 422
