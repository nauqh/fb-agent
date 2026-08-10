"""The layout screen's routes: the overrides, and the sample card.

`POST /layout/sample` exists because the editor's live preview is CSS. That
preview is an approximation and says so; these tests are about the other half,
where the answer comes back from the same `text.plan` and `compositor.compose`
that publish. Two things it must never do — bill for a hero, or write a row —
are asserted here rather than left to the reading.
"""

import base64
import io

from PIL import Image
from sqlmodel import select

from app import media
from app.models import Draft, DraftStatus, PageLayout

SAMPLE = "In 1925, a deadly outbreak threatened to wipe out isolated Nome, Alaska."


def _with_hero(session, page, photograph: bytes) -> Draft:
    """A draft carrying a real, decodable hero. The compositor opens these."""
    draft = Draft(
        page_id=page.id,
        status=DraftStatus.APPROVED,
        hook="Whatever this draft's own hook is — the sample supplies its own.",
        hero_image_path=media.store.save(photograph, "7-hero.png"),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def test_the_sample_is_a_real_composite_at_the_card_size(
    client, session, page, a_photograph
):
    _with_hero(session, page, a_photograph)

    response = client.post(
        "/layout/sample",
        params={"page_id": page.id},
        json={"text": SAMPLE, "highlight_phrases": ["deadly outbreak"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    image = Image.open(io.BytesIO(base64.b64decode(body["image_base64"])))
    assert image.format == "JPEG", "the publish path's format, not a PNG preview"
    assert image.size == (896, 1120)
    assert body["lines"], "the wrap is reported so the browser can stop guessing"
    assert " ".join(body["lines"]).startswith("In 1925")


def test_the_sample_draws_the_unsaved_patch_and_saves_nothing(
    client, session, page, a_photograph
):
    """The whole point: values that are not in the database yet.

    A preview that could only draw saved values would need a save to try a
    colour, which is the round trip this route exists to remove.
    """
    _with_hero(session, page, a_photograph)

    response = client.post(
        "/layout/sample",
        params={"page_id": page.id},
        json={"text": SAMPLE, "patch": {"panel_ratio": 0.5}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["panel_height_px"] == 560, "0.5 × 1120, from the patch"
    assert session.exec(select(PageLayout)).first() is None, "the patch was stored"
    assert client.get("/layout", params={"page_id": page.id}).json()["overridden"] == []


def test_a_page_with_no_hero_anywhere_is_refused_rather_than_drawn(
    client, session, page
):
    """`never_buy_an_image` is autouse, so a route that generated would fail here.

    The refusal is the design: `hero.generate` bills per call, and a preview
    button that spends money on every press is one nobody presses twice.
    """
    response = client.post(
        "/layout/sample", params={"page_id": page.id}, json={"text": SAMPLE}
    )

    assert response.status_code == 409
    assert "hero" in response.json()["detail"]


def test_a_named_draft_supplies_the_hero_when_one_is_asked_for(
    client, session, page, a_photograph
):
    older = _with_hero(session, page, a_photograph)
    _with_hero(session, page, a_photograph)

    newest = client.post(
        "/layout/sample", params={"page_id": page.id}, json={"text": SAMPLE}
    )
    named = client.post(
        "/layout/sample",
        params={"page_id": page.id},
        json={"text": SAMPLE, "draft_id": older.id},
    )

    assert newest.json()["hero_draft_id"] != older.id, "the default is the newest"
    assert named.json()["hero_draft_id"] == older.id


def test_alignment_moves_the_anchor_rather_than_being_ignored():
    """`text-anchor` was hardcoded to the centre while `align` was a control.

    SVG has no `text-align`: the anchor *is* the alignment, and it only means
    anything paired with the x it hangs from. Left-aligned text anchored
    "start" at the centre x starts halfway across the card.
    """
    from app.image import compositor, text as overlay
    from app.settings import Layout, layout as defaults

    def aligned(align: str) -> str:
        values = defaults.model_dump()
        values["text"]["align"] = align
        layout = Layout.model_validate(values)
        return compositor.panel_svg(overlay.plan(SAMPLE, layout), [], layout)

    assert 'text-anchor="start"' in aligned("left")
    assert 'x="5"' in aligned("left"), "the left padding, not the centre"
    assert 'text-anchor="end"' in aligned("right")
    assert 'x="891"' in aligned("right"), "the width less the right padding"
    assert 'text-anchor="middle"' in aligned("center")


def _templated(template: str, panel_opacity: float | None = None):
    """The file's layout as one of the two card forms."""
    from app.settings import Layout, layout as defaults

    values = defaults.model_dump()
    values["template"] = template
    if panel_opacity is not None:
        values["panel"]["opacity"] = panel_opacity
    return Layout.model_validate(values)


def _drawn(layout, badge_text=None) -> "Image.Image":
    from app.image import compositor, text as overlay

    hero = io.BytesIO()
    Image.new("RGB", (1280, 1600), (200, 40, 40)).save(hero, format="PNG")
    plan = overlay.plan(SAMPLE, layout)
    jpeg = compositor.compose(
        hero.getvalue(), plan, [], None, None, layout, badge_text=badge_text
    )
    return Image.open(io.BytesIO(jpeg)).convert("RGB")


def test_a_full_overlay_puts_the_photograph_behind_the_panel():
    """The panel is at the same height either way. What changes is what is under
    it: on a `card` nothing, on a `full_overlay` the hero.

    Read at 50% opacity, because an opaque panel is black on both and would
    pass this test while drawing no photograph at all.
    """
    card = _drawn(_templated("card", panel_opacity=0.5))
    full = _drawn(_templated("full_overlay", panel_opacity=0.5))

    # Well inside the panel, which starts at 80% of the height by default.
    probe = (448, 1080)
    assert card.getpixel(probe) == (0, 0, 0), "a card's panel has only black under it"
    assert full.getpixel(probe)[0] > 40, "the hero is not showing through the panel"


def test_the_badge_is_a_full_overlay_thing_only():
    """On a card the panel begins exactly where the badge would sit."""
    layout = _templated("full_overlay", panel_opacity=0.5)

    assert _drawn(layout, badge_text="NEWS") != _drawn(layout), "no badge was drawn"

    card = _templated("card")
    assert _drawn(card, badge_text="NEWS") == _drawn(card), "a card drew a badge"


def test_the_badge_is_measured_rather_than_estimated():
    """The old file guessed `chars × fontSize × 0.62` plus a 0.35em margin.

    We read the same TTF resvg draws with, so the chip fits its word. The
    radius is clamped to half the height, past which resvg draws a stadium
    where the CSS preview drew a rounded rectangle.
    """
    from app.image import compositor
    from app.settings import layout as defaults

    svg, width, height = compositor.badge_svg("news", defaults)

    assert ">NEWS<" in svg, "the label is upper-cased, as the old app's was"
    assert height == 22 + 8 * 2

    # `chars × fontSize × 0.62 + 0.35em`, the old estimate, against the advance
    # widths of the real face. It comes out *narrow* on this label — the chip
    # was 4px tighter than its own word, so the 18px padding it claimed was
    # nearer 16 on each side.
    estimate = round(len("NEWS") * 22 * 0.62 + 22 * 0.35) + 18 * 2
    assert width > estimate, "still using the old estimate"
    assert width - estimate < 10, "and not wildly apart — it was an estimate, not a bug"
    assert 'rx="19"' in svg, "half the height, not the configured 24"


def test_a_template_that_is_not_one_is_refused(client, session, page, a_photograph):
    _with_hero(session, page, a_photograph)

    assert (
        client.patch(
            "/layout", params={"page_id": page.id}, json={"template": "carousel"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/layout", params={"page_id": page.id}, json={"template": "full_overlay"}
        ).status_code
        == 200
    )
    assert client.get("/layout", params={"page_id": page.id}).json()["layout"][
        "template"
    ] == "full_overlay"


def test_an_alignment_that_is_not_one_is_refused_by_both_routes(
    client, session, page, a_photograph
):
    """`text_align` was a bare `str`, so `"sideways"` stored and answered 200.

    The write is validated by building the `Layout` it would produce, which
    means anything that model accepts reaches the compositor — where an
    unknown anchor does not raise, it draws the text somewhere else.
    """
    _with_hero(session, page, a_photograph)

    stored = client.patch(
        "/layout", params={"page_id": page.id}, json={"text_align": "sideways"}
    )
    sampled = client.post(
        "/layout/sample",
        params={"page_id": page.id},
        json={"text": SAMPLE, "patch": {"text_align": "sideways"}},
    )

    assert stored.status_code == 422
    assert sampled.status_code == 422
    assert session.exec(select(PageLayout)).first() is None, "nothing was written"
    assert (
        client.patch(
            "/layout", params={"page_id": page.id}, json={"text_align": "right"}
        ).status_code
        == 200
    )
