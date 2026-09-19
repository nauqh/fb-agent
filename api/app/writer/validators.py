"""The seven brand rules, as pure functions.

Ported from `validation.ts:44` in the old repo, where they ran **after**
generation and were recorded as warnings nobody had to act on. Here they run
inside the writer: a violation raises `ModelRetry` and the model gets another
go, and only what survives the retries reaches the operator as a Warning.

That is the whole difference. A warning that appears after the fact is a note
about a post somebody still has to fix; a retry is a post that comes back
correct. See design.md, "Writer - validation moves inside the interface".

Pure on purpose. Each rule takes strings and returns a reason or `None`, so
they are tested directly rather than through an agent, and the retry wiring in
`agent.py` is the only thing that knows about the model.
"""

import re
from dataclasses import dataclass

HOOK_MAX_WORDS = 65
RECAP_MAX_POINTS = 5
BODY_MIN_CHARS = 1_500
BODY_MAX_CHARS = 2_100
"""The prompt asks for 1,800-1,900; this is the band that triggers a retry.

Deliberately wider than the prompt's target. Retrying a 1,750-character body
that reads well costs a model call to move it inside a range the operator
cannot see, and the old system's own check used these numbers.
"""

FIRST_COMMENT_PARAGRAPHS = (2, 3)


@dataclass(frozen=True)
class Limits:
    """The lengths one Page writes to. The constants above are the house set.

    A value object rather than more parameters because the four numbers travel
    together everywhere - the writer needs them to build the prompt, the check
    needs them to judge the result, and a rule that judged against different
    numbers than the prompt asked for is the C7 trap in a new place.

    `Limits()` is History Retraced and every Page that has not asked for
    anything else, so existing callers and tests read the same as before.
    """

    hook_max_words: int = HOOK_MAX_WORDS
    body_min_chars: int = BODY_MIN_CHARS
    body_max_chars: int = BODY_MAX_CHARS
    paragraphs: tuple[int, int] = FIRST_COMMENT_PARAGRAPHS
    recap_max_points: int = RECAP_MAX_POINTS
    recap_emoji: bool = True
    """The caption's two rules, per Page since 2026-09-19.

    They were the only part of a post no Page could change, and the gap was
    not theoretical: `prompts/pages/fitness-recipes/system.txt` says "no limit
    on the number of the points" for a recipe, and a recipe draft with seven
    points was retried back down to five by a module constant. A rule the
    operator wrote, silently losing to one they could not see.
    """

    @classmethod
    def for_page(cls, page) -> "Limits":
        """Resolve a Page's overrides over the house numbers. Null inherits.

        Takes the Page rather than living on it so that `validators` stays free
        of the models - the rules are pure functions and tested as such, which
        is the property the module docstring is about.
        """
        low, high = FIRST_COMMENT_PARAGRAPHS
        return cls(
            hook_max_words=page.hook_max_words or HOOK_MAX_WORDS,
            body_min_chars=page.first_comment_min_chars or BODY_MIN_CHARS,
            body_max_chars=page.first_comment_max_chars or BODY_MAX_CHARS,
            paragraphs=(
                page.first_comment_min_paragraphs or low,
                page.first_comment_max_paragraphs or high,
            ),
            recap_max_points=page.recap_max_points or RECAP_MAX_POINTS,
            # `or` would read False as unset, which is the one value this
            # column exists to carry.
            recap_emoji=True if page.recap_emoji is None else page.recap_emoji,
        )

    def disagrees(self) -> str | None:
        """Why this set could never be satisfied, or `None`.

        C7 asked for a 1,500-character ceiling while 1,500 was the global floor:
        a band of zero width, where every draft fails one end or the other,
        burns both retries and dies at `Exceeded maximum output retries`. That
        is unbuildable rather than strict, and it is the reason C7 sat dropped
        for two days. The screen that sets these numbers has to say so before
        they are saved, not after a run dies.
        """
        if self.body_min_chars > self.body_max_chars:
            return (
                f"The first comment cannot be both over {self.body_min_chars:,} and "
                f"under {self.body_max_chars:,} characters."
            )
        low, high = self.paragraphs
        if low > high:
            return f"The paragraph range is backwards: {low}-{high}."
        if self.hook_max_words < 5:
            return f"A {self.hook_max_words}-word hook is not writable."
        if self.recap_max_points < 1:
            return "A caption needs at least one point."
        return None

