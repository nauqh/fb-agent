"""The run. Generate is the only thing that writes a Source Item."""

import pytest
from sqlmodel import Session, func, select

from app import generate, media
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


def test_a_redraw_takes_the_composite_it_replaced_with_it(
    client, written, illustrated, media_root
):
    """Nothing pointed at the old one, and nothing ever deleted it either.

    Every hook edit and every slider nudge writes a new composite. Seven drafts
    had left 37MB behind that way, which was untidy on a laptop and is a 1GB
    free tier in a bucket dev shares with production.
    """
    from app import media

    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()["composed_image_path"]
    assert media.store.path(before).exists()

    after = client.patch("/drafts/1", json={"hook": "A different hook entirely."}).json()

    assert not media.store.path(before).exists(), "the superseded composite is gone"
    assert media.store.path(after["composed_image_path"]).exists(), "the new one is not"


def test_the_hero_survives_a_redraw(client, written, illustrated):
    """The composite is free to remake. The hero is the one that was paid for."""
    from app import media

    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    hero_path = client.get("/drafts/1").json()["hero_image_path"]

    client.patch("/drafts/1", json={"hook": "A different hook entirely."})

    assert media.store.path(hero_path).exists()


def test_a_failed_cleanup_does_not_report_the_picture_as_broken(
    client, written, illustrated, monkeypatch
):
    """The row is committed and correct before the delete is attempted."""
    from app import media

    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    before = client.get("/drafts/1").json()["composed_image_path"]

    def refuse(_stored):
        raise media.MediaError("Supabase refused DELETE (503)")

    monkeypatch.setattr(media.store, "delete", refuse)

    after = client.patch("/drafts/1", json={"hook": "A different hook entirely."}).json()

    assert after["composed_image_path"] != before
    assert not [w for w in after["warnings"] if "MediaError" in w]


def test_the_composite_is_stored_as_jpeg(client, written, illustrated):
    """1.21MB PNG against 0.27MB JPEG, and the publish step converted it anyway."""
    from PIL import Image

    from app import media

    client.post("/generate", json={"page_ids": [1], "sources": [_rss().model_dump(mode="json")]})
    stored = media.store.path(client.get("/drafts/1").json()["composed_image_path"])

    assert stored.suffix == ".jpg"
    assert Image.open(stored).format == "JPEG"


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


def test_deleting_a_draft_takes_its_pictures_with_it(client, written, illustrated):
    """Otherwise `media/` grows with files no row can reach."""
    from app import media

    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    row = client.get("/drafts/1").json()
    files = [
        media.store.path(row["hero_image_path"]),
        media.store.path(row["composed_image_path"]),
    ]
    assert all(f.exists() for f in files)

    assert client.delete("/drafts/1").status_code == 204

    assert client.get("/drafts/1").status_code == 404
    assert not any(f.exists() for f in files), "the pictures outlived the row"


def test_a_draft_still_generating_cannot_be_deleted(client, session):
    """Its background task is still writing to the row."""
    session.add(Draft(page_id=1, status=DraftStatus.GENERATING))
    session.commit()

    assert client.delete("/drafts/1").status_code == 409


def test_deleting_something_that_is_not_there_says_so(client):
    assert client.delete("/drafts/999").status_code == 404


# --- regenerating one field --------------------------------------------------


@pytest.fixture
def rewritten(monkeypatch):
    """Stub the rewrite, and record what the writer was asked to keep.

    The prompt is the thing under test as much as the row is: a field written
    without the kept ones in front of the model is a field for a different post.
    """
    seen: dict = {}

    class Result:
        output = DraftContent(
            hook="In 1925, twenty mushers ran serum to Nome through a blizzard.",
            caption="🐕 A relay of dog teams.",
            first_comment="x" * 1850,
            highlight_phrases=["twenty mushers"],
            image_prompt="a sled dog team on sea ice",
        )

    def fake(page, source, topic, field, keeping, model=None):
        seen["field"] = field
        seen["keeping"] = keeping
        return Result()

    monkeypatch.setattr(generate.writer, "rewrite", fake)
    from app.routes import drafts as drafts_routes

    monkeypatch.setattr(drafts_routes.writer, "rewrite", fake)
    return seen


