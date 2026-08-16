# Client Feedback — 2026-08-15

Third round. Sent after the logos landed (B6) and the client generated their
first real drafts for the two new Pages: **BBTT** (Bodybuilding Tips) and **FR**
(Fitness Recipes).

Every item is one complaint: **the app writes and draws in History Retraced's
voice for every Page.** That is not a bug in any one place — it is the shape of
`api/prompts/*.txt`, which is one global set of files with no per-Page
dimension, and of `writer/validators.py`, whose numbers are module constants.

Earlier rounds are `docs/feedback/2026-08-11/` and `docs/feedback/2026-08-14/`.
Item letters continue that scheme (C generation options, F needs a decision), so
a letter means the same thing across all three rounds.

Our reading of each item against the code is `comprehension.md` beside this
file; `address.md` gets written as things ship.

---

## Status

| Item | Summary | Status |
|------|---------|--------|
| **B6** | Logos / watermarks | ✅ Confirmed done by the client |
| **C4** | Overlay text in ALL CAPS for BBTT and FR, and nowhere to set it | ✅ Shipped 2026-08-15 — per-Page `text_uppercase`, applied at draw time |
| **C5** | Hero should be modern, bright, fitness-magazine — not sepia history | ✅ Shipped 2026-08-16 — per-Page prompts in `api/prompts/pages/<slug>/`. BBTT's are **drafted, not the client's**, and need approval |
| **C6** | Hook: straight to the point, no year/event/character scaffolding, ≤30 words | ⛔ **Dropped 2026-08-16, the operator's call.** The scaffolding half already shipped with C5; the word cap is not being enforced — `HOOK_MAX_WORDS` stays 65 |
| **C7** | First comment: ≤1,500 chars, 3–4 short paragraphs, straight to content | ⛔ **Dropped 2026-08-16, the operator's call.** Not built. Left here rather than deleted: it is a written client request, and a tracker a request can vanish from is not a record |
| **F5** | The client already wrote new prompts in the **old** tool's Settings tab | ✅ Read 2026-08-16 — `old-tool-prompts.md`. FR has a real spec; **BBTT has none** |

C4–C7 all resolve to the same missing thing, so they are best read together:
see "One voice, ten Pages" in `comprehension.md`.

---

## The feedback, as sent

> @Minh Quân Logos done.
>
> 1. However, could you please set the overlay text to ALL CAPITAL LETTERS for
> BBTT and FR pages? As this is the current style we've been using. I can't see
> anywhere to change this.
>
> 2. And any way to slightly change few things to better fit these 2 pages
> style? Because the original prompts were for the history page, so the approach
> is not quite suitable.
>
> a. Hero image should be modern with bright lighting, fitness lifestyle
> magazine style. The draft posts I created for BBTT seem to follow the History
> Retraced style, which is a bit "old" with sepia tone.
>
> b. Overlay text: go straight to the point without listing "historical
> year/event/character". Capped at 30 words.
> For example as in the image attached, overlay text should be something like:
> "According to bodybuilding pioneer Eugen Sandow, massive arms do not require
> modern cable machines. You can unlock rapid arm growth using three beginner
> exercises that bypass the cable crossover entirely."
>
> c. First comment: a bit shorter, capped at 1,500 characters. Go straight to
> the main content. 3-4 short paragraphs.
>
> For these 2 pages, I used different prompts to gen content, so if you can/need
> to update the prompts, please let me know. Within the old tool, I did write new
> prompts already in Setting tab. Thanks so much em!

The referenced screenshot is **not** in this folder. Ask for it — the example
overlay text is quoted above verbatim, which is most of its value, but the
picture is the only evidence we have of the caps style as the client renders it
today.

---

## Itemised

### B6 — Logos (confirmed)

> Logos done.

Round 2's blocker, closed by the client's own upload. This is what unblocked
their RSS work and produced the BBTT drafts every item below is about. Nothing
to do.

### C4 — Overlay text in capitals, per Page

> could you please set the overlay text to ALL CAPITAL LETTERS for BBTT and FR
> pages? As this is the current style we've been using. I can't see anywhere to
> change this.

Two halves, and the second is the one the client actually reported. Capitals are
not implemented anywhere — not in the compositor, not in the browser preview —
so there is genuinely nothing to see. But note the request is **per Page**:
History Retraced keeps its mixed case.

### C5 — Hero style

> Hero image should be modern with bright lighting, fitness lifestyle magazine
> style. The draft posts I created for BBTT seem to follow the History Retraced
> style, which is a bit "old" with sepia tone.

The client is describing the output correctly and has diagnosed it correctly:
the hero prompt is History Retraced's, and every Page gets it.

### C6 — Hook

> go straight to the point without listing "historical year/event/character".
> Capped at 30 words.

Read the example carefully before building to this: it **does** name a person
(Eugen Sandow) and it carries no year. So the ask is to drop the *scaffolding* —
the obligation to open with a dated historical anchor — not to ban names. It is
exactly 30 words.

### C7 — First comment

> a bit shorter, capped at 1,500 characters. Go straight to the main content.
> 3-4 short paragraphs.

The one item that cannot be half-shipped: 1,500 characters is our **minimum**
today and 4 paragraphs fails a blocking rule, so a compliant BBTT first comment
is currently unreachable. See `comprehension.md`.

### F5 — The prompts the client already wrote

> For these 2 pages, I used different prompts to gen content ... Within the old
> tool, I did write new prompts already in Setting tab.

This is the most valuable sentence in the message and the easiest to skim past.
The client has already written the BBTT and FR prompts, in
`D:\Laboratory\social-agent`, where prompts are per-Page rows editable from a
Settings tab. Those rows are their real specification; items C5–C7 are a summary
of them. Read them before writing anything new.

**Read 2026-08-16 — `old-tool-prompts.md`.** Half true. Fitness Recipes has a
real, detailed prompt. **Bodybuilding Tips does not**: all four of its prompt
columns are byte-identical to History Retraced's and have been since 2026-07-05.
The client believes they wrote one. That belief is also the explanation for
their complaint.

It also carries a request we have to answer honestly: prompts here are **files
in git**, deliberately (`app/writer/prompts.py`), so "I edit them in Settings"
is not currently true and the client should be told which way we are going.
