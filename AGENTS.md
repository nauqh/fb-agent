# Repo Working Agreements (fb-agent)

Working agreements for any agent in this repo, whichever tool you are: Claude
Code, Codex, Cursor, or something else.

This file is process: how to work, coordinate, and finish. The repo's facts live
elsewhere and are not repeated here.

- `CLAUDE.md` - conventions and the traps that cost real time (ports, Metricool,
  migrations, checks). Not Claude-specific in content; read it whatever you are.
- `CONTEXT.md` - the domain language. What a Page, a Draft, a Source actually is.
- `docs/plan.md`, `docs/decisions.md`, `docs/adr/` - the reasoning, what was cut,
  and the decisions that bind. ADR-0001 comes up most: no local schedule state.
- `HANDOFF.md` - the current state of play.

## Baseline workflow

Start every task by establishing:

1. **Goal and acceptance criteria.** What does done look like, concretely?
2. **Constraints.** Scope, reversibility, anything live that could be touched.
3. **What must be inspected.** The files, the routes, the tests, the real flow
   end to end. Read before you edit; understanding is never the part you skip.
4. **Who else is here.** Read `.agents/status/` (below) before touching a file.
5. **Whether the answer depends on live state.** Model ids, a running server's
   routes, a third-party response shape: verify, do not recall.

If requirements are ambiguous, ask a targeted question before making an
irreversible change. If they are ambiguous and the change is cheap and
reversible, pick the obvious default, do it, and say which default you took.

## Parallel sessions (REQUIRED)

Other agents may be working in this repo at the same time. Status files live in
`.agents/status/`, one per session. They are gitignored: live state, not history.

### Claiming your file

- If the user named your session, use that name.
- Otherwise name it after your task in kebab-case (`shorts-history-fix`,
  `metricool-retry`) and create `.agents/status/<name>.md`.
- If that file exists and is not yours, pick another name. Never adopt or
  overwrite someone else's file.
- A file whose `Updated:` is more than a day old is a dead session. You may take
  its name over.

### Protocol

- At the start of a task, read **every** file in `.agents/status/`.
- Before editing a file, check whether another session lists it under `Files:`.
  If it does, **don't edit it**. Tell the user and stop; do not negotiate with
  the other agent through the status files.
- Update your own file when you start a task, when you start touching new files,
  when you make a decision others need (API shape, renamed function, new env
  var, new migration), and when you finish.
- On finishing: `Status: done`, `Files:` cleared, `Notes:` holding what landed
  and anything the next session needs.
- Only ever write to your own status file.

### Format

```markdown
# backend
Tool: Codex
Status: working
Task: Add refresh token endpoint
Files: api/app/routes/auth.py, api/app/settings.py
Notes: /auth/login now returns { accessToken, refreshToken }
Updated: 2026-09-11 14:20
```

`Updated:` is a real timestamp, taken from the clock, not guessed.

`Status:` is one of:

| Status | Meaning | Are its `Files:` claimed? |
|---|---|---|
| `working` | Actively editing right now. | Yes. Do not touch them. |
| `blocked` | Stopped, waiting on the user or on another session. Say what for in `Notes:`. | Yes. The work is unfinished and will resume. |
| `review` | Change is complete and checks have passed, waiting on the user to look. | Yes. It may still come back for edits. |
| `done` | Task finished and handed over. `Files:` cleared. | No. |
| `idle` | Session alive, no task claimed. | No. |

The difference that matters is `done` versus `idle`: `done` says a task
completed and its `Notes:` are worth reading, `idle` says there is nothing here.
A session that finishes one task and picks up another goes `done` then straight
back to `working` with a new `Task:`, rather than through `idle`.

## Writing style (REQUIRED)

- **No em dashes, no en dashes.** Use a plain hyphen `-`. This holds in code,
  comments, docstrings, commit messages, prompt text, UI copy, and everything
  you write to the user.
- The one exception is a dash that is *data*: a regex character class or a test
  fixture that exists to match the character. `api/app/writer/validators.py`
  has both; leave them alone.