def test_regenerating_a_caption_leaves_the_other_fields_alone(
    client, written, illustrated, rewritten
):
    _generate(client)
    before = client.get("/drafts/1").json()

    after = client.post("/drafts/1/regenerate?field=caption").json()

    assert after["caption"] == "🐕 A relay of dog teams."
    assert after["hook"] == before["hook"], "the hook was overwritten"
    assert after["first_comment"] == before["first_comment"]


def test_the_kept_fields_are_shown_to_the_model(client, written, illustrated, rewritten):
    """Otherwise the new caption is a caption for a different post — it would not
    open on the hook that is drawn on the picture above it."""
    _generate(client)
    before = client.get("/drafts/1").json()

    client.post("/drafts/1/regenerate?field=caption")

    assert rewritten["field"] == "caption"
    assert set(rewritten["keeping"]) == {"hook", "first_comment"}
    assert rewritten["keeping"]["hook"] == before["hook"]


def test_a_new_hook_brings_its_highlight_phrases_with_it(
    client, written, illustrated, rewritten
):
    """They are verbatim substrings of the hook. Phrases chosen for the old one
    match nothing in the new one and render no gold at all — a silent failure
    that reads as the highlight feature being broken."""
    _generate(client)
    before = client.get("/drafts/1").json()

    after = client.post("/drafts/1/regenerate?field=hook").json()

    assert after["highlight_phrases"] == ["twenty mushers"]
    assert after["highlight_phrases"] != before["highlight_phrases"]
    assert all(p in after["hook"] for p in after["highlight_phrases"])


def test_a_new_hook_redraws_the_card(client, written, illustrated, rewritten):
    """The hook is drawn on the panel, so the stored PNG is stale without this."""
    _generate(client)
    before = client.get("/drafts/1").json()

    after = client.post("/drafts/1/regenerate?field=hook").json()

    assert after["composed_image_path"] != before["composed_image_path"]


def test_regenerating_a_caption_does_not_redraw_the_card(
    client, written, illustrated, rewritten
):
    """Nothing on the card changed, and a rebuild would orphan a file for nothing."""
    _generate(client)
    before = client.get("/drafts/1").json()

    after = client.post("/drafts/1/regenerate?field=caption").json()

    assert after["composed_image_path"] == before["composed_image_path"]


def test_a_field_that_is_not_regeneratable_is_refused(client, written, illustrated):
    _generate(client)

    assert client.post("/drafts/1/regenerate?field=hashtags").status_code == 422
    assert client.post("/drafts/1/regenerate?field=image_prompt").status_code == 422


def test_a_published_draft_cannot_be_regenerated(
    client, written, illustrated, rewritten, session
):
    """Same freeze as every other edit: Metricool holds a link to the composite."""
    _generate(client)
    draft = session.get(Draft, 1)
    draft.metricool_post_id = "queued-1"
    session.add(draft)
    session.commit()

    assert client.post("/drafts/1/regenerate?field=caption").status_code == 409


# --- the manual draft --------------------------------------------------------
#
# The old app's second generate mode: "Create a draft for {page} without calling
# Gemini". None of these use `illustrated`, so conftest's autouse guard raising
# on `hero.generate` is what proves no model was called — the same evidence the
# feed-hero tests rely on, and the whole point of the mode.


def _manual(client, **fields):
    data = {"page_id": 1, "hook": "", "caption": "", "first_comment": "", **fields}
    files = data.pop("files", None)
    return client.post("/drafts/manual", data=data, files=files)


def test_a_hand_written_draft_needs_no_model(client):
    response = _manual(
        client,
        hook="In 1925, a serum ran a thousand miles through a blizzard.",
        caption="A relay of dog sled teams saved Nome.",
        first_comment="The full story of the 1925 serum run.",
    )

    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "review", "it is ready to look at, not queued"
    assert draft["hook"].startswith("In 1925")
    assert draft["image_prompt"] is None, "nothing wrote one — there was no writer"


