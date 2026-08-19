"""Getting a Draft out: hand Metricool the words and a link to the picture.

No network. `metricool` takes an `httpx.Client`, so the transport is the seam —
these tests drive the real request-building and response-handling code with a
`MockTransport` underneath, rather than stubbing the functions under test.

The rules being pinned are the ones that cost something to relearn: a
`publicationDate` carries no offset, `Accept` stays off the normalize GET, and
a published draft is frozen — which is what allows the post to point at the
live composite instead of a copy made for the purpose.

Storing the picture is `test_media.py`. Nothing is uploaded here any more.
"""

import io
import json

import httpx
import pytest
from PIL import Image

from app.models import Draft, DraftStatus
from app.publish import metricool as publisher
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


def _jpeg() -> bytes:
    """What a composite is now. Named separately so the fixture is not a lie.

    A PNG stored under a `.jpg` name is the exact mismatch `media._content_type`
    exists to catch, and the local fake does not catch it — so a fixture that
    took the shortcut would pass here and be wrong about production.
    """
    buffer = io.BytesIO()
    Image.open(io.BytesIO(_png())).save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


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

    def normalize(url, blog_id, client=None):
        calls["order"].append("normalize")
        calls["normalized"] = url
        return url

    def schedule(blog_id, text, first_comment, image_url, when=None, client=None):
        calls["order"].append("schedule")
        calls.update(
            blog_id=blog_id,
            text=text,
            first_comment=first_comment,
            image=image_url,
            when=when,
        )
        return "8891"

    monkeypatch.setattr(publisher, "normalize_image", normalize)
    monkeypatch.setattr(publisher, "schedule", schedule)
    return calls


