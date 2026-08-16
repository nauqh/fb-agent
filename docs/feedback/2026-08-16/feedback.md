# Client Feedback — 2026-08-16 (round 4)

Sent after round 3's C4/C5 shipped. Numbered `G1`–`G4` here; the client's own
numbering is 1–4, and the letters continue the scheme the earlier rounds used so
that an item is never ambiguous across rounds.

Our reading of each against the code is `comprehension.md` beside this file;
`address.md` gets written as things ship.

---

## Status

| Item | Summary | Status |
|------|---------|--------|
| **G1** | Sort the Sources grid by reactions, not newest | ✅ Shipped 2026-08-16 — both orders, reactions default, windowed so it cannot freeze |
| **G2** | None of the chosen posts generated; no idea which source a draft came from | 🔴 **Three separate causes, one of them large.** Six Pages have **zero** competitors in Metricool, including both Pages this round is about |
| **G3** | Status still says "Pending review" after scheduling to Metricool | ✅ **Already fixed** 2026-08-16 in `000b856`, before this message arrived. Not yet deployed |
| **G4** | Auto-save on edit, or press Save every time? | ❓ A question, not a defect. Auto-save would undo their own round-2 request (A2) |

---

## The feedback, as sent

> @Minh Quân Could you also please check these after you have done other things:
>
> 1. Sort by reaction from top down, not by "newest" please.
> 2. I've just realized NONE from chosen posts were generated, including all
>    post types (vid, image, long caption, etc). I have no idea which source or
>    which competitor posts the tool gens content from.
> 3. Change the status after sent to metricool please. It still says "pending
>    review" after I have scheduled.
> 4. Auto save when edit the text directly or have to press save changes every
>    time?

---

## Itemised

### G1 — Sort by reactions

The Sources grid is `published_at DESC LIMIT 60`. The client wants reactions.

Worth knowing before building: `fetch_competitor_posts` **already sorts by
reactions** — the fetch does what they are asking for, and the grid read then
re-sorts to newest. So this is one `order_by`, not a feature.

But the current order was chosen on purpose and the comment says why. See
`comprehension.md`; the short version is that reactions is a *stable* ranking
over a table nothing prunes, so a straight swap freezes the grid.

### G2 — "NONE from chosen posts were generated"

The headline claim is **not true as stated** and the underlying complaint is
real. 35 of 38 drafts in the database carry a `source_item_id`, all pointing at
plausible competitor posts and RSS items. Generation does use the chosen post.

What is true is that the client cannot **see** any of that, and on the two Pages
they care about most there is genuinely nothing to choose. Three causes,
separated in `comprehension.md`.

### G3 — Status after scheduling

Already fixed, hours before the message arrived, and for exactly the reason they
give. `StatusBadge` keyed on `draft.status`, and pushing to Metricool does not
move the status — so a published post kept its blue **Pending review** pill.
`metricool_post_id` now outranks it and the badge reads **In Metricool**.

**It is not deployed.** The fix is in `000b856` on `main`, unpushed at the time
of writing. Until it ships they will keep seeing the old behaviour, and telling
them it is fixed before it is deployed would be the same mistake round 2 made
about the publish flag.

### G4 — Auto-save

Currently explicit: a **Save changes** button, enabled only when the form
differs from the row.

This is a question rather than a bug report, and the answer is not obviously
"add auto-save" — the current shape exists because of their own round-2
feedback. See `comprehension.md`.
