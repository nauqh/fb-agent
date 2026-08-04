"""The writer: one agent, typed output, brand rules enforced inside.

Callers ask for a draft and get a brand-compliant draft, or an explanation.
They never see a retry. That is the depth that matters most here — the old
system exposed every intermediate state of a six-node graph, and its brand
rules ran afterwards as warnings nobody had to act on.
"""

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
    """What the writer returns. Mirrors the columns it fills on `Draft`."""

    hook: str = Field(description="Text for the image panel. Under 65 words, no questions.")
    caption: str = Field(description="The recap: at most 5 points, each opening with an emoji.")
    first_comment: str = Field(description="The main body, 1800-1900 characters.")
    overlay_text: str = Field(description="Panel text. The hook unless there is reason to differ.")
    highlight_phrases: list[str] = Field(
        description="5-8 short substrings copied verbatim out of overlay_text."
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


FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")
"""Tried in order when the configured model is unavailable.

Ported from the old repo, which kept the same chain
(`generate-with-fallback.ts:9`) — and needed it. `gemini-3.5-flash` answered
503 "experiencing high demand" three times while this was being built, and one
of those killed a real run.
"""

TRANSIENT = ("503", "UNAVAILABLE", "high demand", "RESOURCE_EXHAUSTED", "500", "502")
"""Substrings that mean "ask again", not "this request is wrong".

Matched on the message because `ModelHTTPError` flattens the provider's body
into it. Crude, and deliberately so: the failure mode of matching too widely is
one wasted retry, and of matching too narrowly is a dead run.
"""


def is_transient(error: Exception) -> bool:
    message = str(error)
    return any(marker.lower() in message.lower() for marker in TRANSIENT)


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