@pytest.fixture
def ready(session, page):
    """A reviewable Draft with a composite stored."""
    from app import media

    draft = Draft(
        page_id=page.id,
        status=DraftStatus.APPROVED,
        hook="On the image.",
        caption="🌊 The recap.",
        first_comment="The body." * 40,
        # Left set deliberately. Hashtags were removed on 2026-08-12 (feedback
        # E1, reversed) *without* clearing the column, so a draft written before
        # the removal still carries them. Pinned by the test below.
        hashtags=["#history", "#historyretraced"],
        composed_image_path=media.store.save(_jpeg(), "12-composed.jpg"),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def test_publishing_schedules_against_the_composite_itself(client, ready, published):
    """No copy. The freeze is what makes the live composite a permanent link."""
    from app import media

    response = client.post(f"/drafts/{ready.id}/publish")

    assert response.status_code == 200
    assert published["order"] == ["normalize", "schedule"], "nothing was uploaded"
    assert published["normalized"] == media.public_url(ready.composed_image_path)
    assert response.json()["metricool_post_id"] == "8891"


def test_a_chosen_time_reaches_the_scheduler_naive(client, ready, published):
    """The drawer's "Publish at" is the whole of this app's scheduling.

    It arrives as a naive stamp and must stay naive all the way down —
    `publication_date` attaches `settings.timezone` itself, and an offset
    suffix is what Metricool rejects. A `datetime-local` input cannot produce
    one, so the guard is that nothing in between adds it.
    """
    from datetime import datetime

    response = client.post(
        f"/drafts/{ready.id}/publish", json={"when": "2026-08-14T18:00"}
    )

    assert response.status_code == 200
    assert published["when"] == datetime(2026, 8, 14, 18, 0)
    assert published["when"].tzinfo is None


def test_no_time_means_as_soon_as_metricool_will_take_it(client, ready, published):
    """Omitting it is not "some default hour" — it is `None`, and the sender
    turns that into now plus `MIN_MINUTES_AHEAD`."""
    client.post(f"/drafts/{ready.id}/publish")

    assert published["when"] is None


def test_the_link_metricool_gets_is_the_one_the_browser_showed(client, ready, published):
    """One file, one URL. A second copy is a second thing that can go stale."""
    client.post(f"/drafts/{ready.id}/publish")

    assert published["image"] == client.get(f"/drafts/{ready.id}").json()[
        "composed_image_url"
    ]


def test_the_caption_is_the_post_the_hook_and_old_hashtags_are_not(
    client, ready, published
):
    """The hook is drawn on the image; repeating it prints it twice on one post.

    Hashtags were removed on 2026-08-12 (feedback E1, reversed by the client).
    The column was kept, so 20 of 21 drafts still hold tags — `ready` is one of
    them. They must not reach Facebook: a removal that still publishes tags for
    every draft written before it is not a removal, and the operator asked for
    the stored values to be left alone rather than for the feature to linger.
    """
    client.post(f"/drafts/{ready.id}/publish")

    assert "🌊 The recap." in published["text"]
    assert "#history" not in published["text"], "a stored tag was published"
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
    assert published["order"] == [], "nothing reached Metricool"


def test_a_failed_draft_cannot_be_published(client, session, page, ready, published):
    ready.status = DraftStatus.FAILED
    session.add(ready)
    session.commit()

    assert client.post(f"/drafts/{ready.id}/publish").status_code == 409


def test_an_upstream_failure_leaves_the_draft_publishable(client, ready, monkeypatch):
    """502, and no id written: the draft is untouched and can go again."""

    def refuse(*_a, **_k):
        raise publisher.PublishError("Metricool refused the image (403)")

    monkeypatch.setattr(publisher, "normalize_image", refuse)

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


# A scheduled draft cannot be **redrawn**. ADR-0001 gave the reason — the
# planner owns a scheduled post — but the rule went unenforced until the
# composite became the thing Metricool links to. Facebook fetches that link when
# the post is due, so any edit that redraws, and any delete, would pull the
# picture out from under a post that has not gone out yet.
#
# It used to freeze the whole row, and that was too much: the client could fix a
# typo in the old tool without opening the planner, and D6 (2026-08-14) is that
# capability going missing. The text is now editable and pushed to Metricool;
# only the picture is held.


@pytest.mark.parametrize(
    "method, path, kwargs",
    [
        ("patch", "", {"json": {"hook": "Drawn on the image."}}),
        ("post", "/image", {}),
        ("post", "/image?new_hero=true", {}),
        ("delete", "/inset", {}),
    ],
    ids=["drawn-field", "rebuild", "new-hero", "remove-inset"],
)
def test_a_scheduled_draft_cannot_be_redrawn(
    client, ready, published, method, path, kwargs
):
    client.post(f"/drafts/{ready.id}/publish")

    response = getattr(client, method)(f"/drafts/{ready.id}{path}", **kwargs)

    assert response.status_code == 409
    assert "Metricool" in response.json()["detail"]


def test_a_refused_redraw_changes_nothing(client, ready, published):
    """The 409 is the point, but a half-applied edit would be worse than the 409."""
    client.post(f"/drafts/{ready.id}/publish")
    before = client.get(f"/drafts/{ready.id}").json()

    client.patch(f"/drafts/{ready.id}", json={"hook": "Edited after publishing."})

    assert client.get(f"/drafts/{ready.id}").json() == before


def test_a_published_draft_cannot_be_deleted(client, ready, published):
    """Deleting the row takes the composite, and Metricool still holds its link."""
    from app import media

    client.post(f"/drafts/{ready.id}/publish")

    response = client.delete(f"/drafts/{ready.id}")

    assert response.status_code == 409
    assert client.get(f"/drafts/{ready.id}").status_code == 200
    assert media.store.path(ready.composed_image_path).exists(), "picture survives"


def test_the_screen_can_ask_whether_publish_reaches_an_audience(client, monkeypatch):
    """Rehearsal mode was invisible, and seven real posts paid for it.

    `METRICOOL_PUBLISH_AS_DRAFT` differs between environments on purpose — false
    on Railway, true on a laptop — and until this endpoint existed no screen
    could tell which it was talking to. Both said "Handed to Metricool".
    """
    monkeypatch.setattr(settings, "metricool_publish_as_draft", True)
    assert client.get("/publish/mode").json() == {"rehearsal": True}

    monkeypatch.setattr(settings, "metricool_publish_as_draft", False)
    assert client.get("/publish/mode").json() == {"rehearsal": False}


def test_publish_mode_is_read_per_request_not_captured_at_import(client, monkeypatch):
    """The value a deploy is running under, not the one this process booted with.

    Reading it into a module constant would answer correctly in every test that
    never changed it, and be wrong for exactly the environment this exists to
    describe.
    """
    monkeypatch.setattr(settings, "metricool_publish_as_draft", False)
    first = client.get("/publish/mode").json()["rehearsal"]

    monkeypatch.setattr(settings, "metricool_publish_as_draft", True)
    second = client.get("/publish/mode").json()["rehearsal"]

    assert (first, second) == (False, True)


# --- editing and cancelling a scheduled post (D6) ------------------------------
#
# Measured against the live planner on 2026-08-17, because the docs do not say
# any of it. Metricool has **no in-place update**: PUT with the id in the body
# deletes the post and makes a new one, PUT without it leaves the original and
# makes a second. Either way the id changes, so the id that comes back is the
# only thing keeping a Draft attached to its post.


def test_an_edit_carries_the_post_id_in_its_body():
    """Without it Metricool duplicates instead of replacing.

    The path already names the post, so this looks redundant — right up until
    the planner has two of everything. The old app omits it
    (`metricoolService.ts:622`) and that is exactly what it does.
    """
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"id": 99}})

    publisher.update(
        "4605385", "42", "new text", "new body", None, client=_client(handler)
    )

    assert seen["method"] == "PUT"
    assert seen["body"]["id"] == 42, "no id in the body means a duplicate post"


