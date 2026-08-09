"""The store, against a mock transport rather than a bucket.

`SupabaseMediaStore` takes an `httpx.Client`, so the transport is the seam and
these drive the real request building and the real retry loop.

What is pinned here is what the move off local disk actually changed: a write
can now fail, and the difference between a failure worth retrying and one that
is an answer. The rest — the URL shape, the content type — is pinned because
getting it wrong produces a file that uploads fine and is unreadable later.
"""

import httpx
import pytest

from app import media
from app.settings import settings


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key")
    monkeypatch.setattr(settings, "supabase_bucket", "fb-agent-media")
    # The retry is the thing under test, not the wait. Three attempts at the
    # real backoff would put 1.5s into the suite for every failure case.
    monkeypatch.setattr(media, "BACKOFF_SECONDS", 0)


def _store(handler, bucket=None) -> media.SupabaseMediaStore:
    return media.SupabaseMediaStore(
        bucket, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_saving_returns_a_bucket_relative_path_not_a_url():
    """The row stores this. A URL here welds every row to one project."""
    seen: dict = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = request.content
        return httpx.Response(200, json={"Key": "x"})

    stored = _store(handler).save(b"pixels", "12-hero-20260809T101500-a3f9c1.png")

    assert stored.endswith("/12-hero-20260809T101500-a3f9c1.png")
    assert not stored.startswith("http")
    month, _, name = stored.partition("/")
    assert len(month) == 7 and month[4] == "-", f"{month!r} is not yyyy-mm"
    assert seen["url"] == (
        "https://demo.supabase.co/storage/v1/object/fb-agent-media/" + stored
    )
    assert seen["body"] == b"pixels"


def test_a_save_overwrites_its_own_name_rather_than_failing():
    """`x-upsert`: re-running a migration must not 409 on what it already wrote."""
    seen: dict = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx.Response(200, json={})

    _store(handler).save(b"pixels", "12-hero-x.png")

    assert seen["headers"]["x-upsert"] == "true"
    assert seen["headers"]["authorization"] == "Bearer service-key"


@pytest.mark.parametrize(
    "name, expected",
    [("a.png", "image/png"), ("a.jpg", "image/jpeg"), ("a.jpeg", "image/jpeg")],
)
def test_the_content_type_follows_the_extension(name, expected):
    """Supabase serves back what it was told. A wrong label breaks the fetcher."""
    seen: dict = {}

    def handler(request):
        seen["type"] = request.headers["content-type"]
        return httpx.Response(200, json={})

    _store(handler).save(b"pixels", name)

    assert seen["type"] == expected


def test_a_file_the_bucket_would_not_take_is_refused_before_the_request():
    """The bucket's mime whitelist would answer too, but not until it mattered."""
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    with pytest.raises(media.MediaError, match="not a kind of file"):
        _store(handler).save(b"pixels", "12-composed.gif")

    assert not called, "nothing was uploaded"


def test_reading_returns_the_bytes():
    store = _store(lambda request: httpx.Response(200, content=b"pixels"))

    assert store.read("2026-08/12-hero.png") == b"pixels"


def test_deleting_something_already_gone_is_not_an_error():
    """`delete_draft` runs over three columns that may never have been filled."""
    store = _store(lambda request: httpx.Response(404, json={"error": "not_found"}))

    store.delete("2026-08/12-hero.png")  # no raise


def test_a_missing_file_on_read_is_loud():
    """The caller is about to composite with these bytes."""
    store = _store(lambda request: httpx.Response(404, json={"error": "not_found"}))

    with pytest.raises(media.MediaError, match="404"):
        store.read("2026-08/12-hero.png")


def test_a_dropped_connection_is_tried_again():
    """The hero above this call was paid for; the inset cannot be remade at all."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(200, json={})

    _store(handler).save(b"pixels", "12-hero.png")

    assert attempts["n"] == 3


def test_a_refusal_is_not_retried():
    """403 means the key is wrong. Asking twice more only delays the error."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(403, text="invalid signature")

    with pytest.raises(media.MediaError, match="403"):
        _store(handler).save(b"pixels", "12-hero.png")

    assert attempts["n"] == 1


def test_supabase_being_down_is_retried_and_then_raised():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(503, text="upstream unavailable")

    with pytest.raises(media.MediaError, match="after 3 attempts"):
        _store(handler).save(b"pixels", "12-hero.png")

    assert attempts["n"] == media.ATTEMPTS


def test_an_unconfigured_store_says_so_before_it_tries():
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    settings.supabase_url = ""
    try:
        with pytest.raises(media.MediaError, match="SUPABASE_URL"):
            _store(handler).save(b"pixels", "12-hero.png")
    finally:
        settings.supabase_url = "https://demo.supabase.co"

    assert not called


def test_dev_and_production_write_to_different_buckets():
    """Separate databases hand out the same draft ids. One bucket would collide."""
    seen: dict = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    _store(handler, bucket="fb-agent-media-dev").save(b"pixels", "12-hero.png")

    assert "/object/fb-agent-media-dev/" in seen["url"]


def test_the_public_url_carries_no_signature_and_no_expiry():
    """Facebook fetches this when the post goes out, which may be days later."""
    url = media.public_url("2026-08/12-composed-a3f9c1.jpg")

    assert url == (
        "https://demo.supabase.co/storage/v1/object/public/fb-agent-media/"
        "2026-08/12-composed-a3f9c1.jpg"
    )
    assert "token" not in url and "?" not in url


def test_two_composites_in_the_same_second_get_different_names():
    """Overwriting one would change a picture a row already pointed at."""
    first = media.filename(12, "composed", "jpg")
    second = media.filename(12, "composed", "jpg")

    assert first != second
    assert first.startswith("12-composed-") and first.endswith(".jpg")
