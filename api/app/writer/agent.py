"""The writer: one agent, typed output, brand rules enforced inside.

Callers ask for a draft and get a brand-compliant draft, or an explanation.
They never see a retry. That is the depth that matters most here - the old
system exposed every intermediate state of a six-node graph, and its brand
rules ran afterwards as warnings nobody had to act on.
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import BinaryImage
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
rule is wrong, not the model.
"""


class DraftContent(BaseModel):
    """What the writer returns. Mirrors the columns it fills on `Draft`.

    There used to be an `overlay_text` beside `hook`, described as "the hook
    unless there is reason to differ". There never was a reason: both prompts
    gave them the same rules, and the model returned the same string twice. What
    the split actually bought was a hole - `validators.check` ran on `hook` while
    the compositor drew `overlay_text`, so the panel text was the one thing on
    the post no rule guarded. One field, validated, drawn.
    """

    # These say what each field *is*, and leave the numbers to the prompt.
    #
    # They used to restate them - "Under 65 words", "5-8 short substrings" - and
    # that was survivable while one prompt served every Page. It stops being
    # survivable the moment a Page has its own: Fitness Recipes asks for a
    # 35-word hook and 1-3 highlights, so a description carrying the old numbers
    # sends the model two caps in the same request and lets it pick. The
    # validators are still the backstop; the prompt is the instruction.
    hook: str | None = Field(
        default=None,
        description=(
            "The text drawn on the image panel. No questions. Return null ONLY "
            "when the instructions say this post has NO overlay text - then the "
            "image carries no text panel at all. For any post with an overlay, "
            "this is required."
        ),
    )
    caption: str = Field(description="The recap: at most 5 points, each opening with an emoji.")
    first_comment: str | None = Field(
        default=None,
        description=(
            "The main body, as paragraphs separated by a blank line. Length and "
            "paragraph count are stated in the prompt. Leave it out (null) ONLY "
            "when the instruction says the source is a minimal post - a meme, "
            "quote, recipe card or motivational image with little or no caption "
            "text - and the post must mirror that shape. For a minimal post an "
            "empty first comment is the format, not an omission to fix."
        ),
    )
    highlight_phrases: list[str] = Field(
        description="Short substrings copied verbatim out of the hook. Empty when the hook is null."
    )
    image_prompt: str = Field(
        description=(
            "A photorealistic hero prompt for this story. For a competitor post, "
            "depict the theme of their image - same subject, scene and mood - "
            "composed fresh; never their actual photograph."
        )
    )


