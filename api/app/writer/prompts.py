"""Prompts live in `api/prompts/*.txt`, not in the database.

They are the product, and they are edited far more often than anything else
here. As database columns they were invisible to git, unreviewable, and they
drifted: in the old system all three configured pages stored the full
2350-character image prompt, of which **2030 characters were byte-identical**,
and those copies went stale — they still said "HERO PHOTO (~75% height)" and
"CIRCLE BRAND LOGO" while the code they were copied from had moved on to a
panel that grows and a logo at natural aspect ratio. History Retraced's stored
overlay prompt carries that same stale block a second time, at offset 903.

As files they diff, review and revert. One page, one file per prompt:

    prompts/system.txt     writer voice and post structure
    prompts/overlay.txt    how to write the panel text and pick highlights
    prompts/image.txt      hero photography style, card layers, exclusions

Read on every call — they are ~5KB total, and editing a prompt should not
require a restart.

`image.txt` was two files until the split was measured against its own rule.
The claim was that hero *style* varies by page while the *card contract* does
not, so they should live apart — but 7 of the 19 lines in the shared half were
History Retraced's taste, not the card's geometry: historical reenactment,
period-accurate dress, no surreal metaphors, mid-shot at 40–60% of frame. The
old system proves those are not universal, because it sent that same block to
Hot Tub Timeout and to a Bible Focus page whose own style block asked for
reverent fine-art photography the shared rules then forbade. A boundary nobody
can place a line on correctly is not a boundary; it had already caused
photorealism, mid-shot and documentary to be stated twice. Merging changed no
bytes — the concatenation this function used to do is now the file.

## Placeholders

A few numbers appear in both a prompt and the compositor, so they are written
as tokens and substituted from `layout.yml`. The old system hardcoded them and
they disagreed in production: History Retraced rendered a 20% panel while its
prompt told the model 25%, because the hint was built from a shared default
constant instead of the page's own value.

Substitution is a plain `str.replace`, not `str.format`, so a stray brace in a
prompt cannot raise at generation time.
"""

from app.settings import API_DIR, Layout

PROMPTS_DIR = API_DIR / "prompts"


def _tokens(layout: Layout) -> dict[str, str]:
    return {
        "{panel_pct}": str(round(layout.panel.ratio * 100)),
        "{highlight_color}": layout.highlight.color,
    }


def _read(name: str, layout: Layout) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
    for token, value in _tokens(layout).items():
        text = text.replace(token, value)
    return text


def system_prompt(layout: Layout) -> str:
    return _read("system.txt", layout)


def overlay_prompt(layout: Layout) -> str:
    return _read("overlay.txt", layout)


def image_prompt(layout: Layout) -> str:
    return _read("image.txt", layout)
