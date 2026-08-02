"""Prompt fragments that are the same for every Page.

Only the page-specific part of a prompt lives in the `page` table. Everything
identical across pages lives here, because the old system proved what happens
otherwise: all three configured pages stored the full 2350-character image
prompt, of which **2030 characters were byte-identical**. Those copies then
went stale — the stored versions still say "HERO PHOTO (~75% height)" and
"CIRCLE BRAND LOGO", while the code they were copied from had since changed to
a panel that grows and a logo at natural aspect ratio. Three rows drifted from
one constant, silently, and the model kept being told the old thing.

So: the shared block is code, the page-specific block is data.
"""

from app.settings import Layout

HERO_RULES = """Hero composition rules:
- Full-bleed photorealistic photograph edge to edge — no letterboxing or post mockup.
- Must look like a real camera photo (documentary, editorial, or historical reenactment photography).
- COMPOSITION: mid-shot or medium close-up — main subjects fill ~40–60% of frame height (~50% larger than a wide panorama). Not tiny distant figures.
- FOCAL POINT: 1–3 faces or figures clearly visible in the foreground as the visual hook (reenactment faces OK). Prefer subjects facing or near the camera.
- When people appear: believable anatomy and period-accurate dress; faces must be readable at feed size.
- Keep the entire top-right quadrant clean — a brand logo is composited there in post.
- NO surreal metaphors (giant objects, glowing silhouettes, fantasy props, comic or illustrated style).

Strict exclusions — your image must contain NONE of these:
- ANY readable text, letters, numbers, captions, titles, headline typography, or hashtags (including #tags painted in the image)
- ANY social-media post mockup: black bars, text panels, meme layout, or card framing
- ANY brand names, logos, watermarks, or channel name text
- Black text box, speech bubbles, UI chrome, or post mockup frames
- Circular frames, medallions, round profile photos, or logo badges drawn in the photo
- Digital illustration, cartoon, anime, 3D render, or "AI art" look — photograph only
- Wide establishing shots where people are small specks in the distance"""


def card_layers_hint(layout: Layout) -> str:
    """Tell the model what it is *not* drawing.

    The percentage comes from `panel_ratio`, so the prompt and the compositor
    cannot disagree. In the old system they already did: History Retraced
    rendered at 0.20 while its prompt hint said 25%, because the hint was built
    from a shared default constant rather than the page's own value.
    """
    panel_pct = round(layout.panel.ratio * 100)
    return f"""Final post card assembly (layers 2–3 are added in code — do NOT draw them):
1. HERO PHOTO (top portion — shrinks when copy is long) — YOU generate only this: full-bleed photorealistic photograph, square output, no UI, no text.
2. BLACK TEXT BOX (bottom, at least ~{panel_pct}% of card height, grows to fit copy) — solid black panel with white/gold copy (added in code).
3. BRAND LOGO — uploaded brand logo (natural aspect ratio), top-right corner of the hero (added in code). Leave top-right empty in your photo.

Your output must be layer 1 only — a clean photograph with zero text and zero logos."""


def build_image_prompt(page_image_prompt: str, layout: Layout) -> str:
    """The page's visual-style block, then the rules every page shares."""
    return "\n\n".join(
        [page_image_prompt.strip(), card_layers_hint(layout), HERO_RULES]
    )
