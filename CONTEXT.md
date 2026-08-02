# Facebook Agent

Generates Facebook posts for a fixed set of owned Facebook pages by drawing on
external material — rival posts, tweets, and news articles — then hands approved
posts to Metricool for scheduling and publishing.

## Language

**Page**:
One of the owned Facebook pages the agent publishes to. Owns its daily quota,
its three prompts, and its watermark. It does *not* own styling — every Page
renders in the same form and size. Four are active.
_Avoid_: Brand, brand key, `hr`/`tff`/`bf`/`htt`, blog

**Source Item**:
A piece of external material selected as input for generation. Exactly three
kinds exist: a rival post, a tweet, or an article.
_Avoid_: Competitor post, inspiration post, feed item, viral post

**Rival**:
A Facebook page, not owned by us, whose posts are synced from Metricool and used
as Source Items. Which pages are Rivals is configured in Metricool, not here —
the agent stores their posts, never the list itself.
_Avoid_: Competitor

**Style Source**:
A Source Item whose *subject is not binding* — it is borrowed for tone and
structure only. Rival posts are Style Sources.

**Factual Source**:
A Source Item whose *subject is binding* — the generated post must be about the
same story, people, and events. Tweets and articles are Factual Sources.
Confusing the two tells the model to treat a Smithsonian article as a writing
sample.

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

**Composed Image**:
The final post image: a generated hero image with the text panel, highlighted
phrases, and page watermark rendered over it. There is exactly one form — a hero
photo above a black text panel — at one size, 896×1120, identical for every
Page. Only the watermark differs. No headline badge; it belonged to the cut
`full_overlay` layout.
_Avoid_: Overlay, composite, thumbnail, card, layout

**Highlight Phrase**:
An exact substring of the panel text, copied verbatim by the writer, rendered in
gold on the Composed Image.

**Quota**:
The maximum number of posts a Page may publish in one calendar day, in
Asia/Ho_Chi_Minh time.