def test_an_uploaded_picture_becomes_the_hero_and_the_card_is_drawn(
    client, a_photograph
):
    """Not the finished post. Publishing an upload untouched would bypass the
    panel, the hook and the watermark — the whole card system."""
    response = _manual(
        client,
        hook="A hand-written hook that belongs on the panel.",
        files={"file": ("hero.png", a_photograph, "image/png")},
    )

    draft = response.json()
    assert draft["hero_image_path"], "the upload was not stored as the hero"
    assert draft["composed_image_path"], "the card was not composited around it"


def test_without_a_picture_the_draft_survives_and_says_it_has_no_card(client):
    """As the old app allowed. The text is worth keeping on its own."""
    draft = _manual(client, caption="Words now, picture later.").json()

    assert draft["composed_image_path"] is None
    assert any("no image was uploaded" in w for w in draft["warnings"]), draft["warnings"]


def test_an_entirely_empty_manual_draft_is_refused(client):
    assert _manual(client).status_code == 422


def test_a_hand_written_hook_that_breaks_a_rule_is_recorded_not_refused(client):
    """`validators.check` is the writer correcting itself. A human who types a
    question mark has decided to — so the rule is reported, never enforced."""
    draft = _manual(client, hook="Did you know about the 1925 serum run?").json()

    assert draft["status"] == "review"
    assert draft["hook"].endswith("?"), "the text was altered"
    assert draft["warnings"], "the broken rule was not recorded at all"


def test_a_manual_draft_against_a_page_that_does_not_exist_is_a_404(client):
    assert _manual(client, page_id=999, hook="x").status_code == 404


# --- the feed's own picture as the hero --------------------------------------
#
# Note what is *absent* from these: the `illustrated` fixture. The autouse guard
# in conftest makes `hero.generate` raise, so a run that finishes without it is
# proof that nothing was billed — which is the whole point of the feature, and
# not something an assertion on the row could show.


def _feed_png(monkeypatch) -> bytes:
    """Stand in for the publisher's CDN. Real bytes: the compositor opens them."""
    import io

    from PIL import Image

    from app.image import hero

    buffer = io.BytesIO()
    Image.new("RGB", (1600, 900), (90, 60, 40)).save(buffer, format="PNG")
    png = buffer.getvalue()
    monkeypatch.setattr(hero, "from_url", lambda *a, **k: png)
    return png


def test_the_feeds_picture_becomes_the_hero_and_costs_nothing(
    client, written, monkeypatch
):
    _feed_png(monkeypatch)
    source = _rss()
    source.image_url = "https://example.com/photo.jpg"

    client.post(
        "/generate",
        json={
            "page_ids": [1],
            "sources": [source.model_dump(mode="json")],
            "hero_from_source": True,
        },
    )
    draft = client.get("/drafts/1").json()

    assert draft["hero_from_source"] is True
    assert draft["hero_image_path"], "the fetched picture was not stored"
    assert draft["composed_image_path"], "the card did not compose around it"


def test_the_fetched_picture_is_stored_rather_than_hot_linked(
    client, written, monkeypatch
):
    """Metricool keeps a link and Facebook fetches it days later.

    A publisher's CDN can rotate a URL or drop the file with no notice, so the
    bytes have to be ours by the time the post is queued.
    """
    png = _feed_png(monkeypatch)
    source = _rss()
    source.image_url = "https://example.com/photo.jpg"

    client.post(
        "/generate",
        json={
            "page_ids": [1],
            "sources": [source.model_dump(mode="json")],
            "hero_from_source": True,
        },
    )
    draft = client.get("/drafts/1").json()

    assert media.store.read(draft["hero_image_path"]) == png
    assert "example.com" not in (draft["hero_image_path"] or "")