def _instructions(page: Page, layout: Layout, template=None) -> str:
    """System prompt, panel rules, how to treat the source, and the post style.

    The last part is the one that cannot be got wrong. `source_instruction`
    decides how the Source Item is read, and every kind now binds the subject:
    telling the model otherwise produces confident, well-formed output about the
    wrong story that nothing downstream catches - which is exactly what the
    competitor-post branch used to do.

    The sentence naming the page used to be the *whole* per-Page dimension of
    this prompt. It is now the fallback: `page.name` also selects
    `prompts/pages/<slug>/`, and a Page with its own files never sees History
    Retraced's voice at all.

    **The lengths are stated only when the Page has changed one.** The prompts
    already carry the house numbers in prose, so repeating them would be a
    second copy to drift - the exact failure `prompts.py` is written against. A
    Page that has asked for 30 words gets a line saying so, and it goes last, so
    it wins over whatever the inherited prose says.

    **A post template layers last of all**, for the same reason the lengths do:
    last wins. It carries only its delta - the fields the style actually
    changes - and says it outranks, which is the same mechanism the minimal-post
    instruction uses and the one that has survived contact with the model. The
    template's text is a delta by construction (see `models.PromptTemplate`),
    so there is no second copy of the house prose here to drift.
    """
    parts = [
        prompts.system_prompt(layout, page.name, page),
        prompts.overlay_prompt(layout, page.name, page),
        f"You are writing for the Facebook page {page.name}.",
    ]
    house = validators.Limits()
    limits = validators.Limits.for_page(page)
    if limits != house:
        low, high = limits.paragraphs
        parts.append(
            "LENGTHS FOR THIS PAGE. These override any length given above.\n"
            f"- The hook must be at most {limits.hook_max_words} words.\n"
            f"- The first comment must be between {limits.body_min_chars:,} and "
            f"{limits.body_max_chars:,} characters.\n"
            f"- The first comment must be {low}-{high} paragraphs."
        )
    # Two ways to opt out, one outcome. The Page's overlay prompt emptied is
    # every draft on the Page; a style's overlay stored as `""` is only the drafts
    # written under that style (client, 2026-09-14). A style's `None` is neither:
    # it uses the Page's overlay prompt, which is what an image-only style that
    # still wants a panel means.
    no_overlay = not prompts.overlay_prompt(layout, page.name, page).strip() or (
        template is not None
        and template.overlay_prompt is not None
        and not template.overlay_prompt.strip()
    )
    if template is not None:
        layers = []
        for label, text in (
            ("SYSTEM", template.system_prompt),
            # Skipped for a no-overlay post, whichever switch said so: layering
            # panel rules for a post that must not carry a panel would only
            # confuse the model.
            ("OVERLAY (text panel rules)", None if no_overlay else template.overlay_prompt),
        ):
            if (text or "").strip():
                layers.append(f"{label}:\n{prompts.substitute(text, layout)}")
        if layers:
            parts.append(
                f"POST STYLE: {template.name}. These instructions outrank "
                "everything above for this draft. Where they change the "
                "structure, lengths or rules above, follow them.\n\n"
                + "\n\n".join(layers)
            )
    if no_overlay:
        # Last, so last wins over the structure above (client, 2026-09-11: an
        # emptied overlay prompt means the post carries no text panel - the
        # image and the logo only).
        parts.append(
            "NO OVERLAY TEXT. This post carries no text panel on the image - "
            "the picture and the page logo are the whole visual. Return null "
            "for `hook` and an empty list for `highlight_phrases`. Ignore any "
            "instruction above that asks for hook or panel text; the caption "
            "and first comment are unchanged."
        )
    return "\n\n".join(parts)


def source_instruction(kind: SourceKind) -> str:
    """How to read the Source Item. Derived from `kind`, never stored.

    **Every kind binds the subject.** A competitor post used to be the exception
    - "a STYLE sample, choose your own subject" - and that is the flow the client
    reported as broken on 2026-08-18: they ticked competitor posts, the run
    reported success, and the drafts were about something else entirely. Nothing
    had failed. The prompt said to do that.

    The exception was inherited from the old app's *comment*
    (`facebookGenerateGraph.ts:389`) rather than its prompt. The prompt one line
    below that comment says "Write ONE original Facebook post **inspired by** this
    competitor post" and then pastes the post - vague enough that the model
    stayed on the subject, which is the behaviour the client has been using for
    months and the one they expect.

    Competitor posts keep a sentence of their own because the risk is real and
    different: their post is the whole finished artefact, so "same story" has to
    be said alongside "not their words". An RSS item has no such pull - nobody
    republishes a Smithsonian article verbatim by accident.

    Their *picture* is still off-limits as a file, and that rule did not move:
    see `generate.build_image`, where `hero_from_source` stays RSS-only. But the
    line used to forbid imitating anything the image looked like, which for a
    meme or a recipe card forbade the theme itself - the one thing a recreation
    is of. The distinction now drawn is theme versus artefact: depict what
    their picture depicts, freshly composed in the page's style; never their
    photograph, crop, baked-in text or card.
    """
    if kind is SourceKind.COMPETITOR_POST:
        return (
            "The source below is a competitor's post about a real story. Write "
            "about that SAME story - the same subject, people and events. Do not "
            "invent a different subject. Do not reuse their wording or their "
            "opening: the story is shared, the writing is ours.\n"
            "Their post's SHAPE is part of the brief. Match it:\n"
            "- A full post - an image with a substantial caption - gets the "
            "standard structure defined above: hook, recap, first comment.\n"
            "- A minimal post - a meme, a quote, a recipe card, a motivational "
            "image with little or no caption text - gets the same minimal shape: "
            "the hook carries the message their image carries, adapted into our "
            "voice and never their exact words; the caption is a few short plain "
            "lines with no emoji list and no invented points; and the first "
            "comment is left out entirely (null). This outranks the structure "
            "defined above. Do not pad a minimal post into an essay - that is "
            "recreating something the source never was.\n"
            "An image of the post may accompany it; read it for the subject, its "
            "details, which shape it is, and the THEME it depicts. The image "
            "prompt must describe a fresh photograph of that same theme - the "
            "same subject, activity, scene and mood their picture shows - "
            "composed in this page's own photographic style, never their actual "
            "photograph, their exact composition or crop, any text baked into "
            "their image, or their card design and branding. Recreating the "
            "theme is the job; reusing the picture itself would be lifting what "
            "the rival shot."
        )
    return (
        "The source below is FACTUAL. Write about this same story, the same "
        "people and the same events. Do not invent a different subject."
    )


