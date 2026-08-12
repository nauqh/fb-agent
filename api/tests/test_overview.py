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