def test_a_source_with_no_picture_warns_rather_than_buying_one(client, written):
    """The operator asked for the feed's picture. Silently billing them for a
    different one is the wrong kind of helpful — and `hero.generate` raising
    here is what proves it did not happen."""
    client.post(
        "/generate",
        json={
            "page_ids": [1],
            "sources": [_rss().model_dump(mode="json")],
            "hero_from_source": True,
        },
    )
    draft = client.get("/drafts/1").json()

    assert draft["status"] == "review", "the text survived a missing picture"
    assert any("has none" in w for w in draft["warnings"]), draft["warnings"]
    assert draft["hero_image_path"] is None


def test_a_competitors_picture_is_never_reused_as_our_hero(
    client, written, session, monkeypatch
):
    """Reposting a rival page's own creative under our watermark.

    The request was for "the image provided by the RSS feed" specifically, and
    the narrow reading is also the defensible one — a feed image accompanies a
    story we are retelling, a competitor's is the thing they made.
    """
    _feed_png(monkeypatch)
    session.add(
        SourceItem(
            kind=SourceKind.COMPETITOR_POST,
            external_id="rival-1",
            image_url="https://example.com/theirs.jpg",
        )
    )
    session.commit()

    client.post(
        "/generate",
        json={
            "page_ids": [1],
            "sources": [
                {
                    "kind": "competitor_post",
                    "external_id": "rival-1",
                    "image_url": "https://example.com/theirs.jpg",
                }
            ],
            "hero_from_source": True,
        },
    )
    draft = client.get("/drafts/1").json()

    assert any("belongs to whoever published it" in w for w in draft["warnings"]), (
        draft["warnings"]
    )
    assert draft["hero_image_path"] is None


def test_a_topic_only_run_never_carries_the_flag(client, written, illustrated):
    """There is no Source Item to take a picture from, so carrying it would
    guarantee the warning above on every topic draft."""
    client.post(
        "/generate",
        json={"page_ids": [1], "topic": "The Great Molasses Flood", "hero_from_source": True},
    )

    assert client.get("/drafts/1").json()["hero_from_source"] is False


def test_a_feed_serving_html_fails_at_the_fetch(client):
    """Rather than as a broken composite twenty seconds later."""
    import httpx

    from app.image import hero

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="<html>404 not found</html>")
    )
    with httpx.Client(transport=transport) as http:
        with pytest.raises(hero.HeroError, match="not one Pillow can read"):
            hero.from_url("https://example.com/gone.jpg", client=http)


def test_a_feed_image_that_answers_an_error_is_not_treated_as_a_picture():
    import httpx

    from app.image import hero

    transport = httpx.MockTransport(lambda request: httpx.Response(403))
    with httpx.Client(transport=transport) as http:
        with pytest.raises(hero.HeroError, match="403"):
            hero.from_url("https://example.com/forbidden.jpg", client=http)


# --- the circular inset ------------------------------------------------------


def _generate(client):
    client.post("/generate", json={"page_ids": [1], "topic": "x"})
    return client.get("/drafts/1").json()


def _upload(client, data: bytes, name: str = "face.png", kind: str = "image/png"):
    return client.post("/drafts/1/inset", files={"file": (name, data, kind)})


def test_a_fresh_draft_has_no_circle(client, written, illustrated):
    """Nothing generates the inset — a run never produces one."""
    draft = _generate(client)

    assert draft["inset_image_path"] is None
    assert draft["inset_size_px"] is None
    assert draft["composed_image_path"], "the card composes without it"


def test_uploading_a_picture_puts_it_in_the_circle(client, written, illustrated, a_photograph):
    before = _generate(client)

    draft = _upload(client, a_photograph).json()

    assert draft["inset_image_path"], "the upload was not stored"
    assert draft["composed_image_path"] != before["composed_image_path"], (
        "the card was not redrawn around it"
    )


def test_the_upload_is_re_encoded_rather_than_stored_as_sent(
    client, written, illustrated, a_photograph
):
    """A JPEG in, a PNG on disk. The container the camera chose decides nothing."""
    import io

    from PIL import Image

    from app import media

    jpeg = io.BytesIO()
    Image.open(io.BytesIO(a_photograph)).convert("RGB").save(jpeg, format="JPEG")
    _generate(client)

    draft = _upload(client, jpeg.getvalue(), "face.jpg", "image/jpeg").json()

    stored = media.store.path(draft["inset_image_path"])
    assert stored.suffix == ".png"
    assert Image.open(stored).format == "PNG"


