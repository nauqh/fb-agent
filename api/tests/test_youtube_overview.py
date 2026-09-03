"""The youtube overview: brands, and the catalog split into windows.

The overview's fetch functions go to Metricool, so the route tests
monkeypatch `app.youtube.overview` where `test_publish.py` monkeypatches the
publisher — a stubbed call in, a window out. The fetch functions themselves
are driven through `httpx.MockTransport` to pin the request shape and the
error folding.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.settings import settings
from app.youtube import overview


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "metricool_api_token", "mc-token")
    monkeypatch.setattr(settings, "metricool_user_id", "user-1")


def _videos(now: datetime) -> list[dict]:
    """Three videos: two in the 30-day window, one in the previous."""
    def ms(dt: datetime) -> int:
        return int(dt.timestamp() * 1000)

    return [
        {
            "videoId": "early", "title": "Old one", "thumbnailUrl": "https://i.ytimg.com/vi/early/0.jpg",
            "publishedAt": ms(now - timedelta(days=45)),
            "views": 5.0, "likes": 0.0, "comments": 0.0, "shares": 0.0,
            "averageViewDuration": 10.0, "watchUrl": "https://www.youtube.com/watch?v=early",
        },
        {
            "videoId": "middle", "title": "Runner-up", "thumbnailUrl": "https://i.ytimg.com/vi/middle/0.jpg",
            "publishedAt": ms(now - timedelta(days=10)),
            "views": 50.0, "likes": 1.0, "comments": 0.0, "shares": 0.0,
            "averageViewDuration": 20.0, "watchUrl": "https://www.youtube.com/watch?v=middle",
        },
        {
            "videoId": "best", "title": "Most viewed", "thumbnailUrl": "https://i.ytimg.com/vi/best/0.jpg",
            "publishedAt": ms(now - timedelta(days=2)),
            "views": 300.0, "likes": 3.0, "comments": 1.0, "shares": 1.0,
            "averageViewDuration": 34.0, "watchUrl": "https://www.youtube.com/watch?v=best",
        },
    ]


def _configured(monkeypatch):
    monkeypatch.setattr(settings, "metricool_api_token", "mc-token")
    monkeypatch.setattr(settings, "metricool_user_id", "user-1")


def test_brands_keeps_only_youtube_profiles(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        overview,
        "youtube_brands",
        lambda: [
            overview.Brand(id="5600366", label="Bible Focus", channel_id="UC-a"),
            overview.Brand(id="6513629", label="BibleFocusIO", channel_id="UC-b"),
        ],
    )
    response = client.get("/youtube/brands")
    assert response.status_code == 200
    brands = response.json()["brands"]
    assert len(brands) == 2
    assert brands[0] == {
        "id": "5600366",
        "label": "Bible Focus",
        "channel_id": "UC-a",
    }


def test_overview_splits_windows_and_ranks_by_views(client: TestClient, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(overview, "youtube_videos", lambda brand_id: _videos(now))
    monkeypatch.setattr(
        "app.publish.metricool.list_scheduled", lambda *a, **k: []
    )

    response = client.get("/youtube/overview", params={"brand_id": "5600366", "days": 30})
    assert response.status_code == 200
    payload = response.json()

    # Views-descending, not whatever order the catalog arrived in.
    assert [v["video_id"] for v in payload["posts"]] == ["best", "middle"]
    assert payload["posts"][0]["views"] == 300
    assert payload["posts"][0]["kind"] is None  # no planner rows → no kind

    # The 45-day-old video is in `previous`, not `posts`.
    assert [v["video_id"] for v in payload["previous"]] == ["early"]
    assert payload["previous"][0]["published_at"] is not None


def test_overview_all_has_no_previous(client: TestClient, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(overview, "youtube_videos", lambda brand_id: _videos(now))
    monkeypatch.setattr(
        "app.publish.metricool.list_scheduled", lambda *a, **k: []
    )

    response = client.get("/youtube/overview", params={"brand_id": "5600366", "days": 0})
    payload = response.json()
    assert len(payload["posts"]) == 3
    assert payload["previous"] == []


def test_overview_kind_comes_from_the_planner(client: TestClient, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(overview, "youtube_videos", lambda brand_id: _videos(now))
    monkeypatch.setattr(
        "app.publish.metricool.list_scheduled",
        lambda *a, **k: [
            {
                "providers": [{"network": "youtube", "id": "best"}],
                "youtubeData": {"type": "short"},
            }
        ],
    )

    response = client.get("/youtube/overview", params={"brand_id": "5600366", "days": 30})
    by_id = {v["video_id"]: v for v in response.json()["posts"]}
    assert by_id["best"]["kind"] == "short"
    assert by_id["middle"]["kind"] is None


@pytest.mark.usefixtures("configured")
def test_youtube_videos_request_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("X-Mc-Auth")
        return httpx.Response(200, json=[{"videoId": "v1", "views": 1.0}])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = overview.youtube_videos("5600366", client=client)
    assert rows == [{"videoId": "v1", "views": 1.0}]
    assert captured["auth"] == "mc-token"
    assert "blogId=5600366" in captured["url"]


@pytest.mark.usefixtures("configured")
def test_youtube_videos_upstream_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(overview.OverviewError):
        overview.youtube_videos("5600366", client=client)