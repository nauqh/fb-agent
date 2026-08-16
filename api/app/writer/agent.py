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
from app.transient import is_transient
from app.writer import prompts, validators

__all__ = ["is_transient"]  # re-exported: it was defined here before `image/` needed it too

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

    # These say what each field *is*, and leave the numbers to the prompt.
    #
    # They used to restate them — "Under 65 words", "5-8 short substrings" — and
    # that was survivable while one prompt served every Page. It stops being
    # survivable the moment a Page has its own: Fitness Recipes asks for a
    # 35-word hook and 1-3 highlights, so a description carrying the old numbers
    # sends the model two caps in the same request and lets it pick. The
    # validators are still the backstop; the prompt is the instruction.
    hook: str = Field(description="The text drawn on the image panel. No questions.")
    caption: str = Field(description="The recap: at most 5 points, each opening with an emoji.")
    first_comment: str = Field(
        description=(
            "The main body, as paragraphs separated by a blank line. Length and "
            "paragraph count are stated in the prompt."
        )
    )
    highlight_phrases: list[str] = Field(
        description="Short substrings copied verbatim out of the hook."
    )
    image_prompt: str = Field(description="A photorealistic hero prompt for this story.")


def _instructions(page: Page, layout: Layout) -> str:
    """System prompt, panel rules, and how to treat the source.

    The last part is the one that cannot be got wrong. `is_factual` decides
    whether the Source Item's *subject* binds; reversing it tells the model to
    treat a Smithsonian piece as a writing sample, and the result is confident,
    well-formed output about the wrong story that nothing downstream catches.

    The sentence naming the page used to be the *whole* per-Page dimension of
    this prompt. It is now the fallback: `page.name` also selects
    `prompts/pages/<slug>/`, and a Page with its own files never sees History
    Retraced's voice at all.
    """
    return "\n\n".join(
        [
            prompts.system_prompt(layout, page.name),
            prompts.overlay_prompt(layout, page.name),
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


"""The chain is `settings.text_fallback_chain` — deployment config, like the
image one beside it, because model ids rot and a rotted id should be an env
change rather than a release. The evidence for what is in it is on the setting.
"""

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
    return _run(page, user_prompt(source, topic), _validate, model)


def _run(page: Page, prompt: str, validator, model=None):
    """Ask the model, stepping down the fallback chain while it is unavailable.

    Extracted so `rewrite` cannot grow a second copy of the ladder — the two
    differ only in what they ask for and which rules they hold the answer to.

    A caller passing `model` gets exactly that model and no fallback: tests
    supply a fake, and silently swapping it for a real one would bill them.
    """
    if model is not None:
        agent = build_agent(page, model)
        if validator is not _validate:
            # `build_agent` already attached the whole-draft validator; a
            # rewrite needs the narrower one instead, and pydantic-ai has no
            # way to detach.
            agent = Agent(
                model,
                output_type=DraftContent,
                instructions=_instructions(page, layout),
                retries=MAX_RETRIES,
            )
            agent.output_validator(validator)
        return agent.run_sync(prompt)

    last: Exception | None = None

    for name in dict.fromkeys(settings.text_fallback_chain):  # de-duplicated, order kept
        try:
            agent = Agent(
                _model(name),
                output_type=DraftContent,
                instructions=_instructions(page, layout),
                model_settings=_model_settings(name),
                retries=MAX_RETRIES,
            )
            agent.output_validator(validator)
            return agent.run_sync(prompt)
        except Exception as error:  # noqa: BLE001 — re-raised below if not transient
            if not is_transient(error):
                raise
            last = error

    assert last is not None
    raise last


REGENERATABLE = ("hook", "caption", "first_comment")
"""The three fields the operator can ask for again, one at a time.

`highlight_phrases` is not on the list and cannot be: it is defined as verbatim
substrings *of the hook*, so it has no meaning apart from one. It rides along
when the hook is rewritten — see `rewrite`.

`image_prompt` is not here either. Re-rolling it changes nothing on its own; the
picture is bought by `POST /drafts/{id}/image?new_hero=true`, and the prompt is
editable by hand for exactly that purpose.
"""


def _field_rules(field: str):
    """The blocking rules that apply to **one** field, as an output validator.

    The whole-draft validator cannot be reused here. It checks all three fields,
    and on a rewrite the other two come from the row unchanged — so a draft that
    was written by hand, or predates a rule, would fail validation on text the
    operator explicitly asked to keep. The model would then spend its retries
    fixing fields nobody asked about, and the run could exhaust them and die
    without ever producing the one field that was requested.

    So each field is held to its own rules and nothing else. `no_meta_phrases`
    reads the recap and the body together, and is applied to both, because it is
    a rule about the prose either of them contains.
    """

    def reasons(content: DraftContent) -> list[str]:
        if field == "hook":
            found = [
                validators.hook_length(content.hook),
                validators.hook_has_no_question(content.hook),
            ]
        elif field == "caption":
            found = [
                validators.recap_point_count(content.caption),
                validators.recap_lines_start_with_emoji(content.caption),
                validators.no_meta_phrases(content.caption, ""),
            ]
        else:
            found = [
                validators.first_comment_paragraphs(content.first_comment),
                validators.body_length(content.first_comment),
                validators.no_meta_phrases("", content.first_comment),
            ]
        return [reason for reason in found if reason]

    def validate(_ctx: RunContext, output: DraftContent) -> DraftContent:
        broken = reasons(output)
        if broken:
            raise ModelRetry(
                f"The {field.replace('_', ' ')} breaks brand rules. Fix all of "
                "these and return the whole draft again:\n- " + "\n- ".join(broken)
            )
        return output

    return validate


def rewrite_prompt(
    source: SourceItem | None,
    topic: str | None,
    field: str,
    keeping: dict[str, str],
    instruction: str | None = None,
) -> str:
    """The original brief, plus what is being kept and what to replace.

    **The kept fields are in the prompt, and that is the whole point.** A caption
    regenerated in isolation is a caption for a different post — it would not
    open on the hook that is drawn on the picture above it, and the operator
    would be handed two halves that do not meet. Showing the model what stays is
    what makes the new field fit the old ones.

    `instruction` is the operator's own line, and it **replaces** the demand for
    novelty rather than joining it. The two contradict each other: "produce a
    genuinely different one" answers *this is not the post I want*, while "make
    it longer" answers *this is the post I want, said better*. The client's first
    real use was a hook that was too short — no rule anywhere sets a minimum, so
    every unargued retry was an equally valid short hook and the button could
    only re-roll, never steer.
    """
    parts = [user_prompt(source, topic), ""]
    parts.append(
        "This post already exists. Keep the fields below EXACTLY as they are "
        "and return them unchanged."
    )
    for name, value in keeping.items():
        if value:
            parts += ["", f"{name.replace('_', ' ').upper()} (keep verbatim):", value]

    named = field.replace("_", " ")
    if instruction:
        parts += [
            "",
            f"Rewrite ONLY the {named}, following this instruction from the "
            "operator. It is about this post specifically and outranks any "
            "preference for a fresh angle — if it asks for a change to what is "
            "there now, keep the rest of that field:",
            instruction.strip(),
            "",
            "The result must still fit the kept fields above and the brand rules.",
        ]
    else:
        parts += [
            "",
            f"Rewrite ONLY the {named}. Produce a genuinely different one — a "
            "new angle or a new opening, not a reworded copy of what is there "
            "now. It must still fit the kept fields above.",
        ]
    return "\n".join(parts)


def rewrite(
    page: Page,
    source: SourceItem | None,
    topic: str | None,
    field: str,
    keeping: dict[str, str],
    instruction: str | None = None,
    model=None,
):
    """One field again, written to sit with the ones being kept.

    Returns the whole `DraftContent`; the caller takes the field it asked for.
    The model has to return every field because that is the output schema, and
    narrowing the schema per field would be three more types for no gain — what
    matters is that only the requested one is written back to the row.

    The exception is the hook, whose `highlight_phrases` must travel with it.
    They are verbatim substrings of the hook, so phrases chosen for the old one
    match nothing in the new one and render no gold at all — a silent failure
    that looks like the highlight feature being broken.

    `instruction` steers one rewrite and is **not** stored on the Draft and
    **not** turned into a validator: it describes an action, not the post, and a
    brand rule belongs to the Page in `validators.py` where every future draft
    sees it. A stored one would be silently reused by the next press.
    """
    if field not in REGENERATABLE:
        raise ValueError(f"{field!r} is not a field that can be regenerated")
    return _run(
        page,
        rewrite_prompt(source, topic, field, keeping, instruction),
        _field_rules(field),
        model,
    )
