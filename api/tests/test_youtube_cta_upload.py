"""The CTA upload's signed flow: mint, verify, complete.

The old multipart upload died twice in production — first on Vercel's
serverless request-body ceiling (~4.5MB, not raiseable), then on the bucket
the row pointed at not existing. The replacement never carries bytes: the
browser PUTs the clip straight to Supabase with a token the API minted, and
the API's part is two small JSON calls, tested here against a
`httpx.MockTransport`-backed store exactly as `test_publish.py` does.
"""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import CtaTemplate
from app.settings import settings
from app.youtube import storage as ytstore


@pytest.fixture()
def supabase_store(monkeypatch):
    """The real store, on a MockTransport that answers the two calls the flow
    makes of Supabase: the sign, and the HEAD that `complete` uses to check
    the bytes landed. The sign answers with a url for whatever path was
    requested; only minted paths then HEAD as existing — which is also how
    `test_complete_refuses_bytes_that_never_landed` gets its ghost path.

    The settings are patched too, not just the transport: the URL the route
    builds comes from settings, and the suite must not lean on the laptop's
    `.env` having a particular project in it."""
    monkeypatch.setattr(settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key")
    minted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/sign/youtube-media/" in request.url.path:
            month, name = request.url.path.rsplit("/", 2)[-2:]
            minted.append(f"{month}/{name}")
            return httpx.Response(
                200,
                json={
                    "url": f"/object/upload/sign/youtube-media/{month}/{name}?token=test-token"
                },
            )
        if request.method == "HEAD" and request.url.path.endswith(
            tuple(f"/object/youtube-media/{m}" for m in minted)
        ):
            return httpx.Response(200)
        return httpx.Response(404, json={"error": "unexpected"})

    monkeypatch.setattr(
        ytstore,
        "store",
        ytstore.SupabaseYoutubeStore(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )


def _cta_count(session: Session) -> int:
    return len(session.exec(select(CtaTemplate)).all())


def test_upload_url_returns_path_and_browser_url(client: TestClient, supabase_store):
    response = client.post("/youtube/cta-templates/upload-url")
    assert response.status_code == 200
    payload = response.json()
    assert re.fullmatch(r"\d{4}-\d{2}/cta-[0-9a-f]{10}\.mp4", payload["path"])
    # The browser's URL is absolute and carries the token the sign minted.
    assert payload["upload_url"].startswith(
        "https://demo.supabase.co/storage/v1/object/upload/sign/"
    )
    assert "token=test-token" in payload["upload_url"]


def test_complete_creates_the_row(client: TestClient, supabase_store, session: Session):
    minted = client.post("/youtube/cta-templates/upload-url").json()["path"]

    response = client.post(
        "/youtube/cta-templates/complete",
        json={"path": minted, "title": "Follow us"},
    )
    assert response.status_code == 201
    row = response.json()
    assert row["title"] == "Follow us"
    assert row["cta_video_url"].endswith(minted)
    assert _cta_count(session) == 1


def test_complete_refuses_a_path_it_did_not_mint(client: TestClient, supabase_store):
    """Any bucket object, not just a fresh clip — including a processed video
    a worker is mid-concat on."""
    response = client.post(
        "/youtube/cta-templates/complete",
        json={"path": "2026-01/15_processed.mp4", "title": "sneaky"},
    )
    assert response.status_code == 422


def test_complete_refuses_bytes_that_never_landed(client: TestClient, supabase_store):
    response = client.post(
        "/youtube/cta-templates/complete",
        json={"path": "2026-09/cta-0000000000.mp4", "title": "ghost"},
    )
    assert response.status_code == 409
    assert "No clip" in response.json()["detail"]


def test_the_sign_call_is_a_post_with_the_service_key(monkeypatch):
    """Pin the wire shape the browser's flow depends on, since it was found by
    experiment against the live storage service, not from its docs."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"url": "/object/upload/sign/youtube-media/2026-09/cta-ab12cd34ef.mp4?token=test-token"},
        )

    store = ytstore.SupabaseYoutubeStore(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key")
    url = store.signed_upload_url("2026-09/cta-ab12cd34ef.mp4")

    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer service-key"
    assert url == (
        "https://demo.supabase.co/storage/v1"
        "/object/upload/sign/youtube-media/2026-09/cta-ab12cd34ef.mp4?token=test-token"
    )
