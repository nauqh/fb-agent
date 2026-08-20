"""The brand rules, and the retry loop. No network, no model spend."""

import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from app.models import Page, SourceItem, SourceKind
from app.writer import agent as writer
from app.writer import validators
from pydantic_ai.messages import BinaryImage

# A draft that breaks nothing, used as the baseline every test mutates.
GOOD = {
    "hook": "Marie Tharp mapped the ocean floor in 1957 and was told it was girl talk.",
    "caption": (
        "🌊 She drew the mid-Atlantic ridge by hand from soundings.\n"
        "🚫 She was barred from the research ship collecting them.\n"
        "📉 Her own colleague called the result girl talk."
    ),
    "first_comment": (
        "Marie Tharp (1920-2006) joined Lamont Geological Observatory in 1948, at a "
        "time when women were not permitted aboard the research vessels whose data "
        "she was employed to interpret. She worked from numbers other people "
        "collected, and she worked in ink.\n\n"
        + "Her maps redrew the sea floor and, with it, the argument for continental "
        "drift that Bruce Heezen (1924-1977) had dismissed as girl talk before he "
        "came to accept it. " * 9
    ),
    "highlight_phrases": ["Marie Tharp", "1957", "ocean floor"],
    "image_prompt": "A woman at a drafting table, 1950s, documentary photograph.",
}


# --- the rules, directly -----------------------------------------------------


def test_a_compliant_draft_reports_nothing():
    assert validators.check(GOOD["hook"], GOOD["caption"], GOOD["first_comment"]) == []


def test_a_hook_that_asks_a_question_is_caught():
    reason = validators.hook_has_no_question("Did Marie Tharp map the ocean floor?")
    assert reason and "question" in reason


def test_a_hook_over_sixty_five_words_is_caught():
    reason = validators.hook_length("word " * 66)
    assert reason and "66 words" in reason


def test_more_than_five_recap_points_is_caught():
    reason = validators.recap_point_count("\n".join(f"🌊 point {i}" for i in range(6)))
    assert reason and "6 points" in reason


def test_a_recap_line_without_an_emoji_is_caught():
    reason = validators.recap_lines_start_with_emoji("🌊 With one.\nWithout one.")
    assert reason and "do not start with an emoji" in reason


@pytest.mark.parametrize(
    "years",
    [
        "Marie Tharp (1920-2006) did",
        "Ada Lovelace (b. 1990) does",
        "Ada Lovelace (1815 — 1852) wrote",  # em dash
        # Antiquity. These were all rejected until 2026-08-06: the pattern was
        # `\d{4}` with no era, so every pre-1000 subject was unwritable on a
        # history page — and because this rule raises `ModelRetry`, the writer
        # resubmitted correct text until it ran out of retries and the run died.
        "Wu Zetian (624 – 705 AD) ascended",
        "Hypatia (350 - 415 CE) taught",
        "Cleopatra (69 BC - 30 BC) ruled",
        "Someone (b. 812) lived",
    ],
)
def test_birth_and_death_years_are_recognised(years):
    assert validators.birth_death_years(years) is None


@pytest.mark.parametrize(
    "text",
    [
        "Marie Tharp mapped the ocean floor.",
        "The year 1934 appears bare, outside parentheses.",
        # The era marker is what keeps a short span from reading as a lifespan.
        "It took (2 - 3 hours) to build.",
        "Rated (4 - 5 stars) by critics.",
    ],
)
def test_a_body_with_no_years_is_caught(text):
    reason = validators.birth_death_years(text)
    assert reason and "birth/death years" in reason


@pytest.mark.parametrize("phrase", ["as we look back", "As Of Today", "a look back at"])
def test_meta_phrases_are_caught_case_insensitively(phrase):
    assert validators.no_meta_phrases("", f"And {phrase}, the map endures.")


def test_every_violation_is_reported_at_once():
    """A retry costs a call either way, so it should carry the whole list."""
    reasons = validators.check("Why did she do it?", "no emoji here", "short")

    assert len(reasons) >= 4


