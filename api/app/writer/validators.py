"""The seven brand rules, as pure functions.

Ported from `validation.ts:44` in the old repo, where they ran **after**
generation and were recorded as warnings nobody had to act on. Here they run
inside the writer: a violation raises `ModelRetry` and the model gets another
go, and only what survives the retries reaches the operator as a Warning.

That is the whole difference. A warning that appears after the fact is a note
about a post somebody still has to fix; a retry is a post that comes back
correct. See design.md, "Writer — validation moves inside the interface".

Pure on purpose. Each rule takes strings and returns a reason or `None`, so
they are tested directly rather than through an agent, and the retry wiring in
`agent.py` is the only thing that knows about the model.
"""

import re

HOOK_MAX_WORDS = 65
RECAP_MAX_POINTS = 5
BODY_MIN_CHARS = 1_500
BODY_MAX_CHARS = 2_100
"""The prompt asks for 1,800–1,900; this is the band that triggers a retry.

Deliberately wider than the prompt's target. Retrying a 1,750-character body
that reads well costs a model call to move it inside a range the operator
cannot see, and the old system's own check used these numbers.
"""

FIRST_COMMENT_PARAGRAPHS = (2, 3)

META_PHRASES = ("look back", "as of today", "as we look back")
"""Verbatim from the old repo, minus "2026 look back" — a special case of
"look back" that would have dated itself anyway."""

_EMOJI_START = re.compile(r"^[\s•\-*]*[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")

_ERA = r"(?:AD|BC|BCE|CE)"
_YEAR = rf"(?:\d{{1,4}}\s*{_ERA}|\d{{3,4}})"
"""A year is 3–4 digits, or 1–4 digits when an era marker settles it.

The era is what makes `(69 BC - 30 BC)` safe to accept while `(2 - 3 hours)` is
still not a lifespan.
"""
_DASH = r"[-‒–—―]"
_BIRTH_DEATH = re.compile(
    rf"\(\s*b\.\s*{_YEAR}|\(\s*{_YEAR}\s*{_DASH}\s*{_YEAR}\s*\)", re.I
)
"""Ported from `validation.ts:41`, then widened, because it had to be right here.

The original matched `\\d{4}` with no era suffix. In the old repo that was a
*warning* — "may be missing birth/death years" — so a false negative was noise.
Here the rule raises `ModelRetry`, and a false negative is unsatisfiable: the
writer produced `Wu Zetian (624 – 705 AD)`, was told no years were found,
resubmitted the same correct text twice, and the run died at
`Exceeded maximum output retries`. Every pre-1000 subject on a *history* page
was unwritable.

So: three-digit years, and an optional AD/BC/BCE/CE inside the parentheses.
Moving a rule from warning to blocker raises the bar on its precision — a loose
warning is noise, a loose blocker is a dead run.
"""


def _words(text: str) -> int:
    return len([word for word in text.strip().split() if word])


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def hook_length(hook: str) -> str | None:
    count = _words(hook)
    if count > HOOK_MAX_WORDS:
        return f"The hook is {count} words; it must be under {HOOK_MAX_WORDS}."
    return None


def hook_has_no_question(hook: str) -> str | None:
    if "?" in hook:
        return "The hook must not ask a question. Rewrite it as a statement."
    return None


def recap_point_count(recap: str) -> str | None:
    count = len(_lines(recap))
    if count > RECAP_MAX_POINTS:
        return f"The recap has {count} points; keep it to {RECAP_MAX_POINTS} or fewer."
    return None


def recap_lines_start_with_emoji(recap: str) -> str | None:
    bad = [line for line in _lines(recap) if not _EMOJI_START.match(line)]
    if bad:
        return (
            f"{len(bad)} recap line(s) do not start with an emoji, beginning: "
            f"{bad[0][:40]!r}. Every point needs a related emoji in front."
        )
    return None


def first_comment_paragraphs(first_comment: str) -> str | None:
    low, high = FIRST_COMMENT_PARAGRAPHS
    count = len(_paragraphs(first_comment))
    if not low <= count <= high:
        return f"The first comment has {count} paragraphs; it needs {low}–{high}."
    return None


def body_length(first_comment: str) -> str | None:
    count = len(first_comment)
    if count < BODY_MIN_CHARS:
        return f"The first comment is {count} characters; expand it past {BODY_MIN_CHARS}."
    if count > BODY_MAX_CHARS:
        return f"The first comment is {count} characters; cut it below {BODY_MAX_CHARS}."
    return None


def birth_death_years(first_comment: str) -> str | None:
    """Advisory, not blocking. See `advise`.

    The brand rule is "every person named needs birth/death years". That is not
    checkable without knowing who is a person: a regex can confirm the pattern
    is *present*, never that it is present for everyone, and never that a story
    names nobody at all.
    """
    if not _BIRTH_DEATH.search(first_comment):
        return (
            "No birth/death years found. Every person named needs them: "
            "(1828-1894) for the dead, (b. 1994) for the living."
        )
    return None


def no_meta_phrases(recap: str, first_comment: str) -> str | None:
    haystack = f"{recap}\n{first_comment}".lower()
    found = [phrase for phrase in META_PHRASES if phrase in haystack]
    if found:
        return f"Remove the meta-phrase {found[0]!r}; write it as history, not as a retrospective."
    return None


def check(hook: str, recap: str, first_comment: str) -> list[str]:
    """The blocking rules, in reading order. Empty means the draft is compliant.

    All of them are reported at once rather than the first — a retry costs a
    model call either way, so it should carry everything that needs fixing.

    Every rule here is one the model can *act on and verify*: a word count, an
    emoji, a paragraph break, a character count, a banned phrase. That is the
    admission price for blocking, because a rule that raises `ModelRetry` and
    cannot be satisfied does not warn — it kills the run at
    `Exceeded maximum output retries`. See `advise` for the rest.
    """
    results = [
        hook_length(hook),
        hook_has_no_question(hook),
        recap_point_count(recap),
        recap_lines_start_with_emoji(recap),
        first_comment_paragraphs(first_comment),
        body_length(first_comment),
        no_meta_phrases(recap, first_comment),
    ]
    return [reason for reason in results if reason]


def advise(first_comment: str) -> list[str]:
    """Rules that inform the operator but must never block the writer.

    `birth_death_years` is here because it cannot be made precise. It asks for
    something no regex can confirm — that *every person named* carries years —
    and it fires just as loudly on a story that names no people at all. That is
    not hypothetical: an Atlas Obscura piece about the Zantigo taco chain
    mentions no person, so the rule could not be satisfied by any rewrite, and
    the writer spent both retries resubmitting a correct draft before the run
    died. It is genuinely useful as a nudge and useless as a gate, which is what
    a Warning is for — and how the old repo had it (`validation.ts:100`, "may be
    missing").
    """
    return [reason for reason in [birth_death_years(first_comment)] if reason]


def normalise_hashtags(values: list[str]) -> list[str]:
    """`history` becomes `#history`. A hashtag without its hash is a word.

    The model returns them both ways — `['#DDay', '#WWII']` on one run,
    `['history', 'mystery']` on the next — because the field carried no
    description for most of its life. Saying so in the schema helps and does not
    settle it: an operator editing the box types whatever they type, and that
    path never passed through the model at all.

    So it is fixed here, where both paths meet, rather than asked for twice.
    Internal spaces go because Facebook ends a tag at the first one — `#Bill
    Millin` posts as `#Bill` followed by stray text.
    """
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        tag = "".join(value.split()).lstrip("#")
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        out.append(f"#{tag}")
    return out
