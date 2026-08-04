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
    "overlay_text": "Marie Tharp mapped the ocean floor in 1957.",
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


@pytest.mark.parametrize("years", ["Marie Tharp (1920-2006) did", "Ada Lovelace (b. 1990) does"])
def test_birth_and_death_years_are_recognised(years):
    assert validators.birth_death_years(years) is None


def test_a_body_with_no_years_is_caught():
    reason = validators.birth_death_years("Marie Tharp mapped the ocean floor.")
    assert reason and "birth/death years" in reason


@pytest.mark.parametrize("phrase", ["as we look back", "As Of Today", "a look back at"])
def test_meta_phrases_are_caught_case_insensitively(phrase):
    assert validators.no_meta_phrases("", f"And {phrase}, the map endures.")


def test_every_violation_is_reported_at_once():
    """A retry costs a call either way, so it should carry the whole list."""
    reasons = validators.check("Why did she do it?", "no emoji here", "short")

    assert len(reasons) >= 4


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
