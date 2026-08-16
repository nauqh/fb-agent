# Round 4, read against the code

Written before building anything, because two of these four items are not what
their one-line summary suggests and one of them is already done.

Every number below was measured against the live database or a live Metricool
read on 2026-08-16, not inferred.

---

## G1 — Sort by reactions

**Where it is.** `routes/sources.py:207`, `order_by(SourceItem.published_at.desc())`
with `.limit(sources_config.competitors.grid_limit)` — 60, from `config/sources.yml`.

**The fetch already does what they ask.** `sources/metricool.py:145` sorts by
reactions before returning, and its docstring says "Ordered by reactions, which
is the Competitors tab's default sort". The reaction order is thrown away by the
grid read. So the client is asking for the order Metricool's own screen uses and
that our fetch already produces.

**But the current order was a decision, and the reason is still true.** The
comment at `sources.py:196-206` argues: reactions is a *stable* ranking, so the
same winners sit at the top every day; nothing prunes `source_item`; so once 60
older posts out-perform this week's, a genuinely new post can never enter the
grid at all.

That is not theoretical. History Retraced's pool is **1,244 competitor posts**
and growing daily against a 60-row window.

**So a straight swap trades one real problem for another.** Newest-first means
the client cannot find the best post. Reactions-first means they see the same
sixty forever.

**Cheapest honest shape: make it a control, not a constant.** A sort toggle on
the grid — the operator picks, the default stays newest. Reactions-first then
also needs the window bounded by *time* rather than by row count, or the top of
the grid is frozen at whatever went viral in July.

Worth asking whether they want it as the default or as a toggle; the message
reads like a default.

---

## G2 — "NONE from chosen posts were generated"

The strongest claim in the round and the one most worth taking apart, because
the literal statement is false and the complaint underneath it is not.

**Generation does use the chosen post.** Measured:

```
drafts: 38
  from a source item : 35
  from a topic       :  3
  neither            :  0
```

Every one of the 35 resolves to a real row — competitor posts from Ancient
Files, Witty Historian, The Vintage News, and RSS items from Fitness Volt and
Boxrox. `generate.py:114` sets `source_item_id`, `_run_one` loads it back. The
wiring is not broken.

So the client is describing something else, and there are **three** separate
mechanisms. They need separating because only one of them is a bug in our code.

### (a) Six Pages have no competitors at all — including both Pages this round is about

Live read of `fetch_competitors` for all ten Pages:

| Page | Competitors |
|---|---|
| History Retraced | 22 |
| The Fact Feed | 26 |
| Fitness Girls | 27 |
| Bible Focus | 17 |
| **Bodybuilding Tips N Tricks** | **0** |
| **Fitness Recipes** | **0** |
| GYM Motivation | 0 |
| GYM Motivation \| quotes \| … | 0 |
| Hot Tub Timeout | 0 |
| House of Common Sense | 0 |

`fetch_competitor_posts` returns **0 rows** for every Page in the second group.
Their Sources grid is empty, so nothing can be chosen and nothing can be
generated from a competitor post. If the client was working on Bodybuilding Tips
or Fitness Recipes — the two Pages the whole of round 3 was about — then "NONE
from chosen posts were generated" is exactly what they would see, and it is
correct.

**This is not ours to fix in code.** Competitors are configured in Metricool,
and their account is nearly full: 22 + 26 + 17 + 27 = **92 of 100**, which is
the "8 left of 100" the Global screen already shows. Six Pages cannot be given a
competitor set without taking the allowance from somewhere.

That constraint is already understood in this codebase — it is why
`synced_for_page_id` is provenance rather than ownership and why
`page_competitor` exists. What is missing is that **no screen says a Page has no
competitors**; an empty grid looks identical to a quiet week. `_feeds_for` has
exactly this reasoning written above it for feeds, and the same argument applies
here.

### (b) The "used" marker is invisible almost everywhere

`_with_used` flags source items a Draft already came from, so the grid stops
re-offering them. It works. But it is computed over rows the grid has already
truncated to the newest 60:

```
History Retraced   pool 1244  grid 60  used-in-pool 25  used-VISIBLE-in-grid  3
The Fact Feed      pool  655  grid 60  used-in-pool  2  used-VISIBLE-in-grid  0
```

So 22 of History Retraced's 25 used posts, and both of The Fact Feed's, are
marked in a part of the table the operator is never shown. The client generates
from a post, comes back, and sees no marker — which reads exactly as "it didn't
use it".

This is entangled with G1: any fixed-size window over a pool that grows daily
loses the markers within days, whatever the sort.

### (c) Nothing on the Draft says where it came from

`Draft.source_item_id` is on the row and is returned by the API. No screen
renders it. There is no link from a draft back to the competitor post it was
written from, which is the literal second sentence of the client's message: "I
have no idea which source or which competitor posts the tool gens content from."

