# fb-agent

Generates Facebook posts for a fixed set of owned pages from rival posts,
tweets, and news articles. Python + FastAPI + SQLite, with a Next.js frontend.

A rebuild of the Next.js/Supabase system at `../social-agent`, which is still
the only thing that can publish. See [docs/decisions.md](docs/decisions.md).

## Run

```bash
cp .env.example .env      # then fill it in
cd api
uv sync
uv run fastapi dev app/main.py
```

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
Phase 1 next — seed Pages from the old Supabase project and build Settings.
