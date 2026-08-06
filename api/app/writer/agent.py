"""The writer: one agent, typed output, brand rules enforced inside.

Callers ask for a draft and get a brand-compliant draft, or an explanation.
They never see a retry. That is the depth that matters most here — the old
system exposed every intermediate state of a six-node graph, and its brand
rules ran afterwards as warnings nobody had to act on.
"""

import re
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

from app.models import Page, SourceItem, SourceKind
from app.settings import Layout, layout, settings
from app.writer import prompts, validators

MAX_RETRIES = 2
"""Two, then the residue becomes a Warning on the Draft.

The happy path still costs one call. If the retry rate climbs past ~20% the
rule is wrong, not the model — see plan.md's risk table.
"""


class DraftContent(BaseModel):
    """What the writer returns. Mirrors the columns it fills on `Draft`.

    There used to be an `overlay_text` beside `hook`, described as "the hook
    unless there is reason to differ". There never was a reason: both prompts
    gave them the same rules, and the model returned the same string twice. What
    the split actually bought was a hole — `validators.check` ran on `hook` while
    the compositor drew `overlay_text`, so the panel text was the one thing on
    the post no rule guarded. One field, validated, drawn.
    """

    hook: str = Field(
        description=(
            "The text drawn on the image panel. Under 65 words, no questions."
        )
    )
    caption: str = Field(description="The recap: at most 5 points, each opening with an emoji.")
    first_comment: str = Field(
        description=(
            "The main body, 1800-1900 characters, as 2-3 paragraphs separated "
            "by a blank line."
        )
    )
    highlight_phrases: list[str] = Field(
        description="5-8 short substrings copied verbatim out of the hook."
    )
    hashtags: list[str] = Field(default_factory=list)
    image_prompt: str = Field(description="A photorealistic hero prompt for this story.")


def _instructions(page: Page, layout: Layout) -> str:
    """System prompt, panel rules, and how to treat the source.

    The last part is the one that cannot be got wrong. `is_factual` decides
    whether the Source Item's *subject* binds; reversing it tells the model to
    treat a Smithsonian piece as a writing sample, and the result is confident,
    well-formed output about the wrong story that nothing downstream catches.
    """
    return "\n\n".join(
        [
            prompts.system_prompt(layout),
            prompts.overlay_prompt(layout),
            f"You are writing for the Facebook page {page.name}.",
        ]
    )


def source_instruction(kind: SourceKind) -> str:
    """How to read the Source Item. Derived from `kind`, never stored."""
    if kind.is_factual:
        return (
            "The source below is FACTUAL. Write about this same story, the same "
            "people and the same events. Do not invent a different subject."
        )
    return (
        "The source below is a STYLE sample. Borrow its tone, rhythm and "
        "structure only. Choose your own subject — do not write about its story."
    )


def _validate(_ctx: RunContext, output: DraftContent) -> DraftContent:
    reasons = validators.check(output.hook, output.caption, output.first_comment)
    if reasons:
        raise ModelRetry(
            "The draft breaks brand rules. Fix all of these and return the whole "
            "draft again:\n- " + "\n- ".join(reasons)
        )
    return output


def build_agent(page: Page, model: object | None = None) -> Agent:
    """One agent for one Page. `model` overrides for tests, which pass a fake.

    The validator is attached here rather than declared at module level because
    the instructions depend on the Page, and an Agent is cheap to build.
    """
    agent = Agent(
        model or _model(settings.gemini_text_model),
        output_type=DraftContent,
        instructions=_instructions(page, layout),
        model_settings=_model_settings(settings.gemini_text_model),
        retries=MAX_RETRIES,
    )
    agent.output_validator(_validate)
    return agent


FALLBACK_MODELS = ("gemini-flash-latest",)
"""Tried in order when the configured model is unavailable.

Ported from the old repo, which kept the same chain
(`generate-with-fallback.ts:9`) — and needed it. `gemini-3.5-flash` answered
503 "experiencing high demand" three times while this was being built, and one
of those killed a real run.

**Every pinned version has now rotted out of this chain, both on 2026-08-06.**
`gemini-2.0-flash` went first, answering 404 "no longer available" — the same
rot the old repo hit on the image side (`376afdc`). `gemini-2.5-flash` went
hours later, and its wording is the lesson: *"no longer available to new
users."* It kept working on the project the key had always belonged to and
404'd on a project created that afternoon, so a pinned model can be alive for
you and dead for a clone. Neither was detectable from `models.list()`, which
went on listing both.

That leaves one link, and it is an alias on purpose. Google repoints
`gemini-flash-latest`, so it cannot rot the way the pinned ones did. Adding a
pinned version back would buy a second link that expires silently on somebody
else's project — worse than no link, because it fails only where nobody is
looking.
"""