def test_a_file_that_is_not_an_image_is_refused_at_the_upload(client, written, illustrated):
    """Rather than at the composite, an hour later, as a warning on the row."""
    _generate(client)

    response = _upload(client, b"this is not a picture", "notes.txt", "text/plain")

    assert response.status_code == 422
    assert client.get("/drafts/1").json()["inset_image_path"] is None


def test_removing_the_circle_redraws_the_card(client, written, illustrated, a_photograph):
    _generate(client)
    with_circle = _upload(client, a_photograph).json()

    without = client.delete("/drafts/1/inset").json()

    assert without["inset_image_path"] is None
    assert without["composed_image_path"] != with_circle["composed_image_path"]


def test_removing_the_circle_forgets_where_it_was(
    client, written, illustrated, a_photograph
):
    """Otherwise the next upload lands wherever the last picture wanted to be."""
    _generate(client)
    _upload(client, a_photograph)
    client.patch("/drafts/1", json={"inset_size_px": 300, "inset_x_ratio": 0.2})

    client.delete("/drafts/1/inset")
    fresh = _upload(client, a_photograph).json()

    assert fresh["inset_size_px"] is None
    assert fresh["inset_x_ratio"] is None
    assert fresh["inset_y_ratio"] is None


def test_replacing_the_picture_keeps_where_it_was(
    client, written, illustrated, a_photograph
):
    """The point of Replace: a better crop of the same face, in the same place."""
    _generate(client)
    _upload(client, a_photograph)
    placed = client.patch(
        "/drafts/1", json={"inset_size_px": 300, "inset_x_ratio": 0.2, "inset_y_ratio": 0.4}
    ).json()

    replaced = _upload(client, a_photograph).json()

    assert replaced["inset_image_path"] != placed["inset_image_path"]
    assert replaced["inset_size_px"] == 300
    assert replaced["inset_x_ratio"] == 0.2
    assert replaced["inset_y_ratio"] == 0.4


# --- the inset's ring --------------------------------------------------------
#
# Per draft, over the Page's `page_layout.portrait_*`. Null means "whatever the
# Page says", which is why none of these assert against a number from
# `layout.yml` — they assert the *relationships* that a clipped or filled ring
# would break, since a wrong ring still produces a perfectly valid PNG.


def test_the_ring_is_per_draft_and_redraws_the_card(
    client, written, illustrated, a_photograph
):
    _generate(client)
    before = _upload(client, a_photograph).json()

    after = client.patch(
        "/drafts/1", json={"inset_border_width_px": 12, "inset_border_color": "#ffffff"}
    ).json()

    assert after["inset_border_width_px"] == 12
    assert after["inset_border_color"] == "#ffffff"
    assert after["composed_image_path"] != before["composed_image_path"], (
        "the ring is drawn into the composite, so changing it must redraw"
    )


