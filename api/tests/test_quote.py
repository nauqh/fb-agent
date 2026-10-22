"""The quote card: a hook drawn as type, with no picture bought for it."""

import io

import pytest
import resvg_py
from PIL import Image
from sqlmodel import Session

from app import generate
from app.image import quote
from app.image.compositor import CompositeError
from app.image.text import get_measurer
from app.models import Draft, DraftStatus
from app.settings import API_DIR, layout
from app.writer import agent as writer
from app.writer.agent import DraftContent

PSALM = (
    "Psalm 94:19\n"
    "God says, “I see how stressed you are. Don’t let anything steal your "
    "peace today. Leave everything to Me.”"
)
EMPHASIS = ["Don’t let anything steal your peace today"]


def _card(jpeg: bytes) -> Image.Image:
    return Image.open(io.BytesIO(jpeg)).convert("RGB")


def test_the_first_line_is_the_heading_only_when_there_is_a_second():
    assert quote.split(PSALM)[0] == "Psalm 94:19"
    assert quote.split("Be still.") == (None, "Be still.")


def test_a_verse_reference_keeps_its_colon_tight():
    """`text.normalise` spaces every colon, which reads "94: 19"."""
    assert quote.plan(PSALM, EMPHASIS, layout).heading == ["PSALM 94:19"]


def test_an_emphasised_line_fits_in_the_face_it_is_drawn_in():
    """Bold italic runs wider. Measured in the regular face alone, a line full of
    emphasis would wrap late and run past the margin."""
    q = layout.quote
    regular = get_measurer(str(API_DIR / q.font_path))
    emphasis = get_measurer(str(API_DIR / q.emphasis_path))
    text = "Don’t let anything steal your peace today, whatever tomorrow holds for you."
    available = layout.image.width * (1 - q.margin_ratio * 2)

    lines = quote.wrap_runs(text, [text], available, q.body_px, regular, emphasis)

    assert len(lines) > 1
    for line in lines:
        drawn = sum(
            (emphasis if part.highlight else regular).width(part.text, q.body_px)
            for part in line
        )
        assert drawn <= available


@pytest.mark.parametrize("path, weight, style", [
    (layout.quote.font_path, "normal", "normal"),
    (layout.quote.emphasis_path, "bold", "italic"),
])
def test_both_quote_faces_render_as_themselves(path, weight, style):
    """resvg substitutes silently, the trap `test_layout` guards for the card fonts."""

    def ink(family: str) -> bytes:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="80">'
            f'<text x="0" y="60" font-family="{family}" font-weight="{weight}" '
            f'font-style="{style}" font-size="40">Leave everything to Me.</text></svg>'
        )
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, font_files=[str(API_DIR / path)]))

    assert ink(layout.quote.font_family) != ink("No Such Face")


def test_a_quote_card_is_the_card_size_and_dark():
    card = _card(quote.compose(PSALM, EMPHASIS, None, layout, "Golden Years"))

    assert card.size == (layout.image.width, layout.image.height)
    assert max(card.getpixel((10, 10))) < 60, "the corner is the dark ground"


def test_a_quote_too_long_for_the_card_is_refused_rather_than_cut():
    with pytest.raises(CompositeError, match="shorten"):
        quote.plan("Heading\n" + "Peace be with you always. " * 60, [], layout)


def test_the_writer_is_told_the_quote_shape_and_drops_the_first_comment(page):
    instructions = writer._instructions(page, layout, quote=True)

    assert "QUOTE CARD" in instructions
    assert "NO FIRST COMMENT" in instructions
    assert "QUOTE CARD" not in writer._instructions(page, layout)


def test_a_hand_written_quote_draft_is_drawn_without_any_picture(client):
    """`never_buy_an_image` is autouse, so a hero call here fails the test."""
    response = client.post(
        "/drafts/manual",
        data={
            "page_id": "1",
            "hook": PSALM,
            "highlight_phrases": EMPHASIS,
            "caption": "Allow yourself to enjoy the peace today.",
            "template": "quote",
        },
    )

    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["template"] == "quote"
    assert draft["composed_image_path"], "the card was drawn"
    assert draft["hero_image_path"] is None
    assert draft["warnings"] == []


def test_a_quote_run_buys_no_hero_and_tells_the_writer(client, monkeypatch):
    seen = {}

    class Result:
        output = DraftContent(
            hook=PSALM,
            caption="Allow yourself to enjoy the peace today.",
            highlight_phrases=EMPHASIS,
            image_prompt="",
        )

    def write(*_args, **kwargs):
        seen.update(kwargs)
        return Result()

    monkeypatch.setattr(generate.writer, "write", write)

    response = client.post(
        "/generate",
        json={"page_ids": [1], "topic": "peace", "template": "quote", "find_inset": True},
    )
    draft = client.get(f"/drafts/{response.json()[0]}").json()

    assert seen["quote"] is True
    assert draft["status"] == "review"
    assert draft["composed_image_path"] and draft["hero_image_path"] is None
    assert draft["find_inset"] is False, "a quote card has no circle to fill"


def test_switching_off_a_quote_card_with_no_hero_takes_the_card_down(client):
    """Otherwise the quote card would publish under a form that needs a photo."""
    client.post(
        "/drafts/manual",
        data={"page_id": "1", "hook": PSALM, "template": "quote"},
    )

    card = client.patch("/drafts/1", json={"template": "card"}).json()

    assert card["composed_image_path"] is None
    assert any("no hero" in warning for warning in card["warnings"])

    back = client.patch("/drafts/1", json={"template": "quote"}).json()
    assert back["composed_image_path"], "a quote card needs no hero to redraw"


def test_editing_a_quote_cards_text_redraws_it(client, engine):
    client.post(
        "/drafts/manual",
        data={"page_id": "1", "hook": PSALM, "template": "quote"},
    )
    before = client.get("/drafts/1").json()["composed_image_path"]

    after = client.patch("/drafts/1", json={"hook": "Courage\nBe strong."}).json()

    assert after["composed_image_path"] != before
    with Session(engine) as session:
        assert session.get(Draft, 1).status == DraftStatus.REVIEW