- Match the density of the file you are in. Source here carries dense
  explanatory comments; `.env.example` was explicitly asked to stay terse.
- Prose you were not asked for is debt. A report, a walkthrough or per-phase
  notes the user requested is not.

## Default autonomy and safety

Read-only exploration needs no permission. Writes are scoped to the repo. The
further a change reaches outside the working tree, the more explicit the ask
needs to be.

### Editing files

- Make the smallest change that actually solves the problem, **after** reading
  enough to know what it touches. A small diff in the wrong place is a second
  bug, not a win.
- Fix the root cause. Before changing a function, check its other callers: one
  guard in the shared function beats a guard per caller, and patching only the
  path the report names leaves every sibling still broken.
- Patch, don't rewrite. Whole-file rewrites hide the real change in the noise.
- No unrequested abstraction. No interface with one implementation, no config
  for a value that never changes, no scaffolding for later.
- Preserve the surrounding conventions rather than importing your own.

### Live services and remote APIs (REQUIRED)

The API talks to Metricool, Facebook, Supabase Storage, YouTube and Gemini with
real credentials against real accounts.

- **Read-only by default.** Listing, inspecting and diffing need no permission.
- **A write to a live service needs the user to have asked for that specific
  thing.** Publishing a post, scheduling into the Metricool planner, deleting
  from the bucket, uploading to YouTube: none of these are reversible in any way
  that matters, and a published post has been seen.
- Approval for one write is not approval for the next one.
- Where a dry run exists, do that first and show what it would have done.

### Secrets and sensitive data

- Never print secrets. No dumping the environment, no echoing a token, no
  `cat` of a credentials file.
- Never write a secret into a status file, a doc, a test fixture or a commit.
- A `cookies.txt` export is a live Google session, not a config file. Treat it
  as a credential and delete it once encoded.
- Use secret values; do not display them. Redact when output must be shown.

### Destructive operations

- **Never delete by glob.** A `ls | grep | rm` once swept up one of the user's
  own uploaded images alongside test files. Delete the specific paths you
  created, by name.
- Before deleting or overwriting anything you did not create, look at it. If
  what you find contradicts how it was described, surface that instead of
  proceeding.
- The database is either migrated by hand or deleted and reseeded. Say which
  you are doing before you do it.

### Git

- **Stage by filename. Never `git add -A`.** The user's own uncommitted work has
  been swept into a commit that way already.
- Ask before creating a branch. Commit and push only when asked.
- No `Co-Authored-By` or other AI-authorship trailers.
- Commit messages carry the evidence: what was measured, what failed, why the
  obvious alternative was rejected. They are the durable record; this file is not.

## Accuracy and verification

Prefer what the system tells you now over what you remember.

- **Ask the running process, not the source.** A route is real when
  `/openapi.json` has it. A port belongs to whichever process actually holds it,
  which on Windows is not always the one you just started. `CLAUDE.md` has the
  diagnosis for both; it has cost whole sessions.
- **Pinned model ids rot silently**, and a provider's `models.list()` still
  reports ids that 404 on use. Verify with a real call.
- For anything version-sensitive or recent, prefer the vendor's own current docs
  over recall, and note the date of what you relied on.
- Never report a command you did not run or a result you did not see.

## Definition of done

A task is done when:

- the change is implemented, or the question is answered;
- the checks that apply have been **run**, not merely mentioned (the commands
  and their caveats are in `CLAUDE.md`, "Checks"):

  ```
  api/   uv run pytest -q
  api/   uv run alembic check
  web/   npx tsc --noEmit
  web/   npx eslint src
  ```

- anything with a screen or an endpoint has been driven for real. A green suite
  has repeatedly not meant a working screen in this repo;
- new warnings and errors are fixed or explicitly listed as out of scope;
- the impact is stated: what changed, where, and why;
- anything deliberately left out is named as a follow-up;
- your status file reflects where things actually stand.

If a check failed, say so and show the output. If you skipped one, say that too.