def test_a_border_of_zero_draws_no_ring_rather_than_a_filled_disc(a_photograph):
    """Pillow reads `width=0` as *fill the shape*, not as "draw nothing".

    So the unguarded call paints a solid disc of the border colour straight over
    the picture — the inset survives as a flat coloured circle, which is a valid
    image and an obviously broken card. `0` is the client's own "No border"
    option, so this is the value the feature is most likely to be used with.
    """
    from app.image import compositor
    from app.settings import layout

    disc = compositor.circular_portrait(
        a_photograph, layout, size_px=200, border_width_px=0, border_color="#ff0000"
    )

    # The centre is the photograph, not the border colour. Sampling the middle
    # is enough: a filled ellipse covers it completely.
    centre = disc.convert("RGB").getpixel((disc.width // 2, disc.height // 2))
    assert centre != (255, 0, 0), "a zero-width border filled the disc"


def test_a_thick_ring_is_not_clipped_by_the_canvas(a_photograph):
    """The ring is a stroke centred on the disc edge, so half of it falls outside.

    The canvas used to be a constant `ring_pad_px: 3` larger, which was enough
    only for the file's 2px border. At the 48px maximum the overhang is 24px and
    the outer half of the ring was being cropped away — silently, in a valid
    PNG. `PortraitLayout.ring_pad` derives the padding instead.
    """
    from app.image import compositor
    from app.settings import layout

    thick = compositor.circular_portrait(
        a_photograph, layout, size_px=200, border_width_px=48, border_color="#ff0000"
    )

    assert thick.width == 200 + 48, "the canvas did not grow with the border"
    # The ring reaches the canvas edge: its outer radius is exactly half the
    # canvas. Sampling the midpoint of the top edge finds border, not blank.
    top = thick.convert("RGBA").getpixel((thick.width // 2, 1))
    assert top[3] > 0, "the outer half of the ring was clipped away"


def test_the_ring_falls_back_to_the_pages_layout(client, written, illustrated, a_photograph):
    """Null is not zero. A draft that has chosen nothing tracks the Page."""
    _generate(client)
    _upload(client, a_photograph)

    draft = client.get("/drafts/1").json()

    assert draft["inset_border_width_px"] is None
    assert draft["inset_border_color"] is None


def test_a_border_wider_than_the_maximum_is_clamped(client, written, illustrated):
    _generate(client)

    out = client.patch("/drafts/1", json={"inset_border_width_px": 900}).json()

    assert out["inset_border_width_px"] == 48


def test_a_negative_border_is_clamped_to_none_rather_than_refused(
    client, written, illustrated
):
    """A slider cannot send this; a client hand-rolling the PATCH can."""
    _generate(client)

    out = client.patch("/drafts/1", json={"inset_border_width_px": -5}).json()

    assert out["inset_border_width_px"] == 0


def test_removing_the_circle_forgets_its_ring_too(
    client, written, illustrated, a_photograph
):
    """A white ring chosen for a dark portrait is wrong for whatever replaces it."""
    _generate(client)
    _upload(client, a_photograph)
    client.patch(
        "/drafts/1", json={"inset_border_width_px": 20, "inset_border_color": "#ffffff"}
    )

    client.delete("/drafts/1/inset")
    fresh = _upload(client, a_photograph).json()

    assert fresh["inset_border_width_px"] is None
    assert fresh["inset_border_color"] is None


def test_moving_the_circle_redraws_the_card(client, written, illustrated, a_photograph):
    _generate(client)
    before = _upload(client, a_photograph).json()

    after = client.patch("/drafts/1", json={"inset_x_ratio": 0.3, "inset_y_ratio": 0.3}).json()

    assert (after["inset_x_ratio"], after["inset_y_ratio"]) == (0.3, 0.3)
    assert after["composed_image_path"] != before["composed_image_path"]


def test_a_position_off_the_card_is_clamped_to_it(client, written, illustrated):
    _generate(client)

    out = client.patch("/drafts/1", json={"inset_x_ratio": 4.0, "inset_y_ratio": -2.0}).json()

    assert (out["inset_x_ratio"], out["inset_y_ratio"]) == (1.0, 0.0)


def test_resizing_redraws_the_card(client, written, illustrated, a_photograph):
    _generate(client)
    before = _upload(client, a_photograph).json()

    after = client.patch("/drafts/1", json={"inset_size_px": 260}).json()

    assert after["inset_size_px"] == 260
    assert after["composed_image_path"] != before["composed_image_path"]


def test_a_size_outside_the_bounds_is_clamped_on_save(client, written, illustrated):
    """The row is read back into a slider, so it must not hold what it cannot draw."""
    from app.settings import layout

    _generate(client)

    assert client.patch("/drafts/1", json={"inset_size_px": 5}).json()["inset_size_px"] == (
        layout.portrait.min_px
    )
    assert client.patch("/drafts/1", json={"inset_size_px": 9000}).json()["inset_size_px"] == (
        round(layout.image.width * layout.portrait.max_width_ratio)
    )


def test_uploading_to_a_draft_still_generating_is_refused(client, session):
    session.add(Draft(page_id=1, status=DraftStatus.GENERATING))
    session.commit()

    assert _upload(client, b"anything").status_code == 409


def test_deleting_a_draft_takes_its_inset_too(client, written, illustrated, a_photograph):
    from app import media

    _generate(client)
    uploaded = media.store.path(_upload(client, a_photograph).json()["inset_image_path"])
    assert uploaded.exists()

    client.delete("/drafts/1")

    assert not uploaded.exists()


def test_the_circle_straddles_the_seam():
    """Half on the photograph, half on the panel — the whole point of it.

    Geometry is the old app's (`brand-image-layout.ts:125-140`), so this checks
    the two numbers a port gets wrong: which pixel the disc is centred on, and
    that it is a disc rather than a square.
    """
    import io

    from PIL import Image

    from app.image import compositor
    from app.image import text as overlay
    from app.settings import layout

    def png(size, colour):
        buffer = io.BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="PNG")
        return buffer.getvalue()

    plan = overlay.plan("Marie Tharp mapped the ocean floor in 1957.")
    composed = Image.open(
        io.BytesIO(
            compositor.compose(
                png((1280, 720), (40, 70, 120)),
                plan,
                [],
                None,
                compositor.Inset(png((1024, 1024), (200, 120, 40))),
            )
        )
    ).convert("RGB")

    width = layout.image.width
    margin = round(width * layout.image.edge_margin_ratio)
    ring = layout.portrait.ring_size(None, width)
    centre_x = width - margin - ring // 2

    assert composed.getpixel((centre_x, plan.hero_height_px))[0] > 150, (
        "the disc is not centred on the seam"
    )
    # Just below the seam, a ring's width to the left of the disc: panel, so
    # black. A square inset would put portrait pixels in the corner instead.
    assert composed.getpixel((centre_x - ring, plan.hero_height_px + 4)) == (0, 0, 0)


def test_a_position_puts_the_disc_where_it_was_asked_for():
    """Ratios of the whole card, as the old app stored them."""
    import io

    from PIL import Image

    from app.image import compositor
    from app.image import text as overlay
    from app.settings import layout

    def png(size, colour):
        buffer = io.BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="PNG")
        return buffer.getvalue()

    plan = overlay.plan("Marie Tharp mapped the ocean floor in 1957.")
    composed = Image.open(
        io.BytesIO(
            compositor.compose(
                png((1280, 720), (40, 70, 120)),
                plan,
                [],
                None,
                compositor.Inset(
                    png((1024, 1024), (200, 120, 40)), x_ratio=0.25, y_ratio=0.3
                ),
            )
        )
    ).convert("RGB")

    x = round(layout.image.width * 0.25)
    y = round(layout.image.height * 0.3)
    assert composed.getpixel((x, y))[0] > 150, "the disc is not where it was placed"

    # And no longer in the corner it defaults to.
    margin = round(layout.image.edge_margin_ratio * layout.image.width)
    ring = layout.portrait.ring_size(None, layout.image.width)
    corner = composed.getpixel((layout.image.width - margin - ring // 2, plan.hero_height_px))
    assert corner[0] < 150, "the disc was drawn in the default place as well"


def test_a_bigger_size_draws_a_bigger_disc():
    """The one thing the size is for. Measured, not asserted from the argument."""
    import io

    from PIL import Image

    from app.image import compositor
    from app.settings import layout

    def png(size, colour):
        buffer = io.BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="PNG")
        return buffer.getvalue()

    face = png((512, 512), (200, 120, 40))
    small = compositor.circular_portrait(face, layout, 120)
    large = compositor.circular_portrait(face, layout, 300)

    assert small.width == 120 + layout.portrait.ring_pad_px * 2
    assert large.width == 300 + layout.portrait.ring_pad_px * 2


def test_source_kind_survives_a_database_round_trip(session):
    """`is_factual` is a property on the enum, and the writer asks a *stored*
    row for it — see sources/__init__.py. Stored as a bare string it comes back
    as `str` and that call is an AttributeError mid-run.

    Regression: pinning these columns with `sa_type=String` did exactly that,
    and every existing test passed, because they all construct their rows
    rather than reloading them.
    """
    session.add(SourceItem(kind=SourceKind.RSS, external_id="round-trip", text="t"))
    session.commit()
    session.expire_all()

    stored = session.exec(
        select(SourceItem).where(SourceItem.external_id == "round-trip")
    ).one()

    assert isinstance(stored.kind, SourceKind)
    assert stored.kind.is_factual is True


# --- the card form, and a post with no picture --------------------------------


def test_a_draft_follows_the_pages_template_by_default(client, written, illustrated):
    _generate(client)

    assert client.get("/drafts/1").json()["template"] is None, (
        "null is what keeps a draft tracking the Page"
    )


def test_a_draft_can_choose_its_own_card_form(client, written, illustrated):
    """The choice depends on the picture, not on the brand — a busy photograph
    with a face low in the frame is ruined by a panel lying over it."""
    _generate(client)
    before = client.get("/drafts/1").json()

    after = client.patch("/drafts/1", json={"template": "full_overlay"}).json()

    assert after["template"] == "full_overlay"
    assert after["composed_image_path"] != before["composed_image_path"], (
        "the card was not redrawn in the other form"
    )


def test_an_unknown_template_is_refused_on_write(client, written, illustrated):
    """resvg does not fail on a bad one — it draws the wrong card and returns a
    perfectly valid PNG, so this is the only place it can be caught."""
    _generate(client)

    assert client.patch("/drafts/1", json={"template": "billboard"}).status_code == 422


def test_a_no_image_run_draws_nothing_and_warns_about_nothing(client, written):
    """No `illustrated` fixture: conftest makes `hero.generate` raise, so
    finishing without it is the proof that nothing was drawn or billed."""
    client.post("/generate", json={"page_ids": [1], "topic": "x", "no_image": True})
    draft = client.get("/drafts/1").json()

    assert draft["no_image"] is True
    assert draft["status"] == "review"
    assert draft["hero_image_path"] is None
    assert draft["composed_image_path"] is None
    assert draft["warnings"] == [], (
        "a picture left out on purpose is not a warning — that is what makes it "
        "distinguishable from one that failed"
    )


def test_a_text_only_draft_publishes_with_no_media(client, written, session, monkeypatch):
    """A draft whose image *failed* must still be refused; this one is deliberate."""
    from app.publish import metricool as publisher

    sent = {}

    def fake_schedule(blog_id, text, first_comment, image_url, when=None, client=None):
        sent["image_url"] = image_url
        return "queued-text"

    monkeypatch.setattr(publisher, "schedule", fake_schedule)
    monkeypatch.setattr(
        publisher, "normalize_image", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("normalize was called for a post with no image")
        )
    )
    client.post("/generate", json={"page_ids": [1], "topic": "x", "no_image": True})

    published = client.post("/drafts/1/publish", json={}).json()

    assert published["metricool_post_id"] == "queued-text"
    assert sent["image_url"] is None


def test_the_payload_omits_media_entirely_when_there_is_no_picture():
    """Not `[]` and not `[null]`: both are a media field Metricool then has to
    interpret. A Facebook status update is a post with no attachment."""
    from app.publish import metricool as publisher

    body = publisher.build_body("text", None, None)

    assert "media" not in body
    assert body["providers"][0]["facebookData"]["type"] == "POST"


def test_a_draft_whose_picture_failed_still_cannot_publish(client, written, illustrated, session):
    """The difference `no_image` exists to draw. Both have no composite."""
    _generate(client)
    draft = session.get(Draft, 1)
    draft.composed_image_path = None
    session.add(draft)
    session.commit()

    response = client.post("/drafts/1/publish", json={})

    assert response.status_code == 409
    assert "nothing to post" in response.json()["detail"]
