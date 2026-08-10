# fb-agent

Generates Facebook posts for **History Retraced** from competitor posts, tweets, and
RSS items. Python + FastAPI + Supabase Postgres, with a Next.js frontend. More pages are
inserts, not a rewrite — [why](docs/data-model.md#one-page-in-v1).

A rebuild of the Next.js/Supabase system at `../social-agent`, which is still
the only thing that can publish. See [docs/decisions.md](docs/decisions.md).

## Run

```bash
cp .env.example .env      # then fill it in
cd api
uv sync
uv run python scripts/seed_page.py     # once; idempotent
uv run fastapi dev app/main.py
```

Schema changed? Alembic:

```
cd api
uv run alembic revision --autogenerate -m "what changed"   # read the file it writes
uv run alembic upgrade head
```

The app also runs `upgrade head` at startup, so a deploy migrates itself. Run
`uv run alembic check` to see whether the models and the live database differ —
it should say "No new upgrade operations detected".

Delete-and-reseed stopped being the escape hatch when the database moved off the
laptop: it is shared, and it holds the only copy of the drafts.

The page watermark is committed at `api/assets/watermarks/` — recovered from the
previous Supabase project, [provenance here](docs/data-model.md#layout-is-config-not-data).

## Config

`api/config/layout.yml` is the Composed Image — one form, never per-page.
`api/config/sources.yml` is where material comes from — feeds keyed by page
name, plus the windows and grid caps. Both are parsed at import, so a bad value
fails the boot rather than the render.

Vendor base URLs, query-parameter sets and the User-Agent stay in code: changing
one means changing the code that parses the response, so exposing it would offer
an edit that cannot safely be made.

## Prompts

`api/prompts/*.txt` — `system`, `overlay`, `image`. One per prompt, one loader
each. Edit them in place; they are read on every generation, so no restart. `{panel_pct}`
and `{highlight_color}` are filled from `config/layout.yml`. Do not paste those
numbers in literally — that is precisely how the old system's prompts came to
promise a 25% panel while rendering 20%.

On Windows, set `PYTHONIOENCODING=utf-8` first if you redirect output. The
`fastapi dev` startup banner contains characters cp1252 cannot encode, and it
dies with a `UnicodeEncodeError` before the app ever loads. Nothing to do with
this codebase — it just looks like one.

`GET /health` reports database path, image size, models, and the *names* of any
missing secrets.

```bash
uv run python tests/spike_text_render.py    # font measurement + rendering
```

## Docs

| | |
|---|---|
| [CONTEXT.md](CONTEXT.md) | the vocabulary — read first |
| [docs/design.md](docs/design.md) | how the app is assembled |
| [docs/data-model.md](docs/data-model.md) | three tables, and what was rejected |
| [docs/decisions.md](docs/decisions.md) | what was cut, with the evidence |
| [docs/plan.md](docs/plan.md) | seven phases |
| [docs/adr/](docs/adr/) | three decisions expensive to reverse |

## State

Phase 0 done: app boots, schema creates, `/health` green, text spike passed.

Phase 1 backend done: History Retraced seeded, prompts on disk, pages routes
verified. Remaining — the `web/` scaffold and the Settings screen.
