"""Telling "ask again" apart from "this request is wrong".

Shared because both paid calls hit the same wall. The writer met it first and
steps down its fallback chain (`writer/agent.py`); the hero retries the same
model (`image/hero.py`). What counts as transient is one question, so it has one
answer here rather than a copy on each side that drifts.
"""

import re

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
