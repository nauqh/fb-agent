# fb-agent

Generates Facebook posts for **History Retraced** from rival posts, tweets, and
news articles. Python + FastAPI + SQLite, with a Next.js frontend. More pages are
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

Schema changed? Delete `api/fb_agent.db` and re-seed. There is no migration tool
until the move to Supabase.

The page watermark is committed at `api/assets/watermarks/`;
`scripts/fetch_watermark.py` rebuilds it from the page's Facebook avatar.

## Prompts

`api/prompts/*.txt` — `system`, `overlay`, `image`, and the shared `image_rules`.
Edit them in place; they are read on every generation, so no restart. `{panel_pct}`
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
