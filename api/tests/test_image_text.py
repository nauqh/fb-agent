"""Wrapping, panel height and highlight runs. No network, no rasteriser, no spend.

The bulk of this file is a **parity suite**: `fixtures/overlay_parity.json` was
produced by running the old repo's own `planOverlayLayout` and
`segmentTextWithHighlights` at this repo's `layout.yml` values, through
opentype.js and the same `Arial-Bold.ttf`. Every line break, panel height and
gold run in it is the TypeScript implementation's answer, not one we chose.

That is what makes the port checkable. The measurement half was already proven
in Phase 0 — `fontTools` reproduces `getAdvanceWidth` to four decimal places —
but a matching measurer still wraps differently if the safety factor, the space
handling or the panel arithmetic is off by a hair, and the symptom is a picture
that is subtly wrong rather than a test that fails.

`six-lines` is the case plan.md records: 6 lines, 45px line height, a 300px
panel over an 820px hero, matching a real History Retraced post.
"""

import json
from pathlib import Path

import pytest

from app.image import text as overlay
from app.settings import layout

FIXTURE = Path(__file__).parent / "fixtures" / "overlay_parity.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
IDS = [case["name"] for case in CASES]


# --- parity with the implementation being replaced ---------------------------


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_lines_break_where_the_old_renderer_broke_them(case):
    """Word for word. A line count that differs resizes the panel."""
    assert overlay.plan(case["text"], case["phrases"]).lines == case["lines"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_panel_and_hero_match(case):
    result = overlay.plan(case["text"], case["phrases"])

    assert result.line_height_px == case["lineHeight"]
    assert result.panel_height_px == case["panelHeight"]
    assert result.hero_height_px == case["heroHeight"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_gold_falls_on_the_same_characters(case):
    got = [
        [[part.text, part.highlight] for part in overlay.segment(line, case["phrases"])]
        for line in case["lines"]
    ]

    assert got == case["segments"]


def test_the_golden_post_reproduces_its_own_geometry():
    """plan.md's recorded numbers, asserted directly rather than by index."""
    case = next(c for c in CASES if c["name"] == "six-lines")
    result = overlay.plan(case["text"], case["phrases"])

    assert len(result.lines) == 6
    assert result.line_height_px == 45
    assert result.panel_height_px == 300
    assert result.hero_height_px == 820


# --- the panel is a floor that grows, not a band -----------------------------


def test_short_text_still_fills_the_minimum_panel():
    result = overlay.plan("One line only.", [])

    assert len(result.lines) == 1
    assert result.panel_height_px == round(layout.image.height * layout.panel.ratio)


def test_the_panel_grows_with_the_line_count():
    heights = [
        overlay.plan(" ".join(["word"] * count), []).panel_height_px
        for count in (2, 40, 200)
    ]

    assert heights == sorted(heights)
    assert heights[0] < heights[-1], "the panel never grew"


def test_the_panel_stops_at_max_ratio():
    result = overlay.plan("The panel grows until it cannot grow further. " * 40, [])

    assert result.panel_height_px == round(layout.image.height * layout.panel.max_ratio)
    assert result.is_clipped, "text past the ceiling is drawn outside the clip path"


def test_the_font_never_shrinks_to_fit():
    """There is no autofit. The panel moves; the type does not."""
    short = overlay.plan("Two words.", [])
    long = overlay.plan("The panel grows until it cannot grow further. " * 40, [])

    assert short.font_size_px == long.font_size_px == layout.text.font_size_px


def test_the_panel_and_hero_always_add_up_to_the_image():
    for case in CASES:
        result = overlay.plan(case["text"], case["phrases"])
        assert result.panel_height_px + result.hero_height_px == layout.image.height


# --- measurement ------------------------------------------------------------


def test_kerning_is_applied():
    """Without it `AVATAR` measures 10.69px too wide and wraps a line early.

    Phase 0 traced that to Arial's AV/VA/AT/TA pairs at -152 units over a 2048
    em. The number here is opentype.js's, so this fails if the `kern` table
    stops being read.
    """
    measurer = overlay.get_measurer(str(layout.font_file))

    assert measurer.width("AVATAR", 36) == pytest.approx(139.3066, abs=0.01)


def test_the_measurer_is_reused_across_calls():
    """Re-parsing the TTF per draft would be the slow part of the composite."""
    first = overlay.get_measurer(str(layout.font_file))

    assert overlay.get_measurer(str(layout.font_file)) is first


def test_an_empty_overlay_produces_no_lines():
    assert overlay.plan("   ", []).lines == []


# --- wrapping edge cases -----------------------------------------------------


def test_a_word_too_wide_for_a_line_is_broken_rather_than_clipped():
    """The one case wrapping cannot solve. Losing the tail silently is worse."""
    result = overlay.plan("Pneumonoultramicroscopicsilicovolcanoconiosis" * 3, [])

    assert len(result.lines) > 1
    assert "".join(result.lines).count("Pneumo") == 3


def test_no_line_exceeds_the_measured_width():
    """The check the safety factor exists for. A line over budget clips."""
    measurer = overlay.get_measurer(str(layout.font_file))
    budget = (
        layout.image.width - layout.text.padding.left_px - layout.text.padding.right_px
    )

    for case in CASES:
        for line in overlay.plan(case["text"], case["phrases"]).lines:
            assert measurer.width(line, layout.text.font_size_px) <= budget


# --- normalising, which the port did in the wrong order ----------------------


def test_punctuation_spacing_is_fixed_before_the_text_is_measured():
    """The port normalised each line *after* wrapping it.

    Any rule that lengthens a line — `tomb.The` gaining a space — then widened a
    line that had already been measured to fit. Measuring the normalised string
    is what keeps the drawn text and the measured text the same string.
    """
    assert overlay.normalise("a sealed tomb.The pharaoh") == "a sealed tomb. The pharaoh"
    assert overlay.normalise("the tomb ,opened") == "the tomb, opened"
    assert overlay.normalise("Egypt( 1923 )") == "Egypt (1923)"


@pytest.mark.parametrize("intact", ["the U.S. Navy", "fossils, e.g. trilobites"])
def test_an_abbreviation_is_not_split_into_sentences(intact):
    """The port's bare `\\.([A-Za-z])` turned `U.S.` into `U. S.`.

    Not hypothetical on a history page. The lookbehind wants two lowercase
    letters before the period, which every abbreviation of this shape fails.
    """
    assert overlay.normalise(intact) == intact


def test_a_thousands_separator_survives():
    """`2,000-year-old` is in the sample overlay text; a space there breaks it."""
    assert "2,000-year-old" in overlay.normalise("This 2,000-year-old Lighthouse")


def test_manual_line_breaks_become_one_flowing_paragraph():
    """Wrapping owns the line breaks. A newline in the overlay is not one."""
    assert overlay.normalise("Marie Tharp\nmapped\n\nthe floor") == (
        "Marie Tharp mapped the floor"
    )


# --- highlights --------------------------------------------------------------


def test_the_longest_phrase_wins_where_two_overlap():
    """Otherwise `ocean` consumes the prefix and leaves `floor` white."""
    segments = overlay.segment("The ocean floor is deep", ["ocean", "ocean floor"])
    gold = [part.text for part in segments if part.highlight]

    assert gold == ["ocean floor"]


def test_adjacent_runs_of_the_same_colour_become_one():
    segments = overlay.segment("ocean floor", ["ocean", "floor"])

    assert [part.highlight for part in segments] == [True, False, True]


def test_a_phrase_keeps_the_line_s_own_casing():
    """Matching is case-insensitive; the drawn text is never the phrase's."""
    segments = overlay.segment("MARIE THARP mapped it", ["marie tharp"])

    assert segments[0].text == "MARIE THARP"


def test_no_phrases_leaves_the_line_in_one_piece():
    assert overlay.segment("Nothing gold here", []) == [
        overlay.Segment("Nothing gold here", False)
    ]


def test_segments_always_rebuild_the_line_exactly():
    """A segmenter that drops a character silently edits the finished post."""
    for case in CASES:
        for line in case["lines"]:
            parts = overlay.segment(line, case["phrases"])
            assert "".join(part.text for part in parts) == line


def test_a_phrase_split_by_the_wrap_is_reported():
    """The other way to lose the gold, and the one nothing else catches.

    `generate.py` warns when a phrase is not verbatim in the hook. A
    phrase that *is* verbatim can still land across a line break, and because
    segmentation runs per line it then matches nothing and renders no gold —
    visible only by looking at the picture.
    """
    case = next(c for c in CASES if c["name"] == "tharp")
    text, lines = case["text"], case["lines"]

    # "1957 and was" spans the break between line 1 and line 2.
    spanning = " ".join([lines[0].split()[-1], lines[1].split()[0]])
    assert spanning in overlay.normalise(text)

    assert overlay.split_by_wrap(text, lines, [spanning]) == [spanning]
    assert overlay.split_by_wrap(text, lines, ["Marie Tharp"]) == []


def test_a_phrase_absent_from_the_overlay_is_not_blamed_on_the_wrap():
    """That one is `generate.py`'s warning. Reporting it twice hides the real one."""
    case = next(c for c in CASES if c["name"] == "tharp")

    assert overlay.split_by_wrap(case["text"], case["lines"], ["Ada Lovelace"]) == []


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_fixture_s_own_phrases_all_survive_the_wrap(case):
    """A parity case that lost a highlight would be testing the wrong thing."""
    result = overlay.plan(case["text"], case["phrases"])

    assert result.lost_highlights == []


def test_a_quoted_phrase_keeps_the_space_in_front_of_it():
    """Caught on the first real post: `dismissed it as mere"girl talk."`

    The port closed the gap before an opening quote as well as after it — its
    own comment gives `the "Seven` -> `the"Seven`. Only the second half was
    ever right, so only the second half is here.
    """
    written = (
        'her male colleague dismissed her breakthrough as mere "girl talk." It '
        "took years for the community to admit she had rewritten plate tectonics."
    )

    assert overlay.normalise(written) == written
    assert '"girl talk."' in " ".join(overlay.plan(written, []).lines)
