"""Automatic save and repost (H2): `app.publish.auto_repost`.

Metricool is stubbed at the adapters - the stats call, the planner read, and
normalize + schedule - and the image copy at `repost.copy_original_image`, whose
own failure shapes `test_overview.py` already pins. What is asserted is the
decisions: what gets saved, which slot a repost takes, and that nothing is done
twice.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import select

from app.models import Draft, DraftStatus, PageTimeSlot, SavedPost
from app.publish import auto_repost, repost
from app.publish import metricool as publisher
from app.settings import settings
from app.sources import metricool

ZONE = ZoneInfo(settings.timezone)
FB = "569035169625026"


def _local_now() -> datetime:
    return datetime.now(ZONE).replace(tzinfo=None)


def _published(days_ago: int, hour: int = 9) -> datetime:
    """A naive local publish time `days_ago` days back, on the hour."""
    return (_local_now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def _caption(post_id: str) -> str:
    return f"The story of post {post_id}, told at enough length to be its own caption."


class Metricool:
    """The stats call, the planner and the scheduler, as one fake account."""

    def __init__(self):
        self.stats: list[dict] = []
        self.planner: list[dict] = []
        self.scheduled: list[dict] = []
        self.planner_reads: list[tuple[datetime, datetime]] = []
        self.refuse_schedule = False

    def post(self, post_id: str, reactions: int, published: datetime, page_fb: str = FB):
        """A published post: a stats row, and the planner row it went out from."""
        instant = published.replace(tzinfo=ZONE)
        self.stats.append(
            {
                "postId": f"{page_fb}_{post_id}",
                "text": _caption(post_id),
                "created": int(instant.timestamp() * 1000),
                "reactions": reactions,
                "comments": 0,
                "shares": 0,
                "impressions": 10,
            }
        )
        self.planner.append(
            {
                "text": _caption(post_id),
                "firstCommentText": "The body.",
                "media": [f"https://bucket.example/{post_id}.jpg"],
                "publicationDate": {"dateTime": published.isoformat()},
            }
        )

    def list_scheduled(self, blog_id, start, end, client=None):
        self.planner_reads.append((start, end))
        return self.planner

    def schedule(self, blog_id, text, first_comment, image_url, when=None, client=None):
        if self.refuse_schedule:
            raise publisher.PublishError("Metricool refused the post (500): no")
        self.scheduled.append({"text": text, "when": when})
        # Now in the planner, where the next run's busy set will find it.
        self.planner.append({"text": text, "publicationDate": {"dateTime": when.isoformat()}})
        return f"mc-{len(self.scheduled)}"


@pytest.fixture
def account(monkeypatch):
    fake = Metricool()
    monkeypatch.setattr(settings, "metricool_publish_as_draft", False)
    monkeypatch.setattr(metricool, "page_posts", lambda *a, **k: fake.stats)
    monkeypatch.setattr(publisher, "list_scheduled", fake.list_scheduled)
    monkeypatch.setattr(publisher, "schedule", fake.schedule)
    monkeypatch.setattr(publisher, "normalize_image", lambda url, blog, client=None: url)
    return fake


@pytest.fixture
def copies(monkeypatch):
    """The image copy. `state["error"]` makes it refuse."""
    state = {"error": None, "calls": 0}

    def copy(url, draft_id):
        state["calls"] += 1
        if state["error"]:
            raise state["error"]
        return f"2026-09/{draft_id}-repost.jpg"

    monkeypatch.setattr(repost, "copy_original_image", copy)
    return state


@pytest.fixture
def auto(session, page):
    """History Retraced at 1000 reactions, reposting after 30 days, 03:00 and 09:00.

    Two slots, not one, so that a repost 7 hours off (UTC read as local) lands
    on the wrong one rather than on the same one by luck."""
    page.auto_save_min_reactions = 1000
    page.auto_repost_after_days = 30
    session.add(page)
    session.add_all(
        [
            PageTimeSlot(page_id=page.id, minute_of_day=3 * 60),
            PageTimeSlot(page_id=page.id, minute_of_day=9 * 60),
        ]
    )
    session.commit()
    return page


def _saved(session) -> list[SavedPost]:
    session.expire_all()
    return list(session.exec(select(SavedPost)).all())


# --- saving -------------------------------------------------------------------


def test_a_post_at_the_threshold_is_saved_and_one_below_is_not(session, auto, account, copies):
    auto.auto_repost_after_days = None
    account.post("at", 1000, _published(5))
    account.post("below", 999, _published(5))

    auto_repost.run(session, auto)

    [row] = _saved(session)
    assert row.metricool_post_id == f"{FB}_at"
    assert row.auto_saved is True
    assert row.note == "Saved automatically at 1,000 reactions"


def test_a_post_already_saved_by_hand_is_not_saved_again(client, session, auto, account, copies):
    account.post("a", 5000, _published(5))
    client.post("/overview/saved", json={"page_id": 1, "post_id": f"{FB}_a", "text": "t"})

    auto_repost.run(session, auto)

    [row] = _saved(session)
    assert row.auto_saved is False
    assert account.scheduled == [], "a hand-saved post is not auto-reposted"


def test_a_row_belonging_to_another_facebook_page_is_ignored(session, auto, account, copies):
    """Hot Tub Timeout's blog id returns History Retraced's posts."""
    account.post("theirs", 5000, _published(5), page_fb="999")

    auto_repost.run(session, auto)

    assert _saved(session) == []


def test_a_post_whose_caption_is_already_saved_is_not_saved(session, auto, account, copies):
    """A repost is the same caption under a new id, and is not reposted (Q3)."""
    account.post("original", 5000, _published(20))
    auto.auto_repost_after_days = None
    auto_repost.run(session, auto)

    account.stats[0]["postId"] = f"{FB}_the-repost"
    auto_repost.run(session, auto)

    assert len(_saved(session)) == 1


# --- reposting ----------------------------------------------------------------


def test_a_repost_takes_the_first_free_slot_after_publish_plus_n_days(session, auto, account, copies):
    """In the Page's zone: published 09:00 local is 02:00 UTC, and adding 30
    days to that would take the 03:00 slot instead."""
    published = _published(10)
    account.post("a", 5000, published)

    auto_repost.run(session, auto)

    [scheduled] = account.scheduled
    assert scheduled["when"] == published + timedelta(days=30)
    [row] = _saved(session)
    draft = session.get(Draft, row.repost_draft_id)
    assert draft.metricool_post_id == "mc-1"
    assert draft.status == DraftStatus.REVIEW


def test_a_past_target_takes_the_next_free_slot_from_now(session, auto, account, copies):
    auto.auto_repost_after_days = 1
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)

    [scheduled] = account.scheduled
    now = _local_now()
    assert now < scheduled["when"] <= now + timedelta(hours=24)
    assert scheduled["when"].hour in (3, 9)


def test_the_planner_read_reaches_a_target_more_than_30_days_out(session, auto, account, copies):
    auto.auto_repost_after_days = 60
    published = _published(10)
    account.post("a", 5000, published)

    auto_repost.run(session, auto)

    assert account.scheduled[0]["when"] == published + timedelta(days=60)
    # The widest read is the busy set; the others are `original_for`'s ±2 days.
    assert max(end for _, end in account.planner_reads) >= published + timedelta(days=90)


def test_two_reposts_in_one_run_take_two_slots(session, auto, account, copies):
    published = _published(10)
    account.post("a", 5000, published)
    account.post("b", 5000, published)

    auto_repost.run(session, auto)

    whens = [post["when"] for post in account.scheduled]
    assert len(whens) == 2 and len(set(whens)) == 2


def test_running_twice_creates_one_repost(session, auto, account, copies):
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)
    auto_repost.run(session, auto)

    assert len(account.scheduled) == 1
    assert len(session.exec(select(Draft)).all()) == 1


def test_a_run_schedules_at_most_three_earliest_targets_first(session, auto, account, copies):
    for days_ago in (5, 25, 10, 20, 15):
        account.post(f"p{days_ago}", 5000, _published(days_ago))

    auto_repost.run(session, auto)

    texts = [post["text"] for post in account.scheduled]
    assert texts == [_caption("p25"), _caption("p20"), _caption("p15")]


def test_a_dead_original_is_recorded_and_not_tried_again(session, auto, account, copies):
    copies["error"] = repost.RepostError("The original image has expired - 403.")
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)
    auto_repost.run(session, auto)

    [row] = _saved(session)
    assert row.repost_error.startswith("The original image has expired")
    assert copies["calls"] == 1
    assert session.exec(select(Draft)).all() == [], "a failed copy leaves no draft"


def test_a_host_that_did_not_answer_is_retried_next_run(session, auto, account, copies):
    copies["error"] = repost.RepostError("The image host did not answer.", status=502)
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)
    [row] = _saved(session)
    assert row.repost_error is None and row.repost_draft_id is None

    copies["error"] = None
    auto_repost.run(session, auto)
    assert len(account.scheduled) == 1


def test_metricool_refusing_leaves_the_draft_in_review_and_builds_no_second(
    session, auto, account, copies
):
    account.refuse_schedule = True
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)
    auto_repost.run(session, auto)

    [draft] = session.exec(select(Draft)).all()
    assert draft.metricool_post_id is None
    assert draft.status == DraftStatus.REVIEW
    assert "Not scheduled automatically" in draft.warnings[-1]


def test_no_free_slot_leaves_the_draft_in_review_with_a_warning(session, auto, account, copies):
    published = _published(10)
    account.post("a", 5000, published)
    target = published + timedelta(days=30)
    for day in range(31):
        for hour in (3, 9):
            stamp = (target + timedelta(days=day)).replace(hour=hour)
            account.planner.append({"text": "x", "publicationDate": {"dateTime": stamp.isoformat()}})

    auto_repost.run(session, auto)

    assert account.scheduled == []
    [draft] = session.exec(select(Draft)).all()
    assert "already has a post" in draft.warnings[-1]


def test_auto_repost_off_saves_but_schedules_nothing(session, auto, account, copies):
    auto.auto_repost_after_days = None
    account.post("a", 5000, _published(10))

    auto_repost.run(session, auto)

    assert len(_saved(session)) == 1
    assert account.scheduled == [] and copies["calls"] == 0


def test_rehearsal_does_nothing_and_a_dry_run_writes_nothing(
    session, auto, account, copies, monkeypatch
):
    monkeypatch.setattr(settings, "metricool_publish_as_draft", True)
    account.post("a", 5000, _published(10))

    assert auto_repost.run(session, auto) == auto_repost.Report()

    report = auto_repost.run(session, auto, dry_run=True)
    assert report.saved == [f"{FB}_a"]
    assert [post_id for post_id, _ in report.scheduled] == [f"{FB}_a"]
    assert _saved(session) == []
    assert account.scheduled == [] and copies["calls"] == 0


# --- unsaving -----------------------------------------------------------------


def test_unsaving_an_auto_saved_post_dismisses_it_for_good(client, session, auto, account, copies):
    auto.auto_repost_after_days = None
    account.post("a", 5000, _published(10))
    auto_repost.run(session, auto)
    [row] = _saved(session)

    assert client.delete(f"/overview/saved/{row.id}").status_code == 204
    assert client.get("/overview/saved?page_id=1").json() == []

    auto.auto_repost_after_days = 30
    account.post("same-caption-new-id", 5000, _published(3))
    account.stats[-1]["text"] = account.stats[0]["text"]
    auto_repost.run(session, auto)

    [row] = _saved(session)
    assert row.dismissed_at is not None
    assert account.scheduled == []


def test_saving_a_dismissed_post_by_hand_restores_it(client, session, auto, account, copies):
    auto.auto_repost_after_days = None
    account.post("a", 5000, _published(10))
    auto_repost.run(session, auto)
    [row] = _saved(session)
    client.delete(f"/overview/saved/{row.id}")

    response = client.post(
        "/overview/saved", json={"page_id": 1, "post_id": f"{FB}_a", "text": "t"}
    )

    assert response.status_code == 201
    assert response.json()["dismissed_at"] is None
    assert response.json()["auto_saved"] is False


def test_deleting_a_repost_draft_clears_the_link(session, auto, account, copies):
    account.refuse_schedule = True
    account.post("a", 5000, _published(10))
    auto_repost.run(session, auto)
    [draft] = session.exec(select(Draft)).all()

    session.delete(draft)
    session.commit()

    [row] = _saved(session)
    assert row.repost_draft_id is None


# --- the trigger --------------------------------------------------------------


def test_get_pages_queues_one_run_per_six_hours(client, session, auto, monkeypatch):
    runs = []
    monkeypatch.setattr(auto_repost, "run_pages", lambda ids: runs.append(ids))

    client.get("/pages")
    client.get("/pages")

    assert runs == [[auto.id]]


def test_a_page_with_auto_save_off_is_not_queued(client, page, monkeypatch):
    runs = []
    monkeypatch.setattr(auto_repost, "run_pages", lambda ids: runs.append(ids))

    client.get("/pages")

    assert runs == []


def test_get_pages_answers_the_same_when_the_run_raises(client, session, auto, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Metricool is on fire")

    monkeypatch.setattr(auto_repost, "run", boom)

    response = client.get("/pages")

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["History Retraced"]