def test_a_story_naming_no_people_does_not_block_the_writer():
    """The Zantigo case: an Atlas Obscura piece about a taco chain.

    No person is named, so no rewrite can produce birth/death years. While this
    was a blocking rule the writer resubmitted a correct draft until it ran out
    of retries and the run died.
    """
    body = "\n\n".join(
        ["The chain opened in Minneapolis. " * 28, "Then it closed for good. " * 30]
    )

    assert validators.check("A hook.", "🌮 One point.", body) == []
    assert validators.advise(body), "still worth telling the operator"


def test_the_blocking_rules_are_only_ones_the_model_can_act_on():
    """A rule that cannot be satisfied on demand kills the run instead of warning."""
    blocking = "\n".join(validators.check("Why?", "no emoji", "short"))

    assert "birth/death years" not in blocking


# --- the retry loop ----------------------------------------------------------


@pytest.fixture
def page() -> Page:
    return Page(id=1, name="History Retraced", facebook_page_id="1", metricool_blog_id="1")


def _responder(*drafts: dict):
    """A model that returns each draft in turn, recording how often it was called."""
    calls: list[int] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        index = min(len(calls), len(drafts) - 1)
        calls.append(1)
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, drafts[index])])

    return FunctionModel(respond), calls


def test_a_compliant_draft_passes_on_the_first_call(page):
    model, calls = _responder(GOOD)

    result = writer.write(page, None, topic="Marie Tharp", model=model)

    assert result.output.hook == GOOD["hook"]
    assert len(calls) == 1, "the happy path must cost exactly one call"


def test_a_violation_is_retried_and_corrected(page):
    """The phase's done-when: a hook ending in `?` comes back fixed, not warned."""
    bad = {**GOOD, "hook": "Did Marie Tharp really map the ocean floor?"}
    model, calls = _responder(bad, GOOD)

    result = writer.write(page, None, topic="Marie Tharp", model=model)

    assert "?" not in result.output.hook
    assert len(calls) == 2, "one retry, not more"


def test_the_retry_tells_the_model_what_to_fix(page):
    """A retry that does not name the rule is a coin flip."""
    bad = {**GOOD, "hook": "Did she map it?"}
    seen: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in message.parts:
                content = getattr(part, "content", None)
                if isinstance(content, str) and "brand rules" in content:
                    seen.append(content)
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, GOOD if seen else bad)])

    writer.write(page, None, topic="x", model=FunctionModel(respond))

    assert seen, "the model was never told why it was being retried"
    assert "question" in seen[0]


def test_retries_are_capped(page):
    """Otherwise one stubborn rule bills indefinitely."""
    bad = {**GOOD, "hook": "Did she map it?"}
    model, calls = _responder(bad)

    with pytest.raises(UnexpectedModelBehavior, match="Exceeded maximum output retries"):
        writer.write(page, None, topic="x", model=model)

    # The first call plus MAX_RETRIES corrections, and then it stops.
    assert len(calls) == writer.MAX_RETRIES + 1


# --- the instruction that must not be reversed -------------------------------


@pytest.mark.parametrize("kind", list(SourceKind))
def test_every_kind_binds_the_subject(kind):
    """Reversing this produces confident output about the wrong story.

    The competitor-post branch used to say the opposite — "a STYLE sample,
    choose your own subject" — and the client reported it on 2026-08-18 as posts
    that were not generated from the competitor posts they ticked. They were;
    the prompt told the model to write about something else.
    """
    instruction = writer.source_instruction(kind)

    assert "SAME story" in instruction or "same story" in instruction
    assert "Do not invent a different subject" in instruction
    assert "own subject" not in instruction


def test_a_competitor_post_binds_the_subject_without_lending_its_words():
    """Same story, our writing. The one rule that is only about competitors.

    Their post is a finished artefact, so "write about this" and "do not copy
    this" have to arrive together. An RSS item needs no such warning.
    """
    instruction = writer.source_instruction(SourceKind.COMPETITOR_POST)

    assert "Do not reuse their wording" in instruction