def _validator_for(limits: validators.Limits):
    """The output validator, closed over one Page's lengths.

    A closure rather than a module-level function because the numbers are now
    per-Page, and judging a draft against the house numbers while the prompt
    asked for the Page's would fail a rule the model was never given.
    """

    def _validate(_ctx: RunContext, output: DraftContent) -> DraftContent:
        reasons = validators.check(
            output.hook, output.caption, output.first_comment, limits
        )
        if reasons:
            raise ModelRetry(
                "The draft breaks brand rules. Fix all of these and return the whole "
                "draft again:\n- " + "\n- ".join(reasons)
            )
        return output

    return _validate


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
    agent.output_validator(_validator_for(validators.Limits.for_page(page)))
    return agent


"""The chain is `settings.text_fallback_chain` - deployment config, like the
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


def user_contents(prompt: str, image: BinaryImage | None) -> list:
    """The run's content: the text prompt, and the source picture if there is one.

    A text-only run is a bare string (not a one-string list) so existing copy
    and callers read unchanged. With an image, the model gets it in the same
    user turn as the caption, exactly as the old app sent competitor pictures
    to Gemini. Kept here rather than inside `write` so the image can be
    threaded by callers that own the fetch.
    """
    return prompt if image is None else [prompt, image]


def write(
    page: Page,
    source: SourceItem | None,
    topic: str | None = None,
    model=None,
    image: BinaryImage | None = None,
    template=None,
):
    """A brand-compliant draft, or an explanation. Never a retry.

    `image` is the competitor post's own picture, fetched by `generate` and
    sent alongside the text so the model can read it - never a style sample.
    `template` is the run's post style row, layered last in the instructions;
    None is the normal case.

    Two different retries live here and they are not the same thing.
    `ModelRetry` corrects a draft that broke a brand rule - that is the writer
    doing its job. This loop reacts to the model being *unavailable*, which is
    not about the draft at all, and steps down the fallback chain rather than
    asking the same overloaded model again.

    A caller passing `model` gets exactly that model and no fallback: tests
    supply a fake, and silently swapping it for a real one would bill them.
    """
    return _run(
        page,
        user_contents(user_prompt(source, topic), image),
        _validator_for(validators.Limits.for_page(page)),
        model,
        template=template,
    )


def _run(page: Page, prompt, validator, model=None, template=None):
    """Ask the model, stepping down the fallback chain while it is unavailable.

    Extracted so `rewrite` cannot grow a second copy of the ladder - the two
    differ only in what they ask for and which rules they hold the answer to.

    A caller passing `model` gets exactly that model and no fallback: tests
    supply a fake, and silently swapping it for a real one would bill them.
    """
    if model is not None:
        # Built here rather than through `build_agent`, which attaches the
        # whole-draft validator and offers no way to detach it. This used to
        # call it and then rebuild when the validator differed, testing
        # `validator is not _validate` - an identity check that stopped meaning
        # anything once the validators became per-Page closures. Constructing
        # with the validator the caller asked for is what both branches wanted.
        agent = Agent(
            model,
            output_type=DraftContent,
            instructions=_instructions(page, layout, template),
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
                instructions=_instructions(page, layout, template),
                model_settings=_model_settings(name),
                retries=MAX_RETRIES,
            )
            agent.output_validator(validator)
            return agent.run_sync(prompt)
        except Exception as error:
            if not is_transient(error):
                raise
            last = error

    assert last is not None
    raise last


REGENERATABLE = ("hook", "caption", "first_comment")
"""The three fields the operator can ask for again, one at a time.

