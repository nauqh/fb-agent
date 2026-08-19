"""The Overview screen: live performance, and the posts kept from it.

The two halves are tested differently on purpose. Performance is a read of
somebody else's service, so the transport is stubbed and what is asserted is the
*shaping* — the sort, the computed engagement, the epoch conversion. Saved posts
are ours, so they are asserted against the database.
"""

import pytest
from sqlmodel import select

from app.models import SavedPost
from app.sources import metricool


def _row(post_id: str, reactions=0, comments=0, shares=0, created=1786468297000, **extra):
    """A Metricool `/stats/facebook/posts` row, in the shape the live API sends.

    `engagement` is null here because it is null on every real row we have seen —
    which is why the code computes its own rather than reading it.
    """
    return {
        "postId": post_id,
        "text": f"post {post_id}",
        "permalinkUrl": f"https://facebook.com/{post_id}",
        "picture": "https://scontent.xx.fbcdn.net/x.jpg",
        "created": created,
        "reactions": reactions,
        "comments": comments,
        "shares": shares,
        "clicks": 0,
        "impressions": 100,
        "engagement": None,
        **extra,
    }


@pytest.fixture
def writes(monkeypatch):
    """Stub the writer, so reuse exercises the run without a model call.

    Local rather than shared with `test_generate.py`: that module's `written`
    fixture is its own, and importing fixtures across test modules is how a
    change to one silently breaks the other.
    """
    from app import generate
    from app.writer.agent import DraftContent

    class Result:
        output = DraftContent(
            hook="A hook about the serum run that is comfortably under the cap.",
            caption="🐕 A relay of dog teams carried it.",
            first_comment="x" * 1850,
            highlight_phrases=["serum run"],
            image_prompt="a sled dog team on sea ice",
        )

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())
    return Result


@pytest.fixture
def stats(monkeypatch):
    """Whatever the Page's stats are, without leaving the building."""

    def use(rows):
        monkeypatch.setattr(metricool, "page_posts", lambda *a, **k: rows)

    use([])
    return use


def test_posts_come_back_best_first(client, page, stats):
    """Metricool's own `sortcolumn` is accepted and ignored — asking for
    reactions returned a zero-reaction post first while the window held one
    with 160,282. So the order has to be ours."""
    stats([
        _row("a", reactions=1),
        _row("b", reactions=500, comments=10, shares=5),
        _row("c", reactions=50),
    ])

    posts = client.get("/overview/performance?page_id=1").json()

    assert [p["post_id"] for p in posts] == ["b", "c", "a"]


def test_engagement_is_computed_not_read(client, page, stats):
    """Their `engagement` field is null on every row. Three numbers that are
    populated beat one that is not."""
    stats([_row("a", reactions=10, comments=3, shares=2)])

    assert client.get("/overview/performance?page_id=1").json()[0]["engagement"] == 15


def test_the_published_time_is_read_from_epoch_milliseconds(client, page, stats):
    stats([_row("a", created=1786468297000)])

    when = client.get("/overview/performance?page_id=1").json()[0]["published_at"]

    assert when.startswith("2026-"), when


def test_metricool_being_down_is_a_502_not_an_empty_page(client, page, monkeypatch):
    """An empty grid reads as a Page that has never posted."""
    def boom(*a, **k):
        raise metricool.StatsError("Metricool refused the post stats (500)")

    monkeypatch.setattr(metricool, "page_posts", boom)

    assert client.get("/overview/performance?page_id=1").status_code == 502


def test_a_post_can_be_saved_and_says_so_next_time(client, page, stats):
    stats([_row("a", reactions=99)])
    assert client.get("/overview/performance?page_id=1").json()[0]["saved"] is False

    client.post(
        "/overview/saved",
        json={"page_id": 1, "post_id": "a", "text": "post a", "reactions": 99},
    )

    assert client.get("/overview/performance?page_id=1").json()[0]["saved"] is True


def test_the_metrics_are_a_snapshot_not_a_live_figure(client, page, session, stats):
    """A saved post outlives the window it was found in, so its numbers cannot
    be re-read — they are what it scored when it was kept."""
    client.post(
        "/overview/saved",
        json={"page_id": 1, "post_id": "a", "text": "t", "reactions": 99, "shares": 4},
    )

    stats([_row("a", reactions=1_000_000)])
    client.get("/overview/performance?page_id=1")

    kept = session.exec(select(SavedPost)).first()
    assert kept.reactions == 99, "the snapshot was overwritten by a later read"


def test_saving_the_same_post_twice_is_refused(client, page):
    body = {"page_id": 1, "post_id": "a", "text": "t"}
    assert client.post("/overview/saved", json=body).status_code == 201
    assert client.post("/overview/saved", json=body).status_code == 409


