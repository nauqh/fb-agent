# Facebook Agent

Generates Facebook posts for a fixed set of owned Facebook pages by drawing on
external material — competitor posts, tweets, and RSS items — then hands approved
posts to Metricool for scheduling and publishing.

## Language

**Page**:
One of the owned Facebook pages the agent publishes to. Owns its watermark. It
does *not* own styling — every Page renders in the same form
and size — and it no longer owns its prompts, which are files. v1 has exactly
one: History Retraced.
_Avoid_: Brand, brand key, `hr`/`tff`/`bf`/`htt`, blog

**Source Item**:
A piece of external material selected as input for generation. Exactly three
kinds exist: a competitor post, a tweet, or an RSS item.
_Avoid_: Inspiration post, viral post, article

**Competitor**:
A Facebook page, not owned by us, whose posts are synced from Metricool and used
as Source Items. Which pages are Competitors is configured in Metricool, not
here — the agent stores their posts, never the list itself.

The word is Metricool's own: the endpoint is `/analytics/competitors`, and its
tables were `social_competitors` and `competitor_posts`. Naming it anything else
means translating at every boundary, in both directions, forever.
_Avoid_: Rival

**RSS Item**:
A Source Item from one of a Page's curated feeds. The feeds are configured in
`api/config/sources.yml`, per Page, because the beats do not overlap.
_Avoid_: Article, news item, feed item

**Binding subject**:
Every Source Item's subject binds: the generated post is about that same story,
those same people, those same events. There is no kind that is borrowed for tone
alone.

There was, until 2026-08-18 — competitor posts were "Style Sources", and the
writer was told to pick its own story. The client read that as the tool ignoring
the posts they had chosen, which is what it looks like from the outside. Both
terms are retired; only the sentence handed to the model differs by kind now
(`writer.agent.source_instruction`), and a competitor's differs only in also
saying not to borrow their words.
_Avoid_: Style Source, Factual Source, inspiration

**Cart**:
The set of Source Items currently ticked for the next generation run.
_Avoid_: Inspiration, selection, basket

**Draft**:
A generated post awaiting human review. Carries the hook, caption, first
comment, overlay text, and its composed image. One Source Item yields one Draft
per targeted Page.
_Avoid_: Post, generation, candidate

**Approve**:
The act of accepting a Draft as ready to publish. The agent holds no schedule
state of its own — once a Draft leaves for Metricool, Metricool's planner is the
sole source of truth for what is queued.
_Avoid_: Schedule, publish, queue

**Warning**:
A brand rule the writer still broke after its retries were spent. Warnings are
residue, not advice — every rule is enforced first, and one only becomes a
Warning once it has survived correction. Shown against the Draft for the
operator to judge; it never blocks Approve.

**Composed Image**:
The final post image: a generated hero image with the text panel, highlighted
phrases, and page watermark rendered over it. There is exactly one form — a hero
photo above a black text panel — at one size, 896×1120. Nothing about it is
per-Page except which watermark file is stamped on. No headline badge; it
belonged to the cut `full_overlay` layout.
_Avoid_: Overlay, composite, thumbnail, card, layout

**Highlight Phrase**:
An exact substring of the panel text, copied verbatim by the writer, rendered in
gold on the Composed Image.

**Repost**:
A Draft that reproduces a post that already went out — the caption, first
comment and picture as they were published, copied from Metricool's planner at
repost time. Distinct from Write again, which sends the story back through the
writer for fresh copy and a fresh picture. A Repost has no hook and no hero:
the hook was drawn into the picture that is being reused.
_Avoid_: Copy, duplicate, clone

