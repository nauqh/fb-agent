"""Metricool's planner, read live. There is no local schedule table (ADR-0001).

No network: `list_scheduled` takes an `httpx.Client`, so the transport is the
seam and the real request-building runs under a `MockTransport`.
"""

import httpx
import pytest

from app.models import Draft, DraftStatus
from app.publish import metricool as publisher
from app.settings import settings


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "metricool_api_token", "mc-token")
    monkeypatch.setattr(settings, "metricool_user_id", "user-1")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


PLANNER_ROW = {
    "id": 356030804,
    "publicationDate": {"dateTime": "2026-08-01T00:08:00", "timezone": "Asia/Ho_Chi_Minh"},
    "text": "The recap.",
    "firstCommentText": "The body.",
    "media": ["https://old.example/media/open?path=x"],
    "draft": False,
    "providers": [
        {
            "network": "facebook",
            "status": "PUBLISHED",
            "publicUrl": "https://facebook.com/1",
        }
    ],
}


def test_the_planner_window_goes_out_as_naive_local_times():
    """`20260801` answers 400 — the format is spelled out in the error."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": [PLANNER_ROW]})

    from datetime import datetime

    publisher.list_scheduled(
        "4605385",
        datetime(2026, 8, 1, 0, 0, 0),
        datetime(2026, 8, 31, 23, 59, 59),
        client=_client(handler),
    )

    assert "start=2026-08-01T00%3A00%3A00" in seen["url"]
    assert "end=2026-08-31T23%3A59%3A59" in seen["url"]


def test_the_schedule_flattens_a_planner_row(client, monkeypatch):
    monkeypatch.setattr(publisher, "list_scheduled", lambda *a, **k: [PLANNER_ROW])

    [post] = client.get("/schedule").json()

    assert post["id"] == "356030804"
    assert post["published_at"] == "2026-08-01T00:08:00", "local, never re-anchored to UTC"
    assert post["status"] == "PUBLISHED"
    assert post["public_url"] == "https://facebook.com/1"
    assert post["image_url"] == "https://old.example/media/open?path=x"
    assert post["draft_id"] is None, "the old system queued this one"


def test_our_own_posts_are_marked_as_ours(client, session, page, monkeypatch):
    """The cutover needs to tell fb-agent's posts from the old system's."""
    monkeypatch.setattr(publisher, "list_scheduled", lambda *a, **k: [PLANNER_ROW])
    session.add(
        Draft(page_id=page.id, status=DraftStatus.APPROVED, metricool_post_id="356030804")
    )
    session.commit()

    [post] = client.get("/schedule").json()

    assert post["draft_id"] == 1


def test_a_planner_draft_reports_as_a_draft_not_as_blank(client, monkeypatch):
    """A draft has no provider status, and blank reads as broken."""
    row = {**PLANNER_ROW, "draft": True, "providers": [{"network": "facebook"}]}
    monkeypatch.setattr(publisher, "list_scheduled", lambda *a, **k: [row])

    [post] = client.get("/schedule").json()

    assert post["status"] == "DRAFT"
    assert post["is_draft"] is True


def test_metricool_being_down_is_a_502_not_an_empty_schedule(client, monkeypatch):
    """An empty calendar would read as "nothing scheduled", which is a lie."""

    def refuse(*_a, **_k):
        raise publisher.PublishError("Metricool did not answer the planner: ReadTimeout")

    monkeypatch.setattr(publisher, "list_scheduled", refuse)

    response = client.get("/schedule")

    assert response.status_code == 502
    assert "did not answer" in response.json()["detail"]


# --- the next available slot --------------------------------------------------
#
# The Page's configured times, minus whatever the planner already holds. There
# is no local schedule state involved and there must not be (ADR-0001): a post
# somebody scheduled by hand in Metricool's own UI has to count exactly as much
# as one of ours, and only the planner knows about it.


def _slots(client, *times):
    for hour, minute in times:
        response = client.post("/pages/1/slots", json={"hour": hour, "minute": minute})
        assert response.status_code == 201, response.text


def _at(client, monkeypatch, *stamps):
    """Make the planner report posts at these naive local times."""
    rows = [
        {**PLANNER_ROW, "publicationDate": {"dateTime": s, "timezone": "Asia/Ho_Chi_Minh"}}
        for s in stamps
    ]
    monkeypatch.setattr(publisher, "list_scheduled", lambda *a, **k: rows)


def _next(client):
    response = client.get("/schedule/next-slot?page_id=1")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_next_slot_is_the_first_configured_time_still_free(
    client, page, monkeypatch
):
    _slots(client, (8, 0), (13, 30), (19, 0))
    _at(client, monkeypatch)  # nothing queued

    answer = _next(client)

    assert answer["label"] in {"08:00", "13:30", "19:00"}
    assert answer["taken"] == 0
    # Naive local, no offset suffix — the shape publish takes and the planner
    # stores. An offset here is rejected by Metricool.
    assert "+" not in answer["when"] and answer["when"].count(":") == 2


def test_a_slot_the_planner_already_has_a_post_at_is_skipped(
    client, page, monkeypatch
):
    """Including a post nobody here created — the planner is the only authority."""
    _slots(client, (8, 0), (19, 0))
    # Stubbed *before* the first read: without this the call leaves the building
    # and answers 401 from the real Metricool.
    _at(client, monkeypatch)
    first = _next(client)

    _at(client, monkeypatch, first["when"])
    second = _next(client)

    assert second["when"] != first["when"]
    assert second["taken"] >= 1, "the occupied slot was not reported as skipped"


def test_a_post_a_second_off_the_slot_still_occupies_it(client, page, monkeypatch):
    """A post moved by hand lands seconds off. Matching to the minute is what
    stops the same slot being offered forever."""
    _slots(client, (8, 0), (19, 0))
    _at(client, monkeypatch)
    first = _next(client)

    # Same minute, 42 seconds in — `YYYY-MM-DDTHH:MM:` is 17 characters.
    _at(client, monkeypatch, first["when"][:17] + "42")

    assert _next(client)["when"] != first["when"]


def test_a_page_with_no_slots_says_so_rather_than_guessing(client, page, monkeypatch):
    _at(client, monkeypatch)

    response = client.get("/schedule/next-slot?page_id=1")

    assert response.status_code == 409
    assert "no publishing times" in response.json()["detail"]


def test_slots_come_back_earliest_first(client, page):
    _slots(client, (19, 0), (8, 0), (13, 30))

    labels = [s["label"] for s in client.get("/pages/1/slots").json()]

    assert labels == ["08:00", "13:30", "19:00"]


def test_the_same_time_twice_is_refused(client, page):
    _slots(client, (8, 0))

    assert client.post("/pages/1/slots", json={"hour": 8, "minute": 0}).status_code == 409


def test_an_impossible_time_is_refused(client, page):
    assert client.post("/pages/1/slots", json={"hour": 24, "minute": 0}).status_code == 422
    assert client.post("/pages/1/slots", json={"hour": 8, "minute": 60}).status_code == 422


def test_removing_a_slot_leaves_the_others(client, page):
    _slots(client, (8, 0), (19, 0))
    slots = client.get("/pages/1/slots").json()

    assert client.delete(f"/pages/1/slots/{slots[0]['id']}").status_code == 204
    assert [s["label"] for s in client.get("/pages/1/slots").json()] == ["19:00"]


def test_the_schedule_window_is_on_the_pages_clock_not_the_servers(
    client, page, monkeypatch
):
    """`list_scheduled` sends naive local times and tells Metricool they are
    `Asia/Ho_Chi_Minh`, so a bare `datetime.now()` labels the *server's* wall
    clock as Vietnamese and shifts the window by the offset — 7h on Railway
    (UTC), 3h on the operator's laptop (Melbourne). Posts near either edge go
    missing, silently.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    seen = {}

    def capture(blog_id, start, end, client=None):
        seen["start"], seen["end"] = start, end
        return []

    monkeypatch.setattr(publisher, "list_scheduled", capture)
    client.get("/schedule?page_id=1&days_back=0&days_ahead=1")

    expected = datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    drift = abs((seen["start"] - expected).total_seconds())
    assert drift < 120, (
        f"the window starts {drift / 3600:.1f}h from the Page's clock — it is on "
        "the server's"
    )
