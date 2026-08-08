"""Getting a Draft out: upload the picture, hand Metricool the words.

No network. Both modules take an `httpx.Client`, so the transport is the seam —
these tests drive the real request-building and response-handling code with a
`MockTransport` underneath, rather than stubbing the functions under test.

The rules being pinned are the ones that cost something to relearn: the image
goes up before the post is scheduled, a `publicationDate` carries no offset, and
`Accept` stays off the normalize GET.
"""

import io
import json

import httpx
import pytest
from PIL import Image

from app.models import Draft, DraftStatus
from app.publish import metricool as publisher
from app.publish import storage
from app.settings import settings


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key")
    monkeypatch.setattr(settings, "supabase_bucket", "fb-agent-media")
    monkeypatch.setattr(settings, "metricool_api_token", "mc-token")
    monkeypatch.setattr(settings, "metricool_user_id", "user-1")
    monkeypatch.setattr(settings, "metricool_publish_as_draft", True)


def _png(size=(896, 1120)) -> bytes:
    """Noise, not a flat fill.

    A single-colour PNG compresses to a few KB and JPEG cannot beat it, so a
    flat image makes the "JPEG is smaller" assertion fail on a picture that is
    nothing like a photograph. Noise is closer to a hero.
    """
    from random import Random

    noise = Random(7)
    image = Image.new("RGB", size)
    image.putdata(
        [
            (noise.randrange(256), noise.randrange(256), noise.randrange(256))
            for _ in range(size[0] * size[1])
        ]
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- the upload ---------------------------------------------------------------


def test_the_composite_goes_up_as_jpeg_not_png():
    """4.5× smaller for the same picture, and the only reader is Facebook."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["type"] = request.headers.get("content-type")
        seen["upsert"] = request.headers.get("x-upsert")
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"Key": "fb-agent-media/12.jpg"})

    png = _png()
    url = storage.upload(png, "12.jpg", client=_client(handler))

    assert Image.open(io.BytesIO(seen["body"])).format == "JPEG"
    assert len(seen["body"]) < len(png), "the whole point of converting"
    assert seen["type"] == "image/jpeg"
    assert seen["upsert"] == "true", "re-publishing must overwrite, not accumulate"
    assert seen["auth"] == "Bearer service-key"
    assert url == "https://demo.supabase.co/storage/v1/object/public/fb-agent-media/12.jpg"


def test_the_public_url_is_unsigned():
    """A signed URL expires, and Facebook fetches this when the post is due."""
    assert "token=" not in storage.public_url("12.jpg")
    assert "/object/public/" in storage.public_url("12.jpg")


def test_transparency_is_flattened_onto_white_not_black():
    """`convert("RGB")` alone composites onto black and says nothing about it."""
    buffer = io.BytesIO()
    Image.new("RGBA", (40, 40), (255, 255, 255, 0)).save(buffer, format="PNG")

    flattened = Image.open(io.BytesIO(storage.as_jpeg(buffer.getvalue())))

    assert flattened.getpixel((20, 20)) > (200, 200, 200)


def test_an_upload_that_is_refused_says_so_loudly():
    def handler(_request):
        return httpx.Response(403, text="new row violates row-level security policy")

    with pytest.raises(storage.StorageError, match="403"):
        storage.upload(_png(), "12.jpg", client=_client(handler))


def test_publishing_without_supabase_configured_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")

    with pytest.raises(storage.StorageError, match="SUPABASE_URL"):
        storage.upload(_png(), "12.jpg")


# --- the schedule -------------------------------------------------------------


def test_normalize_is_called_without_an_accept_header():
    """With one, the endpoint answers 500 "No acceptable representation"."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("accept")
        seen["url"] = str(request.url)
        return httpx.Response(200, text="https://demo.supabase.co/x/12.jpg")

    publisher.normalize_image(
        "https://demo.supabase.co/x/12.jpg", "4605385", client=_client(handler)
    )

    assert seen["accept"] in (None, "*/*"), "an explicit JSON Accept 500s here"
    assert "userToken=mc-token" in seen["url"], "the scheduler API wants it in the query"
    assert "blogId=4605385" in seen["url"]


def test_a_normalize_that_returns_no_url_is_an_error():
    def handler(_request):
        return httpx.Response(200, text="")

    with pytest.raises(publisher.PublishError, match="no usable image URL"):
        publisher.normalize_image("https://x/1.jpg", "4605385", client=_client(handler))


def test_the_publication_date_carries_no_offset():
    """Metricool takes the timezone as its own field and rejects a suffix."""
    stamp = publisher.publication_date()

    assert "+" not in stamp and "Z" not in stamp
    assert len(stamp) == len("2026-08-08T12:00:00")


def test_a_time_in_the_past_is_pushed_far_enough_ahead():
    from datetime import datetime, timedelta, timezone

    stamp = publisher.publication_date(datetime.now(timezone.utc) - timedelta(days=1))
    soon = publisher.publication_date()

    assert stamp == soon, "Metricool rejects a date in the past"


def test_the_body_says_metricool_owns_publishing():
    body = publisher.build_body("caption #tag", "the long body", "https://x/12.jpg")

    assert body["autoPublish"] is True, "otherwise nothing ever reaches the page"
    assert body["firstCommentText"] == "the long body", "Metricool posts this, not us"
    assert body["providers"] == [
        {"network": "facebook", "facebookData": {"type": "POST"}}
    ]
    assert body["media"] == ["https://x/12.jpg"], "a list — the id form needs an id"


def test_the_draft_flag_is_what_keeps_a_test_off_the_page(monkeypatch):
    assert publisher.build_body("t", None, "https://x/1.jpg")["draft"] is True

    monkeypatch.setattr(settings, "metricool_publish_as_draft", False)
    assert publisher.build_body("t", None, "https://x/1.jpg")["draft"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "8891"},
        {"data": {"id": "8891"}},
        {"data": [{"id": "8891"}]},
        {"result": {"post": {"postId": 8891}}},
    ],
)
def test_the_post_id_is_found_wherever_metricool_nests_it(payload):
    def handler(_request):
        return httpx.Response(200, json=payload)

    got = publisher.schedule(
        "4605385", "text", None, "https://x/1.jpg", client=_client(handler)
    )

    assert got == "8891"