def test_the_prompt_carries_the_source_text_and_its_instruction():
    source = SourceItem(
        id=1,
        kind=SourceKind.RSS,
        external_id="u",
        author="Smithsonian Magazine",
        text="Marie Tharp drew the ridge by hand.",
        url="https://example.com/x",
    )

    prompt = writer.user_prompt(source, None)

    assert "FACTUAL" in prompt
    assert "Marie Tharp drew the ridge by hand." in prompt
    assert "Smithsonian Magazine" in prompt


def test_a_run_with_neither_a_source_nor_a_topic_is_refused():
    with pytest.raises(ValueError, match="source item or a topic"):
        writer.user_prompt(None, None)


def test_user_contents_text_only_is_a_bare_string():
    assert writer.user_contents("just prose", None) == "just prose"


def test_user_contents_sends_the_picture_in_the_same_turn():
    img = BinaryImage(data=b"abc", media_type="image/jpeg")
    contents = writer.user_contents("the caption", img)
    assert contents == ["the caption", img]
    assert contents[1].kind == "binary"


def _pictures(messages: list[ModelMessage]) -> list[BinaryImage]:
    """Every image part the model was actually handed."""
    found = []
    for message in messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, list):
                found += [item for item in content if isinstance(item, BinaryImage)]
    return found


def _rival() -> SourceItem:
    return SourceItem(
        kind=SourceKind.COMPETITOR_POST,
        external_id="rival-1",
        text="the rival's post about the flood",
        image_url="https://example.com/rival.jpg",
    )


def test_the_picture_reaches_the_model_not_just_the_content_list(page):
    """`user_contents` is one hop; this is the whole way down to the request."""
    seen: list[list[BinaryImage]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(_pictures(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, GOOD)])

    writer.write(
        page,
        _rival(),
        model=FunctionModel(respond),
        image=BinaryImage(data=b"abc", media_type="image/jpeg"),
    )

    assert seen[0], "the model was handed no image part"
    assert seen[0][0].data == b"abc"


def test_a_rewrite_never_carries_the_picture(page):
    """Decided, not overlooked — the old app's regenerate was text-only too.

    The fields being kept are in the prompt verbatim and were written while the
    model could see the picture, so its contribution is already there as prose.
    A rewrite is synchronous and pressed repeatedly; sending the image again
    would buy a fetch and vision tokens per press for detail already in hand.
    """
    seen: list[list[BinaryImage]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(_pictures(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, GOOD)])

    writer.rewrite(
        page,
        _rival(),
        None,
        "hook",
        {"caption": GOOD["caption"], "first_comment": GOOD["first_comment"]},
        model=FunctionModel(respond),
    )

    assert seen[0] == [], "a rewrite must not send the competitor's picture"


# --- the model being unavailable, which is not about the draft ---------------


@pytest.mark.parametrize(
    "message",
    [
        "status_code: 503, body: {'error': {'status': 'UNAVAILABLE'}}",
        "This model is currently experiencing high demand.",
        "RESOURCE_EXHAUSTED",
    ],
)
def test_an_overloaded_model_is_transient(message):
    assert writer.is_transient(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    [
        "status_code: 400, invalid argument",
        "API key not valid",
        "status_code: 404, this model is no longer available. NOT_FOUND",
    ],
)
def test_a_bad_request_is_not_transient(message):
    """Retrying these just spends the same money three times."""
    assert not writer.is_transient(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    [
        "The first comment is 1402 characters; expand it past 1500.",
        "The first comment is 2117 characters; cut it below 2100.",
        "The hook is 502 words; it must be under 65.",
        "Exceeded maximum output retries (2)",
    ],
)
def test_our_own_rule_messages_are_never_read_as_an_outage(message):
    """`"500"` lives inside `"1500"`, and `BODY_MIN_CHARS` is 1,500.

    While the codes were matched as bare substrings, a brand-rule failure could
    read as an overloaded server and move the run onto a different model — a
    silent model swap for a reason that has nothing to do with availability.
    """
    assert not writer.is_transient(RuntimeError(message))


