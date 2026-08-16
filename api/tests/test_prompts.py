"""Per-Page prompt files: `prompts/pages/<slug>/` overriding `prompts/*.txt`.

These read the committed prompts rather than fixtures. That is deliberate — the
defect being guarded is not "the resolver has a bug", it is "a Page is quietly
sent History Retraced's brief", which only the real files can show.
"""

import pytest
from sqlmodel import Session

from app.models import Page
from app.settings import layout
from app.writer import prompts

FITNESS = "Fitness Recipes"
BODYBUILDING = "Bodybuilding Tips N Tricks"


def test_a_page_with_no_directory_of_its_own_reads_the_global_files():
    """The fallback is the common case: eight of the ten Pages have no files."""
    assert prompts.system_prompt(layout, "History Retraced") == prompts.system_prompt(
        layout
    )
    assert prompts.image_prompt(layout, "Nobody's Page") == prompts.image_prompt(layout)


def test_the_slug_is_the_watermark_convention():
    assert prompts.slug(BODYBUILDING) == "bodybuilding-tips-n-tricks"
    assert prompts.slug("The Fact Feed") == "the-fact-feed"
    assert prompts.slug("GYM Motivation | quotes | videos | tips|") == (
        "gym-motivation-quotes-videos-tips"
    )


@pytest.mark.parametrize("page_name", [FITNESS, BODYBUILDING])
def test_the_two_fitness_pages_have_all_three_prompts_of_their_own(page_name):
    """All three, or none. A directory holding two of them is the worst case.

    It looks configured, it reads as configured on the Settings screen for the
    files that are there, and the third silently comes from History Retraced —
    which is precisely the failure the client lived with for six weeks in the
    old tool.
    """
    for name in prompts.ORDER:
        resolved = prompts.source_of(name, page_name)
        assert resolved.parent.name == prompts.slug(page_name), (
            f"{page_name} falls back to the global {name}"
        )


@pytest.mark.parametrize("page_name", [FITNESS, BODYBUILDING])
def test_the_hero_brief_is_bright_and_modern_not_a_history_photograph(page_name):
    """C5. The client's word was "sepia"; the prompt's words were these.

    Split on the NEVER block rather than searching the whole file: these prompts
    *do* say "reenactment" and "sepia", in the list of things to avoid. A naive
    substring search over the whole brief fails on the correct file, which is
    how this test was first written.
    """
    brief = prompts.image_prompt(layout, page_name)
    asked_for, _, forbidden = brief.partition("NEVER:")
    assert forbidden, "the NEVER block is what keeps the history look out"

    for history in ("reenactment", "torchlight", "period-accurate", "historical moment"):
        assert history not in asked_for.lower(), (
            f"{page_name} still asks for a history photograph"
        )
    for history in ("sepia", "torchlight", "reenactment", "period dress"):
        assert history in forbidden.lower(), f"{page_name} does not rule out {history}"

    assert "BRIGHT lighting" in asked_for
    assert "magazine" in asked_for.lower()
    # And the card contract survives the rewrite — this is the half that is not
    # taste, and dropping it is how a hero comes back with text baked in.
    assert "top-right" in brief
    assert "zero text" in brief


@pytest.mark.parametrize("page_name", [FITNESS, BODYBUILDING])
def test_the_hook_is_capped_well_under_the_history_pages_65_words(page_name):
    """C6. The cap is stated in the prompt, which is now the only place.

    `DraftContent.hook` used to restate "Under 65 words" and would have sent a
    Page asking for 30 two caps in the same request.
    """
    from app.writer.agent import DraftContent

    assert "65" not in (DraftContent.model_fields["hook"].description or "")
    assert "30 words" in prompts.system_prompt(layout, BODYBUILDING)
    assert "35 words" in prompts.system_prompt(layout, FITNESS)


@pytest.mark.parametrize("page_name", [FITNESS, BODYBUILDING])
def test_the_panel_token_is_substituted_in_a_page_file_too(page_name):
    """A per-Page file that forgets `{panel_pct}` hardcodes a stale number.

    That is exactly how the old system's copies rotted: they went on saying
    "~75% height" long after the panel started growing to fit.
    """
    brief = prompts.image_prompt(layout, page_name)

    assert "{panel_pct}" not in brief
    assert f"~{round(layout.panel.ratio * 100)}%" in brief


def test_the_highlight_colour_token_is_substituted_in_a_page_overlay():
    body = prompts.overlay_prompt(layout, FITNESS)

    assert "{highlight_color}" not in body
    assert layout.highlight.color in body


def test_no_page_prompt_asks_the_model_to_type_in_capitals():
    """C4 is a drawing setting, and the prompt must not fight it.

    The client's own Fitness Recipes prompt in the old tool said "Written in all
    CAPITAL LETTERS", and their drafts came out mixed case anyway — an
    instruction the model drifts off. The capitals are applied by
    `image.text.cased` at draw time now, so asking again would only put capitals
    into the stored hook the operator has to read and edit.
    """
    for page_name in (FITNESS, BODYBUILDING):
        body = prompts.system_prompt(layout, page_name)
        assert "in all CAPITAL LETTERS" not in body
        assert "normal sentence case" in body


