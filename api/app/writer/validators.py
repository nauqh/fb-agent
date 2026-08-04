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
_BIRTH_DEATH = re.compile(r"\(\s*b\.\s*\d{4}|\(\s*\d{4}\s*[-–—]\s*\d{4}\s*\)", re.I)


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
    """Every rule, in reading order. Empty means the draft is compliant.

    All of them are reported at once rather than the first — a retry costs a
    model call either way, so it should carry everything that needs fixing.
    """
    results = [
        hook_length(hook),
        hook_has_no_question(hook),
        recap_point_count(recap),
        recap_lines_start_with_emoji(recap),
        first_comment_paragraphs(first_comment),
        body_length(first_comment),
        birth_death_years(first_comment),
        no_meta_phrases(recap, first_comment),
    ]
    return [reason for reason in results if reason]