`highlight_phrases` is not on the list and cannot be: it is defined as verbatim
substrings *of the hook*, so it has no meaning apart from one. It rides along
when the hook is rewritten - see `rewrite`.

`image_prompt` is not here either. Re-rolling it changes nothing on its own; the
picture is bought by `POST /drafts/{id}/image?new_hero=true`, and the prompt is
editable by hand for exactly that purpose.
"""


def _field_rules(field: str, limits: validators.Limits | None = None):
    """The blocking rules that apply to **one** field, as an output validator.

    The whole-draft validator cannot be reused here. It checks all three fields,
    and on a rewrite the other two come from the row unchanged - so a draft that
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
                validators.hook_length(content.hook, limits),
                validators.hook_has_no_question(content.hook),
            ]
        elif field == "caption":
            # A minimal post's caption is plain lines; the emoji convention only
            # exists on a story post, signalled by the body being present.
            minimal = not (content.first_comment or "").strip()
            found = [validators.recap_point_count(content.caption)]
            if not minimal:
                found.append(validators.recap_lines_start_with_emoji(content.caption))
            found.append(validators.no_meta_phrases(content.caption, ""))
        else:
            found = [
                validators.first_comment_paragraphs(content.first_comment, limits),
                validators.body_length(content.first_comment, limits),
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
    regenerated in isolation is a caption for a different post - it would not
    open on the hook that is drawn on the picture above it, and the operator
    would be handed two halves that do not meet. Showing the model what stays is
    what makes the new field fit the old ones.

    `instruction` is the operator's own line, and it **replaces** the demand for
    novelty rather than joining it. The two contradict each other: "produce a
    genuinely different one" answers *this is not the post I want*, while "make
    it longer" answers *this is the post I want, said better*. The client's first
    real use was a hook that was too short - no rule anywhere sets a minimum, so
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
            "preference for a fresh angle - if it asks for a change to what is "
            "there now, keep the rest of that field:",
            instruction.strip(),
            "",
            "The result must still fit the kept fields above and the brand rules.",
        ]
    else:
        parts += [
            "",
            f"Rewrite ONLY the {named}. Produce a genuinely different one - a "
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
    template=None,
):
    """One field again, written to sit with the ones being kept.

    Returns the whole `DraftContent`; the caller takes the field it asked for.
    The model has to return every field because that is the output schema, and
    narrowing the schema per field would be three more types for no gain - what
    matters is that only the requested one is written back to the row.

    The exception is the hook, whose `highlight_phrases` must travel with it.
    They are verbatim substrings of the hook, so phrases chosen for the old one
    match nothing in the new one and render no gold at all - a silent failure
    that looks like the highlight feature being broken.

    `template` is the draft's post style (see `write`). A rewrite in a different
    voice than the draft was written in is how a meme field gets regenerated as
    an essay - the stored id, not the operator's current dropdown, decides.

    `instruction` steers one rewrite and is **not** stored on the Draft and
    **not** turned into a validator: it describes an action, not the post, and a
    brand rule belongs to the Page in `validators.py` where every future draft
    sees it. A stored one would be silently reused by the next press.

    **No image part, and that is deliberate.** `write` sends the competitor
    post's own picture to the model as vision input; this does not, matching the
    old app, whose regenerate sent `buildDraftContext(draft)` and never an image
    (`facebookDraftRegenerateService.ts`). The picture is not lost by leaving it
    out: `keeping` puts the other two fields in the prompt verbatim, and those
    were written while the model could see it, so whatever the image contributed
    to the subject is already in front of this call as prose. Sending it again
    would buy a CDN fetch and vision tokens on every press of a button the
    operator presses repeatedly, for detail the prompt already carries.
    """
    if field not in REGENERATABLE:
        raise ValueError(f"{field!r} is not a field that can be regenerated")
    return _run(
        page,
        rewrite_prompt(source, topic, field, keeping, instruction),
        _field_rules(field, validators.Limits.for_page(page)),
        model,
        template=template,
    )