META_PHRASES = ("look back", "as of today", "as we look back")
"""Verbatim from the old repo, minus "2026 look back" - a special case of
"look back" that would have dated itself anyway."""

_EMOJI_START = re.compile(r"^[\s•\-*]*[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")


def _words(text: str) -> int:
    return len([word for word in text.strip().split() if word])


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def hook_length(hook: str, limits: Limits | None = None) -> str | None:
    cap = (limits or Limits()).hook_max_words
    count = _words(hook)
    if count > cap:
        return f"The hook is {count} words; it must be under {cap}."
    return None


def hook_has_no_question(hook: str) -> str | None:
    if "?" in hook:
        return "The hook must not ask a question. Rewrite it as a statement."
    return None


def recap_point_count(recap: str, limits: Limits | None = None) -> str | None:
    cap = (limits or Limits()).recap_max_points
    count = len(_lines(recap))
    if count > cap:
        return f"The recap has {count} points; keep it to {cap} or fewer."
    return None


def recap_lines_start_with_emoji(recap: str) -> str | None:
    bad = [line for line in _lines(recap) if not _EMOJI_START.match(line)]
    if bad:
        return (
            f"{len(bad)} recap line(s) do not start with an emoji, beginning: "
            f"{bad[0][:40]!r}. Every point needs a related emoji in front."
        )
    return None


def first_comment_paragraphs(
    first_comment: str, limits: Limits | None = None
) -> str | None:
    low, high = (limits or Limits()).paragraphs
    count = len(_paragraphs(first_comment))
    if not low <= count <= high:
        return f"The first comment has {count} paragraphs; it needs {low}-{high}."
    return None


def body_length(first_comment: str, limits: Limits | None = None) -> str | None:
    resolved = limits or Limits()
    count = len(first_comment)
    if count < resolved.body_min_chars:
        return (
            f"The first comment is {count} characters; expand it past "
            f"{resolved.body_min_chars}."
        )
    if count > resolved.body_max_chars:
        return (
            f"The first comment is {count} characters; cut it below "
            f"{resolved.body_max_chars}."
        )
    return None


def no_meta_phrases(recap: str, first_comment: str) -> str | None:
    haystack = f"{recap}\n{first_comment}".lower()
    found = [phrase for phrase in META_PHRASES if phrase in haystack]
    if found:
        return f"Remove the meta-phrase {found[0]!r}; write it as history, not as a retrospective."
    return None


def check(
    hook: str | None,
    recap: str,
    first_comment: str | None,
    limits: Limits | None = None,
) -> list[str]:
    """The blocking rules, in reading order. Empty means the draft is compliant.

    All of them are reported at once rather than the first - a retry costs a
    model call either way, so it should carry everything that needs fixing.

    Every rule here is one the model can *act on and verify*: a word count, an
    emoji, a paragraph break, a character count, a banned phrase. That is the
    admission price for blocking, because a rule that raises `ModelRetry` and
    cannot be satisfied does not warn - it kills the run at
    `Exceeded maximum output retries`.

    A blank first comment is not a broken draft - it is a minimal post (see
    `source_instruction`): image plus a short caption, no body. The essay rules
    cannot judge a shape with no essay in it, so only the hook, the caption's
    line count and the meta-phrase ban are enforced; the emoji rule is a
    story-post convention and a character floor on a quote would be a dead run.

    A Page that has turned the emoji rule off skips it everywhere, for the
    same reason the numbers are per-Page: a rule the operator did not ask for,
    enforced against the prompt they wrote, is not a brand rule.

    A blank hook is not a broken draft either (client, 2026-09-11): it is the
    no-overlay opt-out, a post whose image carries no text panel. The hook rules
    cannot judge a shape with no panel text, so they are skipped; the caption
    and body rules still run.
    """
    has_hook = bool((hook or "").strip())
    hook_rules = (
        []
        if not has_hook
        else [hook_length(hook, limits), hook_has_no_question(hook)]
    )
    emoji_rule = (limits or Limits()).recap_emoji
    if not (first_comment or "").strip():
        results = [
            *hook_rules,
            recap_point_count(recap, limits),
            no_meta_phrases(recap, ""),
        ]
    else:
        results = [
            *hook_rules,
            recap_point_count(recap, limits),
            recap_lines_start_with_emoji(recap) if emoji_rule else None,
            first_comment_paragraphs(first_comment, limits),
            body_length(first_comment, limits),
            no_meta_phrases(recap, first_comment),
        ]
    return [reason for reason in results if reason]
