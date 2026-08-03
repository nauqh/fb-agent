# A Page is the only identity — `brand_key` is deliberately destroyed

The previous system carried two overlapping identities for the same thing: a
`brand_key` (`hr`/`tff`/`bf`/`htt`) hardcoded as a four-value constant in
`brand-config.ts`, and a `target_page_id` from Metricool. Settings resolved
two-level — a page-level row falling back to a brand-level row — enforced by two
partial unique indexes.

It decayed exactly as you would expect. `brand_key` was widened from an enum to
free text, and production ended up holding **two parallel naming schemes for the
same four brands** (`hr` *and* `history-retraced`, `tff` *and* `the-fact-feed`,
`bf` *and* `bible-focus`), plus a `fitness-girls` value belonging to no brand at
all. Meanwhile ten Facebook pages had settings rows but only four fit in the
constant, so the other six carried `brand_key = NULL` and silently fell through
to code defaults. The brand-level rows turned out to be **byte-identical
duplicates** of their page-level counterparts.

A Page is now the only identity. Pages are **rows, not constants**. v1 seeds
exactly one, History Retraced; the rest are inserts when they are wanted, which
is the whole point of the decision. Everything references `page_id`.

## Consequences

- Deletes `brand_key`, the two-level fallback, both partial unique indexes, and
  the resolution helpers built on them (`resolve-template.ts`,
  `page-brand-context.ts`, `competitor-brand-key.ts`, `brand-keys.ts`).
- Adding a Page becomes a row insert rather than a code change and deploy. This
  is the specific failure being designed out: configuration that lives in code
  cannot grow, so it corrupts the data that references it.
- If one brand ever needs to publish to several pages, a grouping level has to
  be reintroduced above Page. That was judged unlikely enough to be worth the
  simplification, and is cheap to add later precisely because Pages are data.