def test_the_screen_says_which_files_the_page_is_actually_sent(client, session):
    """`GET /prompts?page_id=` — the window has to report the override.

    Showing a Page the global body, unmarked, is the same defect as the old
    tool's Settings tab: it told the client they had a prompt of their own when
    the row was History Retraced's, byte for byte.
    """
    fitness = Page(name=FITNESS, facebook_page_id="174689475989202")
    session.add(fitness)
    session.commit()
    session.refresh(fitness)

    globals_ = client.get("/prompts").json()
    assert [f["overridden"] for f in globals_] == [False] * len(globals_)

    scoped = client.get(f"/prompts?page_id={fitness.id}").json()
    by_name = {f["filename"]: f for f in scoped}
    assert all(by_name[name]["overridden"] for name in prompts.ORDER)
    assert "Fitness Recipes" in by_name["image.txt"]["body"]
    assert by_name["image.txt"]["body"] != next(
        f["body"] for f in globals_ if f["filename"] == "image.txt"
    )


def test_an_unknown_page_is_a_404_rather_than_the_global_prompts(client):
    assert client.get("/prompts?page_id=9999").status_code == 404


def test_the_history_page_is_untouched(client, page: Page, session: Session):
    """The global files are still History Retraced's, and it has no directory."""
    scoped = client.get(f"/prompts?page_id={page.id}").json()

    assert [f["overridden"] for f in scoped] == [False] * len(scoped)
    assert "History Retraced" in next(
        f["body"] for f in scoped if f["filename"] == "image.txt"
    )


# --- a Page's own text, over the files -----------------------------------------
#
# Prompts were files and read-only until 2026-08-17. Two things changed the
# answer, and neither weakens the reasoning that put them in files:
#
#   - only *overrides* are stored, so nothing holds a copy of text it did not
#     change, and the drift the file layout was chosen against needs copies;
#   - Railway's filesystem is ephemeral, so a screen that wrote a file would
#     lose the edit on the next redeploy — which is the shape of the client's
#     F5 complaint, believing for six weeks in prompts that did not exist.


def test_a_page_with_stored_text_is_sent_that_instead_of_any_file():
    page = Page(name=BODYBUILDING, facebook_page_id="1", system_prompt="Write short.")

    assert prompts.system_prompt(layout, page.name, page) == "Write short."


def test_stored_text_beats_the_pages_own_file_not_just_the_global():
    """Bodybuilding Tips has a `prompts/pages/` directory, so this is the case
    where both overrides exist and only one can win."""
    page = Page(name=BODYBUILDING, facebook_page_id="1", system_prompt="Write short.")
    from_file = prompts.system_prompt(layout, BODYBUILDING)

    assert from_file != "Write short.", "the fixture must not equal the file"
    assert prompts.system_prompt(layout, page.name, page) == "Write short."


def test_a_page_with_no_stored_text_still_reads_its_file():
    page = Page(name=BODYBUILDING, facebook_page_id="1")

    assert prompts.system_prompt(layout, page.name, page) == prompts.system_prompt(
        layout, BODYBUILDING
    )


def test_an_emptied_textarea_clears_the_override_rather_than_silencing_the_model():
    """`""` stored would send the model no system prompt at all — a Page with no
    voice, failing in a way that looks like the model misbehaving."""
    page = Page(name=BODYBUILDING, facebook_page_id="1", system_prompt="   ")

    assert prompts.stored("system.txt", page) is None
    assert prompts.system_prompt(layout, page.name, page) == prompts.system_prompt(
        layout, BODYBUILDING
    )


def test_the_three_sources_are_named_not_just_flagged():
    """`overridden` cannot answer what the operator is about to act on: editing
    inherited text creates an override they did not ask for, and a file-backed
    one cannot be edited from the screen at all."""
    stored = Page(name=BODYBUILDING, facebook_page_id="1", system_prompt="Mine.")
    filed = Page(name=BODYBUILDING, facebook_page_id="1")
    plain = Page(name="History Retraced", facebook_page_id="1")

    def source_of(page, filename="system.txt"):
        files = prompts.list_prompt_files(layout, page.name, page)
        return next(f for f in files if f["filename"] == filename)

    assert source_of(stored)["source"] == "page"
    assert source_of(filed)["source"] == "file-override"
    assert source_of(plain)["source"] == "global"
    assert source_of(plain)["overridden"] is False
    assert source_of(stored)["overridden"] is True


def test_only_the_three_known_prompts_can_be_stored_on_a_page():
    """A prompt with no column is a file and says so, rather than offering a
    textarea whose Save has nowhere to go."""
    page = Page(name="History Retraced", facebook_page_id="1")

    for entry in prompts.list_prompt_files(layout, page.name, page):
        assert entry["editable"] == (entry["filename"] in prompts.COLUMN)
