"""The prompt-template library: named post styles, deltas only.

The client's 2026-08-20 request. The rules the tests pin are the ones the
feature could silently lose: blank inherits (deltas, never copies), a name is
required, an all-blank template is refused, and deleting one must not strand
the drafts generated under it.
"""

import pytest
from sqlmodel import select

from app import generate
from app.models import PromptTemplate


@pytest.fixture
def written(monkeypatch):
    """Stub the writer, as `test_generate` does - the CRUD is not about runs."""

    class Result:
        output = generate.writer.DraftContent(
            hook="h",
            caption="c",
            first_comment="x" * 1850,
            highlight_phrases=[],
            image_prompt="i",
        )

    monkeypatch.setattr(generate.writer, "write", lambda *a, **k: Result())
    return Result

BODY = {
    "name": "Meme",
    "page_id": 1,
    "system_prompt": "One image, one line. No essay.",
    "overlay_prompt": None,
    "image_prompt": None,
}


def _create(client, **overrides):
    return client.post("/prompts/templates", json={**BODY, **overrides})


def test_a_template_is_created_and_listed(client):
    assert _create(client).status_code == 201

    templates = client.get("/prompts/templates").json()
    assert [t["name"] for t in templates] == ["Meme"]
    assert templates[0]["system_prompt"] == BODY["system_prompt"]


def test_a_template_can_be_updated(client, session):
    [row] = client.get("/prompts/templates").json() or [None]
    assert row is None, "the list starts empty"

    created = _create(client).json()
    response = client.put(
        f"/prompts/templates/{created['id']}",
        json={
            "name": "Quote",
            "page_id": 1,
            "system_prompt": "New text.",
            "image_prompt": "x",
        },
    )

    assert response.status_code == 200
    stored = session.exec(select(PromptTemplate)).one()
    assert (stored.name, stored.system_prompt, stored.overlay_prompt) == (
        "Quote",
        "New text.",
        None,
    ), "a field sent back blank clears, it does not keep the old text"


def test_an_all_blank_template_is_refused(client):
    """A template that changes nothing is a dropdown entry, not a style."""
    response = _create(client, system_prompt="", overlay_prompt=None, image_prompt="  ")

    assert response.status_code == 422


def test_no_overlay_text_is_a_style_of_its_own(client, session):
    """The client's 2026-09-14 report: a style for image-only posts still came
    out with a panel, because its empty Overlay box meant "use the Page's". `""`
    is the explicit "no overlay text" and survives the round trip; `None` is still
    "use the Page's" and is not a change on its own."""
    assert _create(client, system_prompt=None, overlay_prompt="").status_code == 201
    assert session.exec(select(PromptTemplate)).one().overlay_prompt == ""

    assert (
        _create(client, name="Blank", system_prompt=None, overlay_prompt=None).status_code
        == 422
    )


def test_an_update_keeps_no_overlay_distinct_from_inherit(client, session):
    created = _create(client).json()
    url = f"/prompts/templates/{created['id']}"

    client.put(url, json={**BODY, "overlay_prompt": "  "})
    assert session.exec(select(PromptTemplate)).one().overlay_prompt == ""

    client.put(url, json={**BODY, "overlay_prompt": None})
    session.expire_all()
    assert session.exec(select(PromptTemplate)).one().overlay_prompt is None


def test_a_name_is_required_and_unique(client):
    assert _create(client, name="  ").status_code == 422
    assert _create(client).status_code == 201
    assert _create(client).status_code == 409
    # Renaming another template onto the taken name is the same clash.
    second = _create(client, name="Second").json()
    assert client.put(
        f"/prompts/templates/{second['id']}", json={**BODY, "name": "Meme"}
    ).status_code == 409


def test_deleting_a_template_unpins_its_drafts(client, session, written):
    """A dangling id would fail the next rewrite on a lookup no screen can fix."""
    created = _create(client).json()
    [draft_id] = client.post(
        "/generate",
        json={"page_ids": [1], "topic": "x", "prompt_template_id": created["id"]},
    ).json()

    assert client.delete(f"/prompts/templates/{created['id']}").status_code == 204

    assert client.get(f"/drafts/{draft_id}").json()["prompt_template_id"] is None


def test_a_template_belongs_to_its_page_only(client):
    """The client's 2026-09-11 report: History Retraced was offered
    Bodybuilding's Workout Infographic through the null-global contract. A
    style is one Page's; another Page's list does not have it, and a style
    without a Page cannot exist at all."""
    _create(client, page_id=1)

    assert [t["name"] for t in client.get("/prompts/templates?page_id=1").json()] == [
        "Meme"
    ]
    assert client.get("/prompts/templates?page_id=2").json() == []
    assert _create(client, page_id=None).status_code == 422


def test_preview_shows_the_page_prompt_with_the_style_layered_on(client):
    """The Settings preview: the string a run would send, not a reassembly.

    The operator writes a style as a delta against the Page's prompts, so the
    preview has to contain *both* - the inherited text and their own, in the
    order the model reads them. A preview that showed only the delta would
    leave them guessing exactly as before.
    """
    body = {
        "name": "Meme",
        "page_id": 1,
        "system_prompt": "One line. No essay.",
        "overlay_prompt": None,
        "image_prompt": "Flat studio light.",
    }
    preview = client.post("/prompts/templates/preview", json=body).json()

    writer = preview["writer"]
    # The Page's own prompt is there, ahead of the style, and the style says it
    # wins - that ordering is the whole contract being previewed.
    assert writer.index("You are writing for the Facebook page") < writer.index(
        "POST STYLE: Meme"
    )
    assert "One line. No essay." in writer
    assert "outrank" in writer

    # The image layer goes to the other model, and only there.
    assert "Flat studio light." not in writer
    assert "Flat studio light." in preview["hero"]

    # An unsaved style previews; nothing was written.
    assert client.get("/prompts/templates?page_id=1").json() == []


def test_preview_matches_what_the_run_actually_sends(client, session):
    """The one property worth pinning: the preview is the same function the
    run calls, so it cannot drift from the request the model gets."""
    from app.image import hero
    from app.models import Page
    from app.settings import layout
    from app.writer import agent

    body = {
        "name": "Meme",
        "page_id": 1,
        "system_prompt": "One line.",
        "overlay_prompt": None,
        "image_prompt": "Flat light.",
    }
    preview = client.post("/prompts/templates/preview", json=body).json()

    page = session.get(Page, 1)
    style = PromptTemplate(**body)
    assert preview["writer"] == agent.instructions_for(page, style)
    assert preview["hero"] == hero.brief(layout, page.name, page, "Flat light.")