def test_a_response_with_no_id_is_not_a_failure():
    """The post is in the planner either way; Metricool just did not name it."""

    def handler(_request):
        return httpx.Response(200, json={"status": "ok"})

    assert (
        publisher.schedule(
            "4605385", "text", None, "https://x/1.jpg", client=_client(handler)
        )
        is None
    )


def test_a_refused_schedule_reports_what_metricool_said():
    def handler(_request):
        return httpx.Response(400, text='{"detail":"publicationDate is in the past"}')

    with pytest.raises(publisher.PublishError, match="publicationDate"):
        publisher.schedule(
            "4605385", "text", None, "https://x/1.jpg", client=_client(handler)
        )


# --- the route ----------------------------------------------------------------


@pytest.fixture
def published(monkeypatch):
    """Both hops recorded, neither performed."""
    calls: dict = {"order": []}

    def upload(png, name, client=None):
        calls["order"].append("upload")
        calls["name"] = name
        return f"https://demo.supabase.co/storage/v1/object/public/b/{name}"

    def normalize(url, blog_id, client=None):
        calls["order"].append("normalize")
        return url

    def schedule(blog_id, text, first_comment, image_url, when=None, client=None):
        calls["order"].append("schedule")
        calls.update(
            blog_id=blog_id, text=text, first_comment=first_comment, image=image_url
        )
        return "8891"

    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(publisher, "normalize_image", normalize)
    monkeypatch.setattr(publisher, "schedule", schedule)
    return calls


@pytest.fixture
def ready(session, page):
    """A reviewable Draft with a composite on disk."""
    from app import media

    draft = Draft(
        page_id=page.id,
        status=DraftStatus.APPROVED,
        hook="On the image.",
        caption="🌊 The recap.",
        first_comment="The body." * 40,
        hashtags=["#history", "#historyretraced"],
        composed_image_path=media.store.save(_png(), "12-composed.png"),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def test_publishing_uploads_before_it_schedules(client, ready, published):
    """A post scheduled against a URL that does not resolve yet goes out broken."""
    response = client.post(f"/drafts/{ready.id}/publish")

    assert response.status_code == 200
    assert published["order"] == ["upload", "normalize", "schedule"]
    assert response.json()["metricool_post_id"] == "8891"


def test_the_caption_and_hashtags_are_the_post_the_hook_is_not(client, ready, published):
    """The hook is drawn on the image; repeating it prints it twice on one post."""
    client.post(f"/drafts/{ready.id}/publish")

    assert "🌊 The recap." in published["text"]
    assert "#history #historyretraced" in published["text"]
    assert "On the image." not in published["text"]
    assert published["first_comment"].startswith("The body."), "Metricool posts this"


def test_publishing_twice_is_refused(client, ready, published):
    client.post(f"/drafts/{ready.id}/publish")

    again = client.post(f"/drafts/{ready.id}/publish")

    assert again.status_code == 409
    assert "already in Metricool" in again.json()["detail"]
    assert published["order"].count("schedule") == 1, "no duplicate post"


def test_a_draft_with_no_image_cannot_be_published(client, session, page, published):
    draft = Draft(page_id=page.id, status=DraftStatus.APPROVED, hook="x", caption="y")
    session.add(draft)
    session.commit()

    response = client.post(f"/drafts/{draft.id}/publish")

    assert response.status_code == 409
    assert published["order"] == [], "nothing was uploaded"


def test_a_failed_draft_cannot_be_published(client, session, page, ready, published):
    ready.status = DraftStatus.FAILED
    session.add(ready)
    session.commit()

    assert client.post(f"/drafts/{ready.id}/publish").status_code == 409


def test_an_upstream_failure_leaves_the_draft_publishable(client, ready, monkeypatch):
    """502, and no id written: the draft is untouched and can go again."""

    def refuse(*_a, **_k):
        raise storage.StorageError("Supabase refused the upload (403)")

    monkeypatch.setattr(storage, "upload", refuse)

    response = client.post(f"/drafts/{ready.id}/publish")

    assert response.status_code == 502
    assert "403" in response.json()["detail"]
    assert client.get(f"/drafts/{ready.id}").json()["metricool_post_id"] is None


def test_a_page_with_no_blog_id_cannot_publish(client, session, page, ready, published):
    page.metricool_blog_id = None
    session.add(page)
    session.commit()

    response = client.post(f"/drafts/{ready.id}/publish")

    assert response.status_code == 409
    assert "metricool_blog_id" in response.json()["detail"]
    assert published["order"] == []