def test_an_edit_hands_back_the_new_id_metricool_made():
    """The post that comes back is a different post. The caller must re-record it."""

    def handler(request):
        return httpx.Response(200, json={"data": {"id": 362758916}})

    assert (
        publisher.update("4605385", "42", "t", None, None, client=_client(handler))
        == "362758916"
    )


def test_an_edit_metricool_will_not_name_is_a_failure_not_a_shrug():
    """`schedule` tolerates a missing id; this cannot.

    By the time the response arrives the old post is already deleted, so a
    caller that carried on would leave the Draft pointing at nothing.
    """

    def handler(request):
        return httpx.Response(200, json={"data": {}})

    with pytest.raises(publisher.PublishError, match="no longer exists"):
        publisher.update("4605385", "42", "t", None, None, client=_client(handler))


def test_deleting_a_post_that_is_already_gone_is_success():
    """404 means gone, which is what the caller wanted.

    The common case is retrying a delete that actually landed. Note the body is
    XML despite being tagged `JsonErrorMessage`, so nothing may call `.json()`
    on the failure path.
    """

    def handler(request):
        return httpx.Response(
            404,
            text="<JsonErrorMessage><detail>Post id '42' does not exist.</detail>"
            "</JsonErrorMessage>",
        )

    publisher.delete("4605385", "42", client=_client(handler))  # does not raise


def test_a_refused_delete_still_reports_what_metricool_said():
    def handler(request):
        return httpx.Response(500, text="upstream is unwell")

    with pytest.raises(publisher.PublishError, match="unwell"):
        publisher.delete("4605385", "42", client=_client(handler))


def test_the_time_a_post_is_scheduled_for_survives_metricools_spelling():
    """It answers `Asia/Bangkok` for the `Asia/Ho_Chi_Minh` we sent, and drops
    the seconds. Same instant, different words — so the wall clock is read and
    the zone ignored, and the value stays naive so a round trip cannot move it.
    """
    from datetime import datetime

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": 42,
                    "publicationDate": {
                        "dateTime": "2026-08-20T03:40:00",
                        "timezone": "Asia/Bangkok",
                    },
                }
            },
        )

    post = publisher.get_post("4605385", "42", client=_client(handler))
    when = publisher.scheduled_at(post)

    assert when == datetime(2026, 8, 20, 3, 40)
    assert when.tzinfo is None, "a tzinfo here would convert the time and move the post"


def test_a_post_metricool_no_longer_has_reads_as_none():
    def handler(request):
        return httpx.Response(404, text="<JsonErrorMessage/>")

    assert publisher.get_post("4605385", "42", client=_client(handler)) is None


@pytest.fixture
def resyncs(monkeypatch):
    """Metricool's side of an edit, recorded rather than performed.

    `get_post` answers a fixed time so a test can prove an edit did not move the
    post, and `update` hands back a *different* id every call — which is what the
    real API does, and the thing a Draft has to keep up with.
    """
    calls: dict = {"order": [], "updates": [], "deleted": []}
    ids = iter(["900001", "900002", "900003"])

    def get_post(blog_id, post_id, client=None):
        calls["order"].append("get")
        return {
            "id": post_id,
            "publicationDate": {
                "dateTime": "2026-09-01T09:00:00",
                "timezone": "Asia/Bangkok",
            },
        }

    def update(blog_id, post_id, text, first_comment, image_url, when=None, client=None):
        calls["order"].append("update")
        calls["updates"].append(
            {
                "post_id": post_id,
                "text": text,
                "first_comment": first_comment,
                "image": image_url,
                "when": when,
            }
        )
        return next(ids)

    def delete(blog_id, post_id, client=None):
        calls["order"].append("delete")
        calls["deleted"].append(post_id)

    monkeypatch.setattr(publisher, "normalize_image", lambda url, blog, client=None: url)
    monkeypatch.setattr(publisher, "get_post", get_post)
    monkeypatch.setattr(publisher, "update", update)
    monkeypatch.setattr(publisher, "delete", delete)
    return calls


