"""The brand rules, and the retry loop. No network, no model spend."""

import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from app.models import Page, SourceItem, SourceKind
from app.writer import agent as writer
from app.writer import validators

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
    "hashtags": ["#history"],
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


def test_a_competitor_post_is_a_style_sample_not_a_subject():
    instruction = writer.source_instruction(SourceKind.COMPETITOR_POST)

    assert "STYLE" in instruction
    assert "own subject" in instruction


@pytest.mark.parametrize("kind", [SourceKind.RSS, SourceKind.TWEET])
def test_an_rss_item_or_tweet_binds_the_subject(kind):
    """Reversing this produces confident output about the wrong story."""
    instruction = writer.source_instruction(kind)

    assert "FACTUAL" in instruction
    assert "same story" in instruction


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
    names = [writer.settings.gemini_text_model, *writer.FALLBACK_MODELS]
    assert list(dict.fromkeys(names))[0] == writer.settings.gemini_text_model


@pytest.mark.parametrize("retired", ["gemini-2.0-flash", "gemini-2.5-flash"])
def test_no_pinned_version_is_a_fallback(retired):
    """Both of these were links here, and both started answering 404.

    `gemini-2.5-flash` is the sharper case: *"no longer available to new
    users."* It still answered on the project the key had always belonged to
    and 404'd on a project created the same afternoon — so a pinned model can
    be alive for us and dead for a clone, and `models.list()` reports neither.
    """
    assert retired not in writer.FALLBACK_MODELS


def test_every_fallback_is_an_alias_so_it_cannot_be_retired():
    """Vacuous while the list is empty, and that is the point: if a link is ever
    added back it must be an alias. A provider repoints an alias; a pinned
    version just expires, and does so silently."""
    assert all(name.endswith("-latest") for name in writer.FALLBACK_MODELS)


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


# --- hashtags, which arrived both ways ---------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (["history", "mystery"], ["#history", "#mystery"]),
        (["#history", "#mystery"], ["#history", "#mystery"]),
        (["##history"], ["#history"]),
        (["  spaced  out "], ["#spacedout"]),
        (["history", "#History"], ["#history"]),
        (["", "   ", "#"], []),
    ],
)
def test_a_hashtag_without_its_hash_is_a_word(given, expected):
    """The model returned both shapes on consecutive runs, and the field carried
    no description for most of its life. Fixed rather than asked for twice —
    the operator's edit box never passes through the schema at all.

    Internal spaces go because Facebook ends a tag at the first one: `#Bill
    Millin` posts as `#Bill` and then stray text.
    """
    assert validators.normalise_hashtags(given) == expected


def test_the_writer_normalises_what_the_model_returns():
    content = writer.DraftContent(**{**GOOD, "hashtags": ["history", "#WWII"]})

    assert content.hashtags == ["#history", "#WWII"]
