# What Was Addressed — 2026-08-16 Feedback

Written as items ship. The request is `feedback.md`, the reading of the code is
`comprehension.md`, and the evidence for each change is its commit message.

---

## G1 — Reactions by default, newest kept beside it ✅

**Shipped 2026-08-16.** `GET /sources/competitors` takes `sort=reactions|newest`,
defaulting to reactions, and the Competitors tab has a two-word toggle.

**The client was right, and here is the size of it.** Measured on History
Retraced's real 1,244-row pool through the running API:

| Sort | Top of grid | Span shown |
|---|---|---|
| `reactions` | **97,080** reactions | 2026-08-07 … 08-13 |
| `newest` | **3** reactions | 2026-08-13 … 08-14 |

The old grid reached back two days and topped out at 2,031 reactions while the
same week held one at 42,738. It was showing the weakest posts in the pool.

`fetch_competitor_posts` had **always** sorted by reactions before returning —
the grid read was the only thing discarding that order, and Metricool's own
Competitors tab ranks the same way. So this restored an order that already
existed rather than inventing one.

**The reactions sort is windowed to `lookback_days`, and that is the load-bearing
part.** The previous newest-first order was a decision, not an oversight, and
its reason still holds: reactions is a *stable* ranking and nothing prunes
`source_item`, so ranking the whole table and taking 60 pins the top of the grid
to whatever went viral weeks ago and a genuinely new post can never enter it.
Measured on the same pool — **42 of the top 60 unwindowed were already older
than the window, against 0 windowed.**

**The window anchors to the newest post in scope, not to `now()`.** The obvious
version subtracts the window from the clock, and that answers with an *empty
grid* for any Page nobody has synced this week — trading a stale ranking for no
ranking at all. An unexplained empty grid is the failure this module already
guards against twice, and it would have hit hardest on the six Pages that have
no competitors. Anchored to the data, the answer is always "the best of the most
recent week we have", and identical whenever the pool is fresh.

That is pinned by `test_a_stale_pool_still_ranks_rather_than_answering_empty`,
which fails on a clock-anchored window: its fixtures are dated 2026-08 and the
suite runs after that.

**Newest stays unwindowed.** Recency *is* the ranking there, so the newest 60 of
a growing pool are recent by construction. A row the reactions window hides is
still reachable by switching to newest — pinned, because hiding a row from one
order must not be mistaken for dropping it from the table.

**Two small things that were not obvious:**

- The hint above the grid moves with the choice — "best of the last 7 days
  first" against "newest first". The window is not independent of the sort, so a
  static sentence would be wrong half the time.
- The choice is component state, not a URL parameter. It is a way of reading one
  grid, not a place to link someone to. It re-queries the server rather than
  re-sorting on the client, because the ranking decides which 60 of 1,244 rows
  come back at all.

**Driven in a browser**, not only in tests: the toggle renders with Reactions
selected, both hints read correctly, the right `sort` parameter goes out on each
press, and the two orders open on 97.1K and 3 reactions.

Suite is **385** (was 382). `tsc` and `eslint src` clean.

**What this does not do.** It does not help the six Pages with no competitors
configured — their grid is empty in either order, which is `G2(a)`. And it does
not fix the used-marker blindness: a fixed 60-row window over a growing pool
still hides most of them, which is `G2(b)` and was always the same problem in a
different shirt.

---

## Still open from this round

`G2` in all three parts — the six Pages with no competitors (theirs to fix in
Metricool, ours to *say*), the used marker invisible outside the window, and no
screen naming the source a Draft came from.

`G3` is **done** (`000b856`) but **not deployed**. It should not be reported to
the client until it is.

`G4` is a question awaiting an answer, not a task. See `comprehension.md`.
