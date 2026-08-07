"""The run. Generate is the only thing that writes a Source Item."""

import pytest
from sqlmodel import Session, func, select

from app import generate
from app.models import Draft, DraftStatus, SourceItem, SourceItemBase, SourceKind
from app.settings import settings
from app.writer.agent import DraftContent

CURATED = "https://www.smithsonianmag.com/history/a-story-180987410/"

GOOD = DraftContent(
    hook="Marie Tharp mapped the ocean floor in 1957.",
    caption="🌊 She drew the ridge by hand.",
    first_comment=(
        "Marie Tharp (1920-2006) worked in ink.\n\n" + "She redrew the sea floor. " * 62
    ),
    highlight_phrases=["Marie Tharp", "1957"],
    hashtags=[],
    image_prompt="A woman at a drafting table.",
)


def _count(engine, model) -> int:
    with Session(engine) as session:
        return session.exec(select(func.count()).select_from(model)).one()


def _rss(external_id: str = CURATED) -> SourceItemBase:
    return SourceItemBase(
        kind=SourceKind.RSS, external_id=external_id, url=external_id, text="A story"
    )


@pytest.fixture
def written(monkeypatch):
    """Stub the writer. The agent has its own tests; this is about the run."""

    class Result:
        output = GOOD

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())
    return Result


# --- the contract: generate is the only write --------------------------------


def test_generating_from_an_unsaved_item_creates_its_row(client, engine, written):
    response = client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    assert response.status_code == 202
    assert _count(engine, SourceItem) == 1, "the row is created here, not at tick"
    assert _count(engine, Draft) == 1


def test_the_same_item_twice_reuses_its_row(client, engine, written):
    body = {"page_ids": [1], "sources": [_rss().model_dump(mode="json")]}
    client.post("/generate", json=body)
    client.post("/generate", json=body)

    assert _count(engine, SourceItem) == 1
    assert _count(engine, Draft) == 2


def test_an_rss_item_from_outside_the_curated_list_is_refused(client, engine, written):
    smuggled = _rss("https://evil.example/post").model_dump(mode="json")

    response = client.post("/generate", json={"page_ids": [1], "sources": [smuggled]})

    assert response.status_code == 422
    assert "curated" in response.json()["detail"]
    assert _count(engine, SourceItem) == 0, "nothing is written when a run is refused"
    assert _count(engine, Draft) == 0


def test_a_competitor_post_must_already_exist(client, engine, written):
    """The sync owns those rows; there is no host allowlist for a Facebook post."""
    forged = SourceItemBase(
        kind=SourceKind.COMPETITOR_POST, external_id="1_2", text="anything at all"
    ).model_dump(mode="json")

    response = client.post("/generate", json={"page_ids": [1], "sources": [forged]})

    assert response.status_code == 422
    assert "Sync the Competitors tab" in response.json()["detail"]
    assert _count(engine, SourceItem) == 0


def test_a_competitor_post_that_was_synced_is_accepted(client, engine, session, written):
    session.add(
        SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="1_2", text="synced")
    )
    session.commit()

    body = SourceItemBase(
        kind=SourceKind.COMPETITOR_POST, external_id="1_2", text="ignored"
    ).model_dump(mode="json")
    response = client.post("/generate", json={"page_ids": [1], "sources": [body]})

    assert response.status_code == 202
    assert _count(engine, SourceItem) == 1, "matched, not duplicated"


def test_a_run_with_no_page_is_refused(client, written):
    assert client.post("/generate", json={"page_ids": []}).status_code == 422


def test_a_run_with_neither_sources_nor_a_topic_is_refused(client, written):
    assert client.post("/generate", json={"page_ids": [1]}).status_code == 422


def test_a_topic_only_run_needs_no_source(client, engine, written):
    response = client.post("/generate", json={"page_ids": [1], "topic": "Marie Tharp"})

    assert response.status_code == 202
    assert _count(engine, SourceItem) == 0
    assert _count(engine, Draft) == 1


