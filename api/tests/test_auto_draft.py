"""Morning auto-drafts: `app.auto_draft` and `POST /generate/auto`.

What is asserted is the picking and the arithmetic - which post a morning takes
and how many. The writing itself is `test_generate.py`, so the route test stubs
`run_drafts` rather than letting a background task reach the writer.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app import auto_draft, generate
from app.models import (
    Draft,
    DraftStatus,
    Page,
    PageCompetitor,
    SourceItem,
    SourceKind,
)

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


# --- the top-up arithmetic ---------------------------------------------------


def test_an_empty_queue_fills_to_the_target(session, page, pool):
    ids = auto_draft.run(session, page, target=2)

    assert len(ids) == 2


def test_a_partly_full_queue_only_makes_up_the_difference(session, page, pool):
    _draft(session, page.id, DraftStatus.REVIEW)

    ids = auto_draft.run(session, page, target=2)

    assert len(ids) == 1


def test_a_full_queue_generates_nothing(session, page, pool):
    _draft(session, page.id, DraftStatus.REVIEW)
    _draft(session, page.id, DraftStatus.REVIEW)

    assert auto_draft.run(session, page, target=2) == []


def test_calling_it_twice_generates_nothing_the_second_time(session, page, pool):
    """The double-fire guard, and the reason this module needs no lock: the
    first run's rows are still `generating` when the second call counts."""
    first = auto_draft.run(session, page, target=2)

    assert len(first) == 2
    assert auto_draft.run(session, page, target=2) == []


def test_a_failed_draft_does_not_hold_a_place(session, page, pool):
    """Otherwise a Page stops generating precisely when something is broken."""
    _draft(session, page.id, DraftStatus.FAILED)
    _draft(session, page.id, DraftStatus.FAILED)

    assert len(auto_draft.run(session, page, target=2)) == 2


def test_a_rejected_draft_frees_its_place(session, page, pool):
    _draft(session, page.id, DraftStatus.REJECTED)

    assert len(auto_draft.run(session, page, target=1)) == 1


def test_nothing_unused_left_is_an_ordinary_morning(session, page):
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


def test_the_route_queues_the_drafts_it_created(client, session, page, pool, queued):
    response = client.post(
        "/generate/auto", json={"page_ids": [page.id], "target": 2}
    )

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


def test_a_full_queue_queues_no_background_work(client, session, page, pool, queued):
    _draft(session, page.id, DraftStatus.REVIEW)
    _draft(session, page.id, DraftStatus.REVIEW)

    response = client.post(
        "/generate/auto", json={"page_ids": [page.id], "target": 2}
    )

    assert response.status_code == 202
    assert response.json() == []
    assert queued == []