def test_a_caption_edit_reaches_metricool_and_the_new_id_is_recorded(
    client, ready, published, resyncs
):
    """The whole of D6's first half: fix a typo without opening the planner.

    The id assertion is the load-bearing one. Metricool replaced the post, so a
    Draft still holding `8891` would be pointing at something it just deleted —
    which is precisely the old app's bug.
    """
    client.post(f"/drafts/{ready.id}/publish")

    response = client.patch(f"/drafts/{ready.id}", json={"caption": "Fixed typo."})

    assert response.status_code == 200
    assert resyncs["updates"][0]["text"] == "Fixed typo."
    assert response.json()["metricool_post_id"] == "900001", "the id moves on every edit"
    assert client.get(f"/drafts/{ready.id}").json()["caption"] == "Fixed typo."


def test_editing_the_text_does_not_move_the_post(client, ready, published, resyncs):
    """`update` replaces the whole post, so an edit has to resend the time.

    Sending nothing means `publication_date(None)`, which is two minutes from
    now — a caption fix would quietly reschedule the post to immediately. So the
    time is read off the planner first.
    """
    from datetime import datetime

    client.post(f"/drafts/{ready.id}/publish")

    client.patch(f"/drafts/{ready.id}", json={"caption": "Fixed typo."})

    assert resyncs["order"][:2] == ["get", "update"], "read the time before sending it"
    assert resyncs["updates"][0]["when"] == datetime(2026, 9, 1, 9, 0)


def test_an_unscheduled_draft_is_not_pushed_anywhere(client, ready, resyncs):
    """The ordinary edit pays nothing. Most drafts have never been published."""
    client.patch(f"/drafts/{ready.id}", json={"caption": "Still in review."})

    assert resyncs["order"] == []


def test_rescheduling_sends_the_time_it_was_given(client, ready, published, resyncs):
    """No planner read: the caller supplied the time, so there is nothing to look up."""
    from datetime import datetime

    client.post(f"/drafts/{ready.id}/publish")

    response = client.post(
        f"/drafts/{ready.id}/reschedule", json={"when": "2026-09-14T07:30:00"}
    )

    assert response.status_code == 200
    assert resyncs["updates"][0]["when"] == datetime(2026, 9, 14, 7, 30)
    assert resyncs["order"] == ["update"], "the time was given, not read"
    assert response.json()["metricool_post_id"] == "900001"


def test_a_draft_that_was_never_scheduled_cannot_be_rescheduled(client, ready, resyncs):
    response = client.post(
        f"/drafts/{ready.id}/reschedule", json={"when": "2026-09-14T07:30:00"}
    )

    assert response.status_code == 409
    assert resyncs["order"] == []


def test_unscheduling_takes_the_post_out_and_gives_the_draft_back(
    client, ready, published, resyncs
):
    """The way back that D6 said did not exist.

    The draft survives — the text and the picture are still good, and the
    complaint was that a mistake could not be undone, not that the work should
    be thrown away.
    """
    client.post(f"/drafts/{ready.id}/publish")

    response = client.post(f"/drafts/{ready.id}/unschedule")

    assert response.status_code == 200
    assert resyncs["deleted"] == ["8891"]
    assert response.json()["metricool_post_id"] is None
    assert response.json()["status"] == DraftStatus.REVIEW


def test_unscheduling_lets_the_picture_be_redrawn_again(
    client, ready, published, resyncs
):
    """Clearing the id is what unfreezes the composite, and the order matters.

    The post is out of the planner before anything can delete the file it was
    pointing at — which is the whole reason the freeze existed.
    """
    client.post(f"/drafts/{ready.id}/publish")
    assert client.post(f"/drafts/{ready.id}/image").status_code == 409

    client.post(f"/drafts/{ready.id}/unschedule")

    assert client.post(f"/drafts/{ready.id}/image").status_code == 200


def test_a_post_metricool_no_longer_has_says_so_rather_than_editing_a_ghost(
    client, ready, published, resyncs, monkeypatch
):
    """Deleted in Metricool's own UI, which the operator is free to do (ADR-0001)."""
    client.post(f"/drafts/{ready.id}/publish")
    monkeypatch.setattr(publisher, "get_post", lambda blog, post, client=None: None)

    response = client.patch(f"/drafts/{ready.id}", json={"caption": "Fixed typo."})

    assert response.status_code == 409
    assert "Unschedule" in response.json()["detail"]


def test_a_post_metricool_never_named_cannot_be_edited(
    client, ready, session, published, resyncs
):
    """`publish` writes "queued" when the id was withheld. It is a marker, not a
    handle — there is nothing to send, so this has to say so rather than PUT to
    `/posts/queued`."""
    client.post(f"/drafts/{ready.id}/publish")
    draft = session.get(Draft, ready.id)
    draft.metricool_post_id = "queued"
    session.add(draft)
    session.commit()

    response = client.patch(f"/drafts/{ready.id}", json={"caption": "Fixed typo."})

    assert response.status_code == 409
    assert "planner" in response.json()["detail"]
    assert resyncs["order"] == []
