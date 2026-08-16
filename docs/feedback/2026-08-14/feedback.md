# Client Feedback — 2026-08-14

Second round. Sent after the client's staff drove the app themselves for the
first time: publishing times set, posts generated, posts pushed to Metricool.

The first round is `docs/feedback/2026-08-11/`. Item letters continue that
scheme (A regressions, B screens/controls, D publishing, F needs decision) so a
number means the same thing across both rounds.

Our analysis of each item is `comprehension.md` beside this file; what has
shipped is `address.md`.

---

## Status

| Item | Round-1 relative | Summary | Status |
|------|------------------|---------|--------|
| **D3** | shipped 2026-08-11 | Publishing times in Settings | ✅ Confirmed working by the client |
| **A2** | regression in B3 | Rewrite says it worked and the screen does not change | ✅ Fixed 2026-08-14, driven in a browser |
| **B5** | extends B3 | Wants a prompt box: *say how* to rewrite a field | ✅ Shipped 2026-08-14 |
| **B6** | extends A1 | Cannot add a logo for the eight Pages without one | 🔴 API exists, no UI, and the artwork is wrong shape |
| **D5** | new | Everything went to Metricool as a **draft** and never published | ✅ Flag off in prod, verified in the planner 2026-08-16 — 5 posts `PUBLISHED`. 7 pushed under the old flag are stranded (see D6) |
| **D6** | new | Cannot change the image once a post is in Metricool | ❓ By design, but there is no way back at all |
| **F4** | new | Google Alerts as a source — untried | ⏸ Blocked behind B6 in the client's own sequencing |

---

## The feedback, as sent

> 1. I did create the publishing times in Settings. Seemed to work.

> 2. About content generation:
> When I want to re-generate one part of the post, should there be a textbox for
> me to input how I want it to be changed - like a prompt? For example, I want
> to rewrite the overlay text as it was too short and I hit the button, but
> nothing changed even it said "re-generated".

> 3. Scheduling in metricool:
> All posts were "sent" to metricool, but I didn't realize they were in "draft"
> only so they were not published, my bad! I then duplicated and re-scheduled in
> metricool. => So yes, can disable the "draft mode".
> Once the post is "sent" to metricool, I cannot do anything with it inside the
> tool (except for deleting it), only able to edit text and change the time in
> metricool. So if I want to edit the image, what should I do?

> 4. I did check the RSS feeds in the settings pages, but did not create anything
> yet as the BBTT and FR pages have no correct watermark (logo) and I cannot add
> the logos in.

> 5. Google alerts: not tried yet.

---

## Itemised

### D3 — Publishing times (confirmed)

> I did create the publishing times in Settings. Seemed to work.

Shipped 2026-08-11. First round-trip confirmation from a real operator on a
round-1 item. Nothing to do.

### A2 — Rewrite reports success and changes nothing

> I want to rewrite the overlay text as it was too short and I hit the button,
> but nothing changed even it said "re-generated".

"Overlay text" is the **hook** — the line drawn on the picture. The client is
right and the report is precise: the toast fires, the model runs, and neither
the text box nor the preview moves. Client-side only; the row in the database
does change. **It is worse than a no-op** — see `comprehension.md`.

### B5 — A prompt box on rewrite

> should there be a textbox for me to input how I want it to be changed - like a
> prompt?

Yes. Round 1 built rewrite as a button with no argument (B3). "Too short" is the
first real use and the button cannot express it.

### B6 — No way to add a Page's logo

> the BBTT and FR pages have no correct watermark (logo) and I cannot add the
> logos in

BBTT = Bodybuilding Tips, FR = Fitness Recipes. Two of the eight Pages with no
committed watermark asset. The client is blocking their own RSS work on this,
which is the right instinct: a feed that generates posts with the wrong mark
stamped on them is worse than no feed.

### D5 — Draft mode

> I didn't realize they were in "draft" only so they were not published, my bad!
> => So yes, can disable the "draft mode".

Not the client's fault, whatever they say. The flag is ours, it defaults to on,
and **no screen in the app mentions it**.

### D6 — Editing a post already in Metricool

> Once the post is "sent" to metricool, I cannot do anything with it inside the
> tool (except for deleting it), only able to edit text and change the time in
> metricool. So if I want to edit the image, what should I do?

Two facts confirmed by this, both new to us:

- Metricool's own editor can change **text and time but not media**. So ADR-0001's
  "change it in the planner" does not cover the image.
- The client can delete a planner post. They did — duplicating and rescheduling
  by hand. That leaves our rows pointing at posts that no longer exist.

### F4 — Google Alerts

> not tried yet.

No blocker on our side. Held behind B6 by the client's own sequencing.