def test_thinking_is_set_for_gemini_3_and_stripped_below_it():
    """Asking 2.5 for a 3.x thinking config is an error, and the chain steps down."""
    assert writer._model_settings("gemini-3.5-flash") is not None
    assert writer._model_settings("gemini-2.5-flash") is None
    assert writer._model_settings("gemini-2.0-flash") is None


def test_the_configured_model_is_tried_before_the_fallbacks():
    chain = writer.settings.text_fallback_chain
    assert chain[0] == writer.settings.gemini_text_model
    assert len(set(chain)) == len(chain), "a model would be tried twice"


@pytest.mark.parametrize("retired", ["gemini-2.0-flash", "gemini-2.5-flash"])
def test_no_pinned_version_is_a_fallback(retired):
    """Both of these were links here, and both started answering 404.

    `gemini-2.5-flash` is the sharper case: *"no longer available to new
    users."* It still answered on the project the key had always belonged to
    and 404'd on a project created the same afternoon — so a pinned model can
    be alive for us and dead for a clone, and `models.list()` reports neither.
    """
    assert retired not in writer.settings.text_fallback_chain


def test_the_fallback_chain_is_the_one_that_was_checked():
    """A tripwire on a default, not a rule. The rule used to be aliases only —
    Google repoints an alias, a pin expires silently. Then the alias was
    measured: `gemini-flash-latest` answered a ping and 503'd on a real
    `writer.rewrite` in the same minute, because it points at a busy model.
    `gemini-3.6-flash` completed a structured rewrite on 2026-08-14.

    Changing this means checking the new id with a real call, not
    `models.list()`, which reports models that 404 on use.
    """
    assert writer.settings.gemini_text_fallback_models == "gemini-3.6-flash"


def test_a_supplied_model_is_never_swapped_for_a_real_one(page, monkeypatch):
    """A test passing a fake must not be billed for a live call."""

    def explode(*_a, **_k):
        raise AssertionError("built a real model when one was supplied")

    monkeypatch.setattr(writer, "_model", explode)
    model, _ = _responder(GOOD)

    assert writer.write(page, None, topic="x", model=model).output.hook == GOOD["hook"]


# --- one field, so the rules and the renderer cannot disagree ----------------


def test_there_is_no_second_field_holding_the_panel_text():
    """`overlay_text` sat beside `hook` holding the same string until 2026-08-06.

    Both prompts gave them identical rules, so the model returned the hook
    twice. Restoring it reopens the hole below.
    """
    assert "overlay_text" not in writer.DraftContent.model_fields


def test_the_text_drawn_on_the_image_is_the_text_the_rules_guard(page):
    """The hole the merge closed.

    `validators.check` ran on `hook` while the compositor drew `overlay_text`,
    so the panel — the one part of the post a reader cannot scroll past — was
    the only copy no brand rule touched. A 200-word question could reach a
    finished image. Now a hook that breaks a rule is retried before anything is
    drawn from it.
    """
    from app.image import text as overlay

    asked = {**GOOD, "hook": "Did Marie Tharp map the ocean floor?"}
    model, calls = _responder(asked, GOOD)

    result = writer.write(page, None, topic="x", model=model)

    assert len(calls) == 2, "the panel text was accepted without correction"
    assert "?" not in result.output.hook

    # And it is that same corrected string the compositor lays out.
    plan = overlay.plan(result.output.hook)
    assert " ".join(plan.lines).startswith("Marie Tharp")


