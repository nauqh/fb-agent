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