TRANSIENT_CODES = ("500", "502", "503", "504", "429")
TRANSIENT_WORDS = ("unavailable", "high demand", "resource_exhausted", "overloaded")
_STATUS = re.compile(r"\b(?:code|status(?:_code)?)\W{0,3}(\d{3})\b", re.I)
"""What means "ask again", as opposed to "this request is wrong".

The codes are matched **as codes**, not as substrings. They used to be plain
`in` tests, which made `is_transient` true for
`"The first comment is 1402 characters; expand it past 1500."` — our own
validator message, because `"1500"` contains `"500"`. A brand-rule failure would
have read as an overloaded server and silently moved the run onto a different
model. Nothing had hit it yet: `UnexpectedModelBehavior` does not carry the
retry reason in its text. `BODY_MIN_CHARS` being 1,500 was one exception
signature away from it.

The words stay as substrings — they are phrases no rule of ours produces.
"""


def is_transient(error: Exception) -> bool:
    message = str(error)
    if any(word in message.lower() for word in TRANSIENT_WORDS):
        return True
    return any(found in TRANSIENT_CODES for found in _STATUS.findall(message))


@lru_cache(maxsize=4)
def _model(model_name: str) -> GoogleModel:
    if not settings.gemini_api_key:
        raise RuntimeError("missing GEMINI_API_KEY")
    return GoogleModel(
        model_name, provider=GoogleProvider(api_key=settings.gemini_api_key)
    )


def _model_settings(model_name: str) -> GoogleModelSettings | None:
    """Thinking is a Gemini 3.x feature; asking 2.5 for it is an error.

    The old repo stripped `thinkingConfig` for any model that was not 3.x
    (`generate-with-fallback.ts:30`), which matters here precisely because the
    fallback chain steps down onto 2.5 and 2.0.
    """
    if "gemini-3" not in model_name.lower():
        return None
    return GoogleModelSettings(google_thinking_config={"thinking_level": "MEDIUM"})


def user_prompt(source: SourceItem | None, topic: str | None) -> str:
    """The run's one variable input: a Source Item, or a bare topic."""
    if source is None:
        if not topic:
            raise ValueError("a run needs either a source item or a topic")
        return f"Write a post about: {topic}"

    parts = [source_instruction(source.kind), ""]
    if source.author:
        parts.append(f"Author: {source.author}")
    if source.url:
        parts.append(f"URL: {source.url}")
    parts += ["", source.text]
    return "\n".join(parts)


def write(page: Page, source: SourceItem | None, topic: str | None = None, model=None):
    """A brand-compliant draft, or an explanation. Never a retry.

    Two different retries live here and they are not the same thing.
    `ModelRetry` corrects a draft that broke a brand rule — that is the writer
    doing its job. This loop reacts to the model being *unavailable*, which is
    not about the draft at all, and steps down the fallback chain rather than
    asking the same overloaded model again.

    A caller passing `model` gets exactly that model and no fallback: tests
    supply a fake, and silently swapping it for a real one would bill them.
    """
    if model is not None:
        return build_agent(page, model).run_sync(user_prompt(source, topic))

    prompt = user_prompt(source, topic)
    names = [settings.gemini_text_model, *FALLBACK_MODELS]
    last: Exception | None = None

    for name in dict.fromkeys(names):  # de-duplicated, order kept
        try:
            agent = Agent(
                _model(name),
                output_type=DraftContent,
                instructions=_instructions(page, layout),
                model_settings=_model_settings(name),
                retries=MAX_RETRIES,
            )
            agent.output_validator(_validate)
            return agent.run_sync(prompt)
        except Exception as error:  # noqa: BLE001 — re-raised below if not transient
            if not is_transient(error):
                raise
            last = error

    assert last is not None
    raise last
