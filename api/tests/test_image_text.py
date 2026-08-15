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
    assert overlay.plan(case["text"]).lines == case["lines"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_panel_and_hero_match(case):
    result = overlay.plan(case["text"])

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
    result = overlay.plan(case["text"])

    assert len(result.lines) == 6
    assert result.line_height_px == 45
    assert result.panel_height_px == 300
    assert result.hero_height_px == 820


# --- the panel is a floor that grows, not a band -----------------------------


def test_short_text_still_fills_the_minimum_panel():
    result = overlay.plan("One line only.")

    assert len(result.lines) == 1
    assert result.panel_height_px == round(layout.image.height * layout.panel.ratio)


def test_the_panel_grows_with_the_line_count():
    heights = [
        overlay.plan(" ".join(["word"] * count)).panel_height_px
        for count in (2, 40, 200)
    ]

    assert heights == sorted(heights)
    assert heights[0] < heights[-1], "the panel never grew"


def test_the_panel_stops_at_max_ratio():
    result = overlay.plan("The panel grows until it cannot grow further. " * 40)

    assert result.panel_height_px == round(layout.image.height * layout.panel.max_ratio)
    assert result.is_clipped, "text past the ceiling is drawn outside the clip path"


def test_the_font_never_shrinks_to_fit():
    """There is no autofit. The panel moves; the type does not."""
    short = overlay.plan("Two words.")
    long = overlay.plan("The panel grows until it cannot grow further. " * 40)

    assert short.font_size_px == long.font_size_px == layout.text.font_size_px


def test_the_panel_and_hero_always_add_up_to_the_image():
    for case in CASES:
        result = overlay.plan(case["text"])
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
    assert overlay.plan("   ").lines == []


# --- wrapping edge cases -----------------------------------------------------


def test_a_word_too_wide_for_a_line_is_broken_rather_than_clipped():
    """The one case wrapping cannot solve. Losing the tail silently is worse."""
    result = overlay.plan("Pneumonoultramicroscopicsilicovolcanoconiosis" * 3)

    assert len(result.lines) > 1
    assert "".join(result.lines).count("Pneumo") == 3


def test_no_line_exceeds_the_measured_width():
    """The check the safety factor exists for. A line over budget clips."""
    measurer = overlay.get_measurer(str(layout.font_file))
    budget = (
        layout.image.width - layout.text.padding.left_px - layout.text.padding.right_px
    )

    for case in CASES:
        for line in overlay.plan(case["text"]).lines:
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


# --- gold that survives a line break -----------------------------------------


def test_a_phrase_split_by_the_wrap_still_renders_gold():
    """This used to produce a warning instead of a highlight.

    Segmentation ran per line, so a phrase the wrap divided matched neither
    half and rendered nothing. It fired on three of six phrases in one real
    run — common enough to train the operator to skim a box that also carries
    the rules that matter.
    """
    case = next(c for c in CASES if c["name"] == "tharp")
    lines = case["lines"]

    # The last word of line 1 plus the first of line 2, so the phrase is cut
    # exactly at the wrap.
    tail, head = lines[0].split()[-1], lines[1].split()[0]
    spanning = f"{tail} {head}"
    coloured = overlay.segment_lines(lines, [spanning])

    gold = ["".join(p.text for p in runs if p.highlight) for runs in coloured]
    assert gold[0].endswith(tail), "the first half did not render gold"
    assert gold[1].startswith(head), "the second half did not render gold"
    assert f"{gold[0]} {gold[1]}" == spanning, "the halves do not rebuild the phrase"


def test_a_phrase_absent_from_the_text_still_renders_nothing():
    """No rendering trick fixes an invented phrase — that stays `generate.py`'s warning."""
    case = next(c for c in CASES if c["name"] == "tharp")
    coloured = overlay.segment_lines(case["lines"], ["Ada Lovelace"])

    assert not any(part.highlight for runs in coloured for part in runs)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_colouring_never_edits_the_line(case):
    """Every character survives the pass, in order. A dropped one edits the post."""
    coloured = overlay.segment_lines(case["lines"], case["phrases"])

    assert ["".join(p.text for p in runs) for runs in coloured] == case["lines"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_whole_line_colouring_agrees_with_the_old_per_line_result(case):
    """Where a phrase fits on one line, nothing changed. Only the split case moved."""
    for line, runs in zip(case["lines"], overlay.segment_lines(case["lines"], case["phrases"])):
        assert runs == overlay.segment(line, case["phrases"])


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
    assert '"girl talk."' in " ".join(overlay.plan(written).lines)


# --- capitals, per Page ------------------------------------------------------

SHOUTING = layout.model_validate(
    {**layout.model_dump(), "text": {**layout.text.model_dump(), "uppercase": True}}
)
"""`layout.yml` with `text.uppercase` on — what a Page that set it resolves to."""


def test_the_default_layout_draws_the_hook_as_it_was_written():
    """The file's answer is no. Only a Page that asked for capitals gets them."""
    assert layout.text.uppercase is False
    assert overlay.cased("Eugen Sandow") == "Eugen Sandow"


def test_capitals_are_applied_after_the_sentence_spacing_rule():
    """The trap: `_SENTENCE_END` needs two *lowercase* letters before the stop.

    Uppercase first and the rule can never fire, so `tomb.The` reaches the
    measurer as one unbroken token — wrapped as a single word, and drawn without
    the space the mixed-case card has. `plan` normalises, then shouts.
    """
    lines = overlay.plan("a sealed tomb.The pharaoh", SHOUTING).lines

    assert " ".join(lines) == "A SEALED TOMB. THE PHARAOH"
    assert "TOMB.THE" not in " ".join(lines)


def test_the_gold_lands_on_a_shouted_panel_without_shouting_the_phrases():
    """Why `panel_svg` does *not* put the phrases through `cased`.

    The writer returns phrases copied out of the hook as written. `segment`
    matches them case-insensitively and keeps the line's own casing, so they
    find their runs in a shouted panel and the gold comes back in capitals.

    The browser is the half that cannot do this — `splitOnHighlights` matches
    exactly — which is why the case transform there is applied to the text *and*
    the phrases, and why this test exists to say the two are not the same
    problem.
    """
    text = "Eugen Sandow built massive arms without a single cable machine"
    plan = overlay.plan(text, SHOUTING)

    runs = overlay.segment_lines(plan.lines, ["Eugen Sandow", "massive arms"])
    gold = [part.text for line in runs for part in line if part.highlight]

    assert gold == ["EUGEN SANDOW", "MASSIVE ARMS"]


def test_capitals_are_wider_and_the_panel_grows_to_take_them():
    """Measured, not assumed — it is what decides how much hero is left.

    Same hook, same font size: capitals wrap to more lines, and the panel is a
    floor that grows, so the hero shrinks by exactly that much.
    """
    text = (
        "According to bodybuilding pioneer Eugen Sandow, massive arms do not "
        "require modern cable machines. You can unlock rapid arm growth using "
        "three beginner exercises that bypass the cable crossover entirely."
    )
    written = overlay.plan(text)
    shouted = overlay.plan(text, SHOUTING)

    assert len(shouted.lines) >= len(written.lines)
    assert shouted.panel_height_px >= written.panel_height_px
    assert shouted.hero_height_px + shouted.panel_height_px == layout.image.height
