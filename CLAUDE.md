# Working in this repo

Loaded automatically every session. Conventions and traps only — the domain
language is `CONTEXT.md`, the reasoning is in `docs/` and the commit messages,
and the current state of play is `HANDOFF.md`.

## Orientation

- This repo is `fb-agent`. **`D:\Laboratory\social-agent` is the old app**: still
  deployed, still publishing History Retraced, and the source of most of the
  prior art referenced in comments here. Read it freely; never edit it.
- `docs/plan.md` has the phases, `docs/decisions.md` what was cut and why,
  `docs/adr/` the decisions that bind. ADR-0001 is the one that comes up most:
  **no local schedule state**, Metricool's planner is the source of truth.

## Checks

```
api/   uv run pytest -q          # 339 at time of writing
api/   uv run alembic check      # "No new upgrade operations detected"
web/   npx tsc --noEmit
web/   npx eslint src            # clean — keep it that way
```

`alembic check` is the one that tests cannot cover: the suite builds its schema
straight from the models with `create_all`, so it verifies the models and never
the migrations. `check` diffs the models against the **live** database. Anything
it reports means a revision is missing, and a deploy would take the schema and
the code out of step.

`eslint src` exits 0, **including warnings**. It carried one standing
`set-state-in-effect` error in `review-list.tsx` for a long time, described here
as pre-existing and to be left alone; it was neither hard nor a false positive
once read. A new problem is a new problem — fix it rather than adding a note
here. Deleting a feature usually strands an import or a handler, and that is
what the warning is telling you.

## Verify in a browser, not just in tests

A green suite has repeatedly not meant a working screen. Playwright is installed
in the **old** repo — require it by absolute path from a script in the
scratchpad:

```js
const { chromium } = require("D:/Laboratory/social-agent/node_modules/playwright");
```

Servers: the API on `:8000` (start with `--reload`), the web dev server on
`:3000`. Both are usually already running.

**Check the port's owner, not the process list.** Windows lets a second process
bind a port that is already bound, so a new server logs `Application startup
complete` and serves nothing while the old one keeps answering. A whole session
was spent on 404s from routes that were plainly on disk, with tests passing,
because a stale API from before the session still held `:8000`. Diagnose it by
asking the server what it has, not by reading the source:

```
curl -s localhost:8000/openapi.json | grep <your-new-route>
Get-NetTCPConnection -LocalPort 8000 -State Listen   # OwningProcess
```

`--reload` also orphans its worker when the parent is killed, so the port stays
held by a process that no longer reloads. Kill the tree (`taskkill /PID n /T
/F`), or kill the worker directly. And `--reload` does **not** reliably pick up
a brand-new route on a detached process: if `/openapi.json` disagrees with the
file, restart rather than editing further.

The web dev server has the same failure in a different shape: it served 404 for
`/auth/login` while the file was plainly there, and a `touch` on the route file
fixed it.

**Drive `http://localhost:3000`, never `http://127.0.0.1:3000`.** Next 16 blocks
`/_next/*` dev resources from any origin not in `allowedDevOrigins`, so the
browser gets server-rendered HTML with no client bundle: skeletons that never
resolve, zero API calls, and *no error in the page* — the warning is on the dev
server's stdout. An hour went into this looking like a broken screen. The
`127.0.0.1` note in `next.config.ts` is the opposite direction (Next → uvicorn),
where localhost really does resolve to `::1` and fail.

`--reload` watches `.py`, not `.env`. A settings change needs the process
restarted, or `touch` a watched file.

## Committing

- **Stage by filename. Never `git add -A`.** The user's own uncommitted work has
  been swept into a commit this way once already.
- Ask before creating a branch.
- No `Co-Authored-By` trailers.
- Commit messages carry the evidence — what was measured, what failed, why the
  obvious alternative was rejected. They are the durable record; this file and
  `HANDOFF.md` are not.

## Destructive operations

Never delete by glob. A `ls | grep inset | rm` swept up one of the user's own
uploaded images alongside test files. Delete the specific paths you created.

The database is migrated **by hand** with `ALTER TABLE ADD COLUMN` when the
user's drafts are worth keeping; the project convention is otherwise
delete-and-reseed. Say which you are doing.

## Style

The user asks for simple approaches and pushes back on over-engineering — they
are usually right, and several of this codebase's better decisions came from that
pushback. Match the density of the surrounding file: source carries dense
explanatory comments, `.env.example` was explicitly asked to stay terse.

## Integration traps

Each of these cost real time to find. They are pinned by tests in
`api/tests/test_publish.py` and `test_schedule.py`.

- **Metricool does not re-host images.** Their help centre says the normalize
  endpoint copies the file to their servers. Tested with a JPEG and a PNG: it
  echoes the URL back unchanged and returns no `mediaId`. The image URL must
  still resolve when Facebook fetches it at publish time — hence a *public*
  bucket. The old app used signed URLs expiring at `publishAt + 2h`; 0 of 105 of
  its published posts still have working images.
- `Accept: application/json` on the normalize **GET** answers 500 "No acceptable
  representation". Omit `Accept` on GETs to Metricool.
- `publicationDate.dateTime` is naive local time, with `timezone` as its own
  field. An offset suffix is rejected. Same on the read side.
- `zoneinfo` needs the `tzdata` package on Windows or `ZoneInfo(...)` raises.
- Pinned Gemini model ids rot silently, and `models.list()` still reports models
  that 404 on use. Verify with a real call.