# --- what the run produces ---------------------------------------------------


def test_a_finished_draft_carries_the_writer_output(client, engine, written):
    [draft_id] = client.post(
        "/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]}
    ).json()

    draft = client.get(f"/drafts/{draft_id}").json()
    assert draft["status"] == "review"
    assert draft["hook"] == GOOD.hook
    assert draft["progress_pct"] == 100
    assert draft["error"] is None


def test_a_highlight_that_is_not_verbatim_becomes_a_warning(client, monkeypatch):
    """Highlighting is a substring match, so an off-by-one renders no gold."""

    class Result:
        output = GOOD.model_copy(update={"highlight_phrases": ["Marie  Tharp"]})

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())

    [draft_id] = client.post("/generate", json={"page_ids": [1], "topic": "x"}).json()

    warnings = client.get(f"/drafts/{draft_id}").json()["warnings"]
    assert any("no gold" in w for w in warnings)


def test_a_writer_failure_lands_on_the_row_not_in_a_log(client, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("model refused")

    monkeypatch.setattr(generate.writer, "write", boom)

    [draft_id] = client.post("/generate", json={"page_ids": [1], "topic": "x"}).json()

    draft = client.get(f"/drafts/{draft_id}").json()
    assert draft["status"] == "failed", "a failed run must not sit at generating"
    assert "model refused" in draft["error"]
    assert draft["progress_step"] == "failed"

    # Not `review`, which is what it used to be: an empty row in the review
    # queue reads as a draft awaiting a decision, and the only sign otherwise
    # was an `error` column nothing rendered.
    assert client.post(f"/drafts/{draft_id}/approve").status_code == 409
    assert client.post(f"/drafts/{draft_id}/reject").status_code == 200


def test_a_restart_sweeps_rows_left_generating(session, engine, page):
    """Otherwise a killed process leaves a row spinning forever."""
    session.add(Draft(page_id=1, status=DraftStatus.GENERATING, progress_step="writing"))
    session.commit()

    assert generate.sweep_stranded(session) == 1

    with Session(engine) as fresh:
        draft = fresh.exec(select(Draft)).one()
        assert draft.status == DraftStatus.FAILED
        assert "restart" in draft.error


# --- review actions ----------------------------------------------------------


def test_approve_is_reversible(client, written):
    [draft_id] = client.post("/generate", json={"page_ids": [1], "topic": "x"}).json()

    assert client.post(f"/drafts/{draft_id}/approve").json()["status"] == "approved"
    assert client.post(f"/drafts/{draft_id}/unapprove").json()["status"] == "review"


def test_an_edit_saves_only_the_written_fields(client, written):
    [draft_id] = client.post("/generate", json={"page_ids": [1], "topic": "x"}).json()

    draft = client.patch(f"/drafts/{draft_id}", json={"hook": "Edited."}).json()

    assert draft["hook"] == "Edited."
    assert draft["caption"] == GOOD.caption, "untouched fields must survive"


def test_a_draft_still_being_written_cannot_be_edited(client, session):
    session.add(Draft(page_id=1, status=DraftStatus.GENERATING))
    session.commit()
    draft_id = session.exec(select(Draft)).one().id

    assert client.patch(f"/drafts/{draft_id}", json={"hook": "x"}).status_code == 409


# --- behaviour inherited from the deleted POST /sources ----------------------


def test_the_same_item_twice_in_one_run_is_one_row(client, engine, written):
    """Two feeds carrying one story arrive as two ticks in a single request.

    Nothing has committed when the second copy is looked up, so this relies on
    the autoflush before each query rather than on the unique constraint.
    """
    item = _rss().model_dump(mode="json")

    response = client.post("/generate", json={"page_ids": [1], "sources": [item, item]})

    assert response.status_code == 202
    assert _count(engine, SourceItem) == 1
    assert _count(engine, Draft) == 2, "two drafts, one source"


def test_one_of_each_kind_creates_three_rows(client, engine, session, written):
    session.add(
        SourceItem(kind=SourceKind.COMPETITOR_POST, external_id="1_2", text="synced")
    )
    session.commit()

    sources = [
        SourceItemBase(
            kind=SourceKind.COMPETITOR_POST, external_id="1_2", text="synced"
        ).model_dump(mode="json"),
        _rss().model_dump(mode="json"),
        SourceItemBase(
            kind=SourceKind.TWEET, external_id="1817449230118928441", text="a tweet"
        ).model_dump(mode="json"),
    ]
    response = client.post("/generate", json={"page_ids": [1], "sources": sources})

    assert response.status_code == 202
    assert _count(engine, SourceItem) == 3
    with Session(engine) as fresh:
        kinds = {row.kind for row in fresh.exec(select(SourceItem)).all()}
    assert kinds == {SourceKind.COMPETITOR_POST, SourceKind.RSS, SourceKind.TWEET}


def test_generating_twice_does_not_rewrite_an_existing_row(client, engine, written):
    """The client hands back a body it was shown, not a fresh vendor read."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    tampered = _rss().model_dump(mode="json") | {"text": "rewritten", "reactions": 999}
    client.post("/generate", json={"page_ids": [1], "sources": [tampered]})

    with Session(engine) as fresh:
        row = fresh.exec(select(SourceItem)).one()
    assert row.text == "A story"
    assert row.reactions is None


# --- the image, which must never take the text down with it ------------------


def test_a_finished_run_composes_an_image(client, engine, written, illustrated):
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    draft = client.get("/drafts/1").json()

    assert draft["status"] == "review"
    assert draft["hero_image_path"], "the generated hero was not stored"
    assert draft["composed_image_path"], "the composite was not stored"


def test_the_hero_and_the_composite_are_stored_apart(client, written, illustrated):
    """So editing the overlay can re-composite without re-buying the picture."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    draft = client.get("/drafts/1").json()

    assert draft["hero_image_path"] != draft["composed_image_path"]


def test_a_refused_image_leaves_the_text_usable(client, written, monkeypatch):
    """The whole point of the split. A failed picture is a warning, not a dead row.

    Without this a perfectly good caption is thrown away because one prompt
    tripped a safety filter.
    """
    from app.image import hero

    def refuse(*_a, **_k):
        raise hero.HeroError("the model returned no image")

    monkeypatch.setattr(hero, "generate", refuse)

    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    draft = client.get("/drafts/1").json()

    assert draft["status"] == "review", "a missing picture must not fail the draft"
    assert draft["hook"], "the text survived"
    assert draft["composed_image_path"] is None
    assert any(warning.startswith(generate.IMAGE_WARNING) for warning in draft["warnings"])


def test_recompositing_reuses_the_paid_hero(client, written, illustrated, monkeypatch):
    """`POST /drafts/{id}/image` is free unless it is explicitly told not to be."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()

    from app.image import hero

    def refuse(*_a, **_k):
        raise AssertionError("bought a second hero without being asked to")

    monkeypatch.setattr(hero, "generate", refuse)
    after = client.post("/drafts/1/image").json()

    assert after["hero_image_path"] == before["hero_image_path"]
    assert after["composed_image_path"] != before["composed_image_path"]


def test_asking_for_a_new_hero_buys_one(client, written, illustrated):
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()

    after = client.post("/drafts/1/image?new_hero=true").json()

    assert after["hero_image_path"] != before["hero_image_path"]


def test_a_stale_image_warning_does_not_outlive_the_fix(client, written, monkeypatch, illustrated):
    """Otherwise the row keeps complaining about a picture it now has."""
    from app.image import hero

    monkeypatch.setattr(hero, "generate", lambda *a, **k: (_ for _ in ()).throw(hero.HeroError("nope")))
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    assert any(w.startswith(generate.IMAGE_WARNING) for w in client.get("/drafts/1").json()["warnings"])

    monkeypatch.setattr(
        hero, "generate", lambda *a, **k: hero.Hero(illustrated, settings.gemini_image_model)
    )
    fixed = client.post("/drafts/1/image?new_hero=true").json()

    assert fixed["composed_image_path"]
    assert not any(warning.startswith(generate.IMAGE_WARNING) for warning in fixed["warnings"])


def test_rebuilding_replaces_image_warnings_rather_than_stacking_them(
    client, written, monkeypatch
):
    """Seen on the first real post: two identical complaints after one rebuild.

    Image warnings are regenerated every time the picture is, so the old ones
    have to go. Warnings from the writer are not this step's to delete.
    """
    from app.image import hero

    def refuse(*_a, **_k):
        raise hero.HeroError("the model returned no image")

    monkeypatch.setattr(hero, "generate", refuse)
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    first = client.get("/drafts/1").json()["warnings"]
    image_warnings = [w for w in first if w.startswith(generate.IMAGE_WARNING)]
    assert len(image_warnings) == 1, "the refusal was not reported"

    after = client.post("/drafts/1/image").json()["warnings"]

    assert [w for w in after if w.startswith(generate.IMAGE_WARNING)] == image_warnings


def test_saving_the_hook_redraws_the_composite(client, written, illustrated):
    """Recompositing was a button, so the row and the picture disagreed by default.

    The obvious thing to do after editing is save and move on, which left a PNG
    showing the previous text. Saving redraws it now.
    """
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()["composed_image_path"]

    after = client.patch("/drafts/1", json={"hook": "A different hook entirely."}).json()

    assert after["hook"] == "A different hook entirely."
    assert after["composed_image_path"] != before, "the picture still shows the old text"


def test_saving_a_highlight_redraws_the_composite(client, written, illustrated):
    """The gold is drawn, so the phrases are a drawn field too."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()["composed_image_path"]

    after = client.patch("/drafts/1", json={"highlight_phrases": ["Marie Tharp"]}).json()

    assert after["composed_image_path"] != before


def test_saving_the_caption_does_not_redraw(client, written, illustrated):
    """The caption is not on the image. Redrawing for it is work for nothing."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()["composed_image_path"]

    after = client.patch("/drafts/1", json={"caption": "🌊 A different recap."}).json()

    assert after["composed_image_path"] == before


def test_saving_the_same_hook_back_does_not_redraw(client, written, illustrated):
    """A PATCH that changes nothing is not an edit."""
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    row = client.get("/drafts/1").json()

    after = client.patch("/drafts/1", json={"hook": row["hook"]}).json()

    assert after["composed_image_path"] == row["composed_image_path"]


def test_saving_without_a_hero_does_not_fail(client, written, monkeypatch):
    """No picture to draw over is not an error — the text still saves."""
    from app.image import hero

    monkeypatch.setattr(
        hero, "generate", lambda *a, **k: (_ for _ in ()).throw(hero.HeroError("nope"))
    )
    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})

    after = client.patch("/drafts/1", json={"hook": "Saved anyway."})

    assert after.status_code == 200
    assert after.json()["hook"] == "Saved anyway."


def test_a_draft_stays_generating_until_its_image_exists(client, written, monkeypatch):
    """The row used to say "review" while the hero was still being drawn.

    `status` was set before `build_image`, so the queue showed a finished-looking
    draft with a blank thumbnail — and the client stops polling once nothing is
    `generating`, so the picture landed twenty seconds later with nothing left to
    fetch it. It never appeared until the operator reloaded.
    """
    from app.image import hero

    seen: list[str] = []

    def slow(*_a, **_k):
        # Whatever the row says at the moment the hero is being drawn is what
        # the queue would have rendered.
        seen.append(client.get("/drafts/1").json()["status"])
        raise hero.HeroError("no image today")

    monkeypatch.setattr(hero, "generate", slow)
    client.post("/generate", json={"page_ids": [1], "topic": "x"})

    assert seen == ["generating"], "the queue must not call it reviewable yet"
    assert client.get("/drafts/1").json()["status"] == "review", "and it settles after"