# --- lengths, per Page (C6, C7) ------------------------------------------------
#
# The client's C6 and C7 (2026-08-15) are the same complaint C5 was: the numbers
# were History Retraced's and every Page got them. Bodybuilding Tips and Fitness
# Recipes want a 30-word hook and a first comment capped at 1,500 characters over
# 3–4 paragraphs; the history page wants none of that.
#
# C7 sat dropped for two days because 1,500 was the global *floor* — their
# ceiling was our minimum, so no draft could satisfy both. That is why `Limits`
# carries `disagrees()` and why the route calls it before saving.


def _page(**overrides) -> Page:
    return Page(name="Bodybuilding Tips N Tricks", facebook_page_id="1", **overrides)


def test_a_page_that_asks_for_nothing_gets_the_house_numbers():
    """Nine of the ten Pages, and every test written before this existed."""
    assert validators.Limits.for_page(_page()) == validators.Limits()


def test_a_page_can_ask_for_a_shorter_hook_than_the_house():
    limits = validators.Limits.for_page(_page(hook_max_words=30))

    assert validators.hook_length("word " * 31, limits), "31 words breaks a 30 cap"
    assert validators.hook_length("word " * 31) is None, "but not the house 65"


def test_a_page_can_ask_for_a_shorter_first_comment():
    """C7 as written: capped at 1,500, which the house treats as a floor."""
    limits = validators.Limits.for_page(
        _page(first_comment_min_chars=800, first_comment_max_chars=1_500)
    )
    body = "x" * 1_200

    assert validators.body_length(body, limits) is None
    reason = validators.body_length(body)
    assert reason and "expand it past 1500" in reason, "the house would reject it"


def test_a_page_can_ask_for_four_paragraphs():
    limits = validators.Limits.for_page(
        _page(first_comment_min_paragraphs=3, first_comment_max_paragraphs=4)
    )
    four = "\n\n".join(["para"] * 4)

    assert validators.first_comment_paragraphs(four, limits) is None
    assert validators.first_comment_paragraphs(four), "the house range is 2-3"


def test_one_end_of_a_range_can_move_without_the_other():
    """Null inherits, so a Page setting only the ceiling keeps the house floor.
    That is the combination `disagrees` exists to catch."""
    limits = validators.Limits.for_page(_page(first_comment_max_chars=1_500))

    assert limits.body_min_chars == validators.BODY_MIN_CHARS
    assert limits.body_max_chars == 1_500


def test_a_band_no_draft_could_satisfy_is_named_rather_than_left_to_the_model():
    """1,500 floor against a 1,500 ceiling is not strictness, it is a dead run:
    every draft fails one end, burns both retries and dies at
    `Exceeded maximum output retries`."""
    limits = validators.Limits.for_page(_page(first_comment_max_chars=1_400))

    assert limits.disagrees(), "1,500 floor vs 1,400 ceiling is unsatisfiable"
    assert validators.Limits().disagrees() is None
    assert validators.Limits.for_page(
        _page(first_comment_min_chars=800, first_comment_max_chars=1_500)
    ).disagrees() is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"first_comment_min_paragraphs": 4, "first_comment_max_paragraphs": 2},
        {"hook_max_words": 3},
    ],
    ids=["backwards-paragraphs", "unwritable-hook"],
)
def test_the_other_impossible_settings_are_caught_too(overrides):
    assert validators.Limits.for_page(_page(**overrides)).disagrees()


def test_the_prompt_states_this_pages_lengths_so_the_check_cannot_surprise_it():
    """A rule the model was never told is a retry it cannot act on.

    The house numbers are already in the prompt prose, so they are *not*
    repeated — a second copy is the drift `prompts.py` is written against.
    """
    from app.settings import layout

    plain = writer._instructions(_page(), layout)
    capped = writer._instructions(_page(hook_max_words=30), layout)

    assert "LENGTHS FOR THIS PAGE" not in plain, "no second copy of the house numbers"
    assert "at most 30 words" in capped
    assert capped.index("LENGTHS FOR THIS PAGE") > capped.index(
        "You are writing for the Facebook page"
    ), "the override has to come last to win"