This is the cheapest of the three to fix and probably the most valuable: a line
on the Review drawer naming the author and linking `SourceItem.url`.

### On "including all post types (vid, image, long caption, etc)"

**We cannot answer this from Metricool's data.** Their `/posts` rows do carry a
`type` key — and `videoViews`, `videoTimeWatched` beside it — but on a live read
of 500 History Retraced rows `type` was **null on all 500**. It is present and
unpopulated. So we cannot label a post as video or photo even if we wanted to,
and any "post type" filter would be built on a field Metricool does not fill.

The one type-shaped filter we *do* apply is `sources/metricool.py:143`: a post
with no text is dropped, because there is no voice to borrow from and `postId`
is the dedup key. Measured across the four Pages that return anything:

| Page | Fetched | Kept | Dropped, no text |
|---|---|---|---|
| History Retraced | 500 | 499 | 1 |
| The Fact Feed | 500 | 450 | 50 |
| Bible Focus | 500 | 437 | 63 |
| Fitness Girls | 500 | 481 | 19 |

Small, but not nothing, and silent. A pure-video post with no caption is
invisible to the client with no explanation — which is a second reason the
grid's contents do not match what they saw in Metricool.

---

## G3 — Status after scheduling

**Already fixed**, `000b856`, earlier the same day and before this message
arrived. Found by reading the planner rather than by report: fourteen drafts
carry a `metricool_post_id`, five are `PUBLISHED` on Facebook, and all fourteen
were rendering a blue **Pending review** pill.

`StatusBadge` keyed on `draft.status` alone, and pushing does not move the
status — approve is queue movement only, round 1's D1. `metricool_post_id` now
outranks it and the badge reads **In Metricool**.

"In Metricool" rather than "Published" because the Review screen cannot tell:
seven of those fourteen are still `draft=true` in the planner with publication
dates three days past and will never go out. The Schedule screen reads the
planner and is the only one that can say `Published` / `Draft` / `Error`.

**Not deployed.** Saying "fixed" to the client before it ships would repeat
round 2's mistake with the publish flag exactly.

---

## G4 — Auto-save

**Currently explicit.** `draft-detail.tsx` holds a `form`, computes `dirty` by
comparing it to the row, and enables **Save changes** only when they differ.
**Revert** discards.

**Auto-save would delete a contract the client themselves asked for.** Round 2's
A2 was "Rewrite says it worked and the screen does not change". The fix made the
rule *Rewrite proposes, Save writes, Revert undoes*: a rewrite lands in the form,
not the database, so the operator sees the proposal, keeps it or throws it away.
That only works because there is a save step. With auto-save, a paid Gemini
rewrite is committed the instant it returns and Revert has nothing to revert to.

**So the honest answer to their question is "you press Save, and here is why".**
If the friction is real, the fix is probably not auto-save but making the unsaved
state louder — the button is already gated on `dirty`, so a screen that shouts
when it is dirty costs nothing and loses nothing.

Worth asking what prompted it: losing work by navigating away is a different
problem from finding the click annoying, and only the first is worth code.

---

## Sequencing

**G3 needs nothing but a deploy.** It is done. Push it.

**Then G2(c) — name the source on the Draft.** Small, self-contained, no client
input needed, and it answers the literal question they asked. Nothing else in
this round is as cheap per unit of complaint addressed.

**Then G2(a) — say when a Page has no competitors.** Also small: an empty grid
that explains itself. Does not fix the allowance problem, but stops it being
invisible, and it is the actual reason their two focus Pages generate nothing.

**G1 and G2(b) together, or not at all.** They are the same problem — a fixed
window over a growing pool — and fixing the sort without the window makes the
used-marker blindness worse rather than better.

**G4 is a reply, not a task.** Answer it before building anything.

---

## Questions for the client

1. **G1** — reactions as the *default*, or as a toggle beside "newest"? The
   message reads like a default, but the grid is capped at 60 rows over a
   1,244-row pool, so a reactions default will show the same posts every day
   unless we also bound it by time. How many days back should it look?
2. **G2** — **were you working on Bodybuilding Tips or Fitness Recipes?** Both
   have zero competitors configured in Metricool, so their Sources grid is empty
   by definition. This is the most likely explanation for the whole item and we
   should confirm it before building anything else.
3. **G2** — Metricool's competitor allowance is 92 of 100 spent across four
   Pages. Which Pages should hold the remaining 8, or which existing competitors
   should be dropped to make room? This is their decision, not ours.
4. **G2** — "all post types (vid, image, long caption)": Metricool returns
   `type` as null on every row we have seen, so we cannot label them. Is it
   enough to show the reaction/comment/share counts already on the card, or is
   the post type itself load-bearing for the choice?
5. **G4** — what went wrong that prompted the question? Lost edits, or just the
   extra click?