def test_a_saved_post_survives_falling_out_of_the_window(client, page, stats):
    """The whole reason this is a table. Metricool's stats take a date range,
    so an old post is in no read at all — and a reference that disappears on a
    rolling window is not a reference."""
    client.post("/overview/saved", json={"page_id": 1, "post_id": "old", "text": "t"})

    stats([])  # the window no longer contains it

    assert client.get("/overview/performance?page_id=1").json() == []
    assert len(client.get("/overview/saved?page_id=1").json()) == 1


def test_unsaving_removes_it(client, page):
    saved = client.post(
        "/overview/saved", json={"page_id": 1, "post_id": "a", "text": "t"}
    ).json()

    assert client.delete(f"/overview/saved/{saved['id']}").status_code == 204
    assert client.get("/overview/saved?page_id=1").json() == []


# --- writing a saved post again ----------------------------------------------


def test_reusing_a_saved_post_writes_its_story_again(client, page, writes, illustrated):
    """The point of keeping a top performer. The same story, written fresh —
    not a copy, and not a style sample."""
    saved = client.post(
        "/overview/saved",
        json={"page_id": 1, "post_id": "a", "text": "The 1925 serum run to Nome."},
    ).json()

    response = client.post(f"/overview/saved/{saved['id']}/reuse")

    assert response.status_code == 202
    draft_ids = response.json()
    assert len(draft_ids) == 1
    draft = client.get(f"/drafts/{draft_ids[0]}").json()
    assert draft["topic"] == "The 1925 serum run to Nome.", (
        "it runs as a topic, so the subject binds without the writer treating "
        "our own prose as an article to summarise"
    )
    assert draft["source_item_id"] is None


def test_reusing_leaves_the_saved_post_alone(client, page, writes, illustrated):
    """Reuse is not a move. The reference stays a reference."""
    saved = client.post(
        "/overview/saved", json={"page_id": 1, "post_id": "a", "text": "A story."}
    ).json()

    client.post(f"/overview/saved/{saved['id']}/reuse")

    assert len(client.get("/overview/saved?page_id=1").json()) == 1


def test_a_saved_post_with_no_text_cannot_be_reused(client, page):
    saved = client.post(
        "/overview/saved", json={"page_id": 1, "post_id": "a", "text": ""}
    ).json()

    assert client.post(f"/overview/saved/{saved['id']}/reuse").status_code == 409


def test_reusing_something_that_is_not_there_says_so(client, page):
    assert client.post("/overview/saved/999/reuse").status_code == 404


# --- reposting the original ---------------------------------------------------
#
# The client asked for "a button to just repost the original", distinct from
# writing the story again. The whole difficulty is the picture: a saved post's
# `picture_url` is Facebook's CDN, signed and expiring, and Metricool keeps a
# *link* that Facebook resolves days later. Measured on 2026-08-18, one of the
# six oldest saved posts already answered 403. So the image is copied into our
# bucket at repost time, and these tests pin that rather than the happy path
# alone.


