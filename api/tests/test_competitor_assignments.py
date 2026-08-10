"""Which Competitors feed which Pages.

The rule these pin down is not obvious from either table: **assignment decides,
provenance is the fallback**, and the fallback ends per Page the moment that
Page has one assignment.

It exists because of a limit outside this codebase. Metricool allows 100
competitors per *account*, not per page, so five Pages that should each watch
the same twenty sources cannot each be given them. A competitor is added once,
under whichever Page has room, and assigned to every Page that should read it.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from app.models import Page, PageCompetitor, SourceItem, SourceKind
from app.routes import sources as routes


@pytest.fixture(autouse=True)
def never_call_metricool(monkeypatch):
    """The empty-pool auto-sync is a real vendor call, and these tests trip it.

    Found the hard way: one of them reached live Metricool and came back with
    500 production posts. Every other test file stubs this per test; here it is
    autouse, because the sync fires from a read rather than from anything the
    test asks for.
    """
    monkeypatch.setattr(routes.metricool, "fetch_competitor_posts", lambda page, **_: [])

WATCHED = "101151834965447"
OTHER = "104188601272158"


def _post(external_id: str, competitor: str, page_id: int, day: int) -> SourceItem:
    return SourceItem(
        kind=SourceKind.COMPETITOR_POST,
        external_id=external_id,
        competitor_page_id=competitor,
        synced_for_page_id=page_id,
        author=f"Competitor {competitor}",
        published_at=datetime(2026, 8, day, tzinfo=timezone.utc),
        text="…",
    )


def _two_pages(session) -> Page:
    other = Page(
        name="The Fact Feed",
        facebook_page_id="603815099479680",
        metricool_blog_id="5600362",
    )
    session.add(other)
    session.commit()
    session.refresh(other)
    return other


def test_without_assignments_a_page_sees_the_set_it_owns_in_metricool(
    client, session, page
):
    """The fallback. Every Page is in this state before anything is assigned.

    Without it, adding the column would blank every grid in the app until
    someone had ticked their way through Settings.
    """
    other = _two_pages(session)
    session.add_all([_post("a", WATCHED, page.id, 1), _post("b", OTHER, other.id, 2)])
    session.commit()

    mine = client.get("/sources/competitors", params={"page_ids": page.id}).json()
    assert {row["external_id"] for row in mine} == {"a"}


def test_an_assignment_lets_a_page_read_another_pages_competitor(client, session, page):
    """The whole point. The competitor is configured under the *other* Page in
    Metricool — because that is where the allowance had room — and this Page
    reads it anyway."""
    other = _two_pages(session)
    session.add(_post("b", OTHER, other.id, 2))
    session.add(PageCompetitor(page_id=page.id, competitor_page_id=OTHER))
    session.commit()

    mine = client.get("/sources/competitors", params={"page_ids": page.id}).json()
    assert {row["external_id"] for row in mine} == {"b"}


def test_one_assignment_ends_the_fallback_for_that_page(client, session, page):
    """Abrupt by design.

    A Page showing its Metricool set *plus* its assignments is a grid nobody can
    predict — the operator assigns one competitor and cannot tell which of the
    twenty on screen is there because they chose it.
    """
    other = _two_pages(session)
    session.add_all([_post("a", WATCHED, page.id, 1), _post("b", OTHER, other.id, 2)])
    session.commit()

    # Assign only the other Page's competitor: "a" was visible by provenance and
    # stops being.
    client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={"competitor_page_ids": [OTHER]},
    )

    mine = client.get("/sources/competitors", params={"page_ids": page.id}).json()
    assert {row["external_id"] for row in mine} == {"b"}


def test_removing_the_last_assignment_restores_the_fallback(client, session, page):
    """Not an error state — it is the state every Page starts in."""
    session.add(_post("a", WATCHED, page.id, 1))
    session.add(PageCompetitor(page_id=page.id, competitor_page_id=OTHER))
    session.commit()

    assert client.get("/sources/competitors", params={"page_ids": page.id}).json() == []

    client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={"competitor_page_ids": []},
    )

    mine = client.get("/sources/competitors", params={"page_ids": page.id}).json()
    assert {row["external_id"] for row in mine} == {"a"}


def test_assignments_are_replaced_wholesale_not_merged(client, session, page):
    """A checkbox list is a set, so the request carries the set.

    Two clicks racing end at the state the second described, rather than at
    whichever order the deltas arrived in.
    """
    client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={"competitor_page_ids": [WATCHED, OTHER]},
    )
    body = client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={"competitor_page_ids": [OTHER]},
    ).json()

    assert [row["competitor_page_id"] for row in body] == [OTHER]
    assert session.exec(select(PageCompetitor)).all() != []


def test_the_same_competitor_can_feed_two_pages(client, session, page):
    """The case Metricool's ceiling makes impossible on their side."""
    other = _two_pages(session)
    session.add(_post("b", OTHER, other.id, 2))
    session.commit()

    for target in (page.id, other.id):
        client.put(
            "/competitors/assignments",
            params={"page_id": target},
            json={"competitor_page_ids": [OTHER]},
        )

    for target in (page.id, other.id):
        rows = client.get("/sources/competitors", params={"page_ids": target}).json()
        assert {row["external_id"] for row in rows} == {"b"}, target


def test_assignments_for_an_unknown_page_are_404(client):
    assert client.get("/competitors/assignments", params={"page_id": 99}).status_code == 404
    assert (
        client.put(
            "/competitors/assignments",
            params={"page_id": 99},
            json={"competitor_page_ids": []},
        ).status_code
        == 404
    )


def test_a_note_records_why_and_survives_a_retick(client, page):
    """The table has no history, so the reasoning lives on the row.

    Keeping this mapping in a config file was considered for exactly that — a
    commit message saying why a Page reads a competitor — and rejected because
    it would put the change behind a deploy. This is the compensation, and it is
    worthless if the next save wipes it: a screen that submits the tick list
    without the notes must not erase them.
    """
    client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={
            "competitor_page_ids": [WATCHED],
            "notes": {WATCHED: "Same politics beat, posts twice a day."},
        },
    )

    # A later save carrying only the ticks — which is what a checkbox list sends.
    body = client.put(
        "/competitors/assignments",
        params={"page_id": page.id},
        json={"competitor_page_ids": [WATCHED, OTHER]},
    ).json()

    kept = next(row for row in body if row["competitor_page_id"] == WATCHED)
    assert kept["note"] == "Same politics beat, posts twice a day."
    added = next(row for row in body if row["competitor_page_id"] == OTHER)
    assert added["note"] is None