@pytest.fixture
def cdn(monkeypatch):
    """Facebook's image host, answering however the test wants it to."""
    import httpx

    state = {
        "status": 200,
        "content": b"\xff\xd8\xff jpeg bytes",
        "type": "image/jpeg",
        # Which URL was actually fetched. The whole point of the planner lookup
        # is that this is not the saved post's thumbnail.
        "fetched": None,
    }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            state["fetched"] = url
            if state["status"] == "boom":
                raise httpx.ConnectError("no route to host")
            return httpx.Response(
                state["status"],
                content=state["content"],
                headers={"content-type": state["type"]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    return state


PUBLISHED_AT = "2026-06-01T09:00:00"


@pytest.fixture
def planner(monkeypatch):
    """Metricool's planner, holding the post a repost is actually copied from.

    Stubbed here for the same reason the stats call is: it is somebody else's
    service. What matters is that the route reads `media` and `firstCommentText`
    from *this* row rather than from the saved post — the saved post's
    `picture_url` is a 130-pixel thumbnail and has no first comment at all.
    """
    from app.publish import repost

    state = {
        "rows": [
            {
                "text": "The 1925 serum run to Nome.",
                "firstCommentText": "The dogs ran 674 miles in 127 hours.",
                "media": ["https://static.metricool.com/full-size.jpg"],
                "publicationDate": {"dateTime": PUBLISHED_AT},
            }
        ],
        "error": None,
    }

    def fake_list_scheduled(blog_id, start, end, client=None):
        if state["error"]:
            raise state["error"]
        return state["rows"]

    monkeypatch.setattr(repost.publisher, "list_scheduled", fake_list_scheduled)
    return state


def _saved_with_picture(client, text="The 1925 serum run to Nome."):
    return client.post(
        "/overview/saved",
        json={
            "page_id": 1,
            "post_id": "a",
            "text": text,
            # The thumbnail, which is all the stats call ever returns. Nothing
            # should reach for it now that the planner carries the real file.
            "picture_url": "https://scontent.xx.fbcdn.net/signed.jpg",
            "published_at": PUBLISHED_AT,
        },
    ).json()


def test_reposting_copies_the_image_into_our_own_bucket(client, page, cdn, planner):
    """The point of the whole feature. Handing Metricool the CDN URL would
    publish whatever it resolves to days later, which is increasingly nothing."""
    saved = _saved_with_picture(client)

    response = client.post(f"/overview/saved/{saved['id']}/repost")

    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "review", "a repost is reviewed, never published straight out"
    assert draft["caption"] == "The 1925 serum run to Nome.", "the caption verbatim"
    assert draft["composed_image_path"], "the copied image, not the CDN URL"
    assert "fbcdn" not in draft["composed_image_path"], (
        "the stored path must be ours — a Facebook URL here is the bug this "
        "feature exists to avoid"
    )


def test_a_repost_carries_the_first_comment(client, page, cdn, planner):
    """The stats row has no first comment on it and no column here ever held
    one, so a repost published the caption alone and dropped the body of the
    post it was repeating. The planner has it."""
    saved = _saved_with_picture(client)

    draft = client.post(f"/overview/saved/{saved['id']}/repost").json()

    assert draft["first_comment"] == "The dogs ran 674 miles in 127 hours."


def test_the_picture_comes_from_the_planner_not_the_saved_thumbnail(
    client, page, cdn, planner
):
    """`SavedPost.picture_url` is Facebook's 130×163 thumbnail — the URL carries
    `stp=dst-jpg_p130x130`, and the full-size sibling is empty on all 633 posts
    measured. Publishing it puts a pixelated image on the page. The planner
    carries the 896×1120 file we handed Metricool at publish time."""
    saved = _saved_with_picture(client)

    client.post(f"/overview/saved/{saved['id']}/repost")

    assert cdn["fetched"] == "https://static.metricool.com/full-size.jpg", (
        "the thumbnail must not be what gets copied"
    )


def test_a_post_whose_original_is_gone_is_refused_rather_than_pixelated(
    client, page, cdn, planner
):
    """382 of this account's 2,197 posts are the old tool's, and their image
    links have lapsed. The thumbnail would publish without complaint and look
    wrong, so this refuses instead."""
    saved = _saved_with_picture(client)
    planner["rows"] = []

    response = client.post(f"/overview/saved/{saved['id']}/repost")

    assert response.status_code == 409
    assert "thumbnail" in response.json()["detail"]
    assert client.get("/drafts").json() == [], "and no draft is left behind"


def test_the_planner_being_unreachable_reads_as_no_original(client, page, cdn, planner):
    """Not a 502. The operator's next move is the same either way — “Write
    again” — and a repost that cannot find its picture cannot proceed."""
    from app.publish.metricool import PublishError

    saved = _saved_with_picture(client)
    planner["error"] = PublishError("planner down")

    assert client.post(f"/overview/saved/{saved['id']}/repost").status_code == 409


def test_an_expired_image_is_refused_with_a_reason(client, page, cdn, planner):
    """The expected end state, not a bug. 403 is what the old app's signed URLs
    do once they age out, and the message has to say what to do instead."""
    saved = _saved_with_picture(client)
    cdn["status"] = 403

    response = client.post(f"/overview/saved/{saved['id']}/repost")

    assert response.status_code == 409
    assert "expired" in response.json()["detail"]


def test_a_failed_copy_leaves_no_half_built_draft(client, page, cdn, planner):
    """A draft with a caption and no picture looks publishable and is not."""
    saved = _saved_with_picture(client)
    cdn["status"] = 403

    client.post(f"/overview/saved/{saved['id']}/repost")

    assert client.get("/drafts").json() == [], "the row is rolled back, not left behind"


def test_the_image_host_being_unreachable_is_a_502(client, page, cdn, planner):
    saved = _saved_with_picture(client)
    cdn["status"] = "boom"

    assert client.post(f"/overview/saved/{saved['id']}/repost").status_code == 502


def test_something_that_is_not_an_image_is_refused(client, page, cdn, planner):
    """An HTML error page served with 200 is the classic way this fails."""
    saved = _saved_with_picture(client)
    cdn["type"] = "text/html"

    assert client.post(f"/overview/saved/{saved['id']}/repost").status_code == 409


def test_a_saved_post_with_no_picture_cannot_be_reposted(client, page, planner):
    """Nothing to repost. `Write again` is the answer, and the message says so.

    The saved row carries no `published_at` here either, so the planner cannot
    even be asked — which is the same outcome by a different road.
    """
    saved = client.post(
        "/overview/saved", json={"page_id": 1, "post_id": "a", "text": "A story."}
    ).json()

    response = client.post(f"/overview/saved/{saved['id']}/repost")

    assert response.status_code == 409
    assert "Write again" in response.json()["detail"]


def test_reposting_leaves_the_saved_post_alone(client, page, cdn, planner):
    saved = _saved_with_picture(client)

    client.post(f"/overview/saved/{saved['id']}/repost")

    assert len(client.get("/overview/saved?page_id=1").json()) == 1


def test_reposting_something_that_is_not_there_says_so(client, page):
    assert client.post("/overview/saved/999/repost").status_code == 404
