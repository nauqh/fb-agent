# PRD — Facebook Agent

Written from the system as built, not as a forward plan. Vocabulary is
[CONTEXT.md](../CONTEXT.md); the binding decisions are the three
[ADRs](adr/). Where this document and the code disagree, the code is right and
this document is a bug.

---

## Problem Statement

An operator runs several owned Facebook Pages — History Retraced and The Fact
Feed today — and every post is hand-made. Finding something worth posting means
scrolling other people's Pages, checking news feeds, and remembering what was
already covered. Writing it means holding a page's voice in your head. Making
the image means a separate tool. Scheduling means a third.

The previous system automated parts of this and made it worse in a specific way:
it mirrored external state locally. It kept its own copy of the posting
schedule, its own copy of the Competitor list, and its own copy of every prompt
in a 54-column templates table. Those copies drifted from the systems they
copied, and when they drifted the app went on producing confident, well-formed
output about the wrong thing. Its schedule table held **0 rows against 237
approved drafts** — the mirror was not merely stale, it was empty, while the app
behaved as though it were authoritative.

The operator needs the tedious parts done for them without ever losing the
ability to see, edit and veto what goes out under their name.

---

## Solution

A two-part application — a browser workspace and a service behind it — that
gathers candidate material, drafts a post and generates its image, then stops
and waits for a human.

The operator picks Source Items from a browsable list, sends them to be written,
reviews the resulting Draft exactly as it will appear on Facebook, edits
anything, and approves or rejects. Approved Drafts are handed to Metricool with
a publish time. Metricool posts to the Page and adds the first comment.

Three properties define the shape:

- **A person is the gate.** No Draft becomes a post without an explicit
  approval. There is no configuration that removes this step.
- **External state is never mirrored.** Metricool owns the schedule and the
  Competitor list; the app reads them live and stores neither (ADR-0001).
- **A Page is a row, not a constant.** Adding a Page is an insert, not a code
  change (ADR-0003).

---

## User Stories

### Choosing what to write about

1. As an operator, I want to see recent Competitor posts for the Page I'm working on, so that I can borrow a format that is currently working.
2. As an operator, I want Competitor posts sorted by reactions, so that the strongest performers are the ones I consider first.
3. As an operator, I want to see items from RSS feeds curated for this Page, so that I get the beats that suit this Page rather than a generic news wire.
4. As an operator, I want to paste an X post URL and pull in that tweet, so that a specific story I've seen elsewhere can become a post.
5. As an operator, I want a Source Item I have already written from to be visibly flagged, so that I don't produce the same post twice.
6. As an operator, I want browsing sources to write nothing to the database, so that looking around has no consequences.
7. As an operator, I want to collect several Source Items before generating, so that I can queue a batch in one pass.
8. As an operator, I want the Source Items I see to belong to the Page I have selected, so that The Fact Feed's beats never appear while I'm working on History Retraced.

### Generating

9. As an operator, I want to send selected Source Items to be written, so that I get a first draft without composing from scratch.
10. As an operator, I want to generate from a topic I type in, so that I am not limited to material the app found.
11. As an operator, I want the app to know that a Competitor post is borrowed for tone only, so that it doesn't write a post about a rival's subject matter.
12. As an operator, I want the app to know that a tweet or RSS item binds the subject, so that the post is about that story and not merely in its style.
13. As an operator, I want each Draft to appear in the queue the moment generation starts, so that I can see work in progress rather than an empty screen.
14. As an operator, I want to see which step a Draft is on and how far through it is, so that I know whether to wait.
15. As an operator, I want a run that fails to leave a Draft that says why, so that a failure is distinguishable from a Draft awaiting review.
16. As an operator, I want Drafts stranded by a restart to be marked as such on the next start, so that they don't sit in the queue looking ready forever.

### Reviewing

17. As an operator, I want a queue of Drafts with the ones needing a decision first, so that I know where to start.
18. As an operator, I want to see the finished card exactly as it will appear on Facebook, so that I am approving the real thing.
19. As an operator, I want to edit the caption, the hook and the first comment, so that I can fix a line without regenerating.
20. As an operator, I want to edit highlight phrases, so that the emphasis in the image is mine.
21. As an operator, I want to regenerate just the image, so that a good caption isn't lost to a bad picture.
22. As an operator, I want to upload my own photograph as a circular inset, so that a post about a real person can show that person.
23. As an operator, I want to move and resize that inset, so that it sits well against the image behind it.
24. As an operator, I want brand-rule failures shown on the Draft, so that I can judge whether they matter rather than discovering them after publishing.
25. As an operator, I want to approve a Draft, so that it becomes eligible for scheduling.
26. As an operator, I want to un-approve a Draft, so that a decision made too quickly can be taken back.
27. As an operator, I want to reject a Draft, so that it leaves the queue without being deleted.
28. As an operator, I want to delete a Draft outright, so that genuine rubbish doesn't accumulate.
29. As an operator, I want an edit in the Draft sheet to update the queue behind it, so that two views of the same Draft never disagree.

### Scheduling and publishing

30. As an operator, I want to hand an approved Draft to Metricool with a date and time, so that it goes out when the audience is there.
31. As an operator, I want the image to still resolve when Facebook fetches it at publish time, so that a post doesn't go out with a broken picture.
32. As an operator, I want the first comment sent with the post, so that Metricool adds it without me returning to do it manually.
33. As an operator, I want the schedule read live from Metricool, so that what I see is what will actually happen.
34. As an operator, I want to see which scheduled posts came from this app and which did not, so that the cutover from the old system is legible.
35. As an operator, I want a rehearsal mode that keeps pushes as Metricool drafts, so that I can exercise the whole path without anything reaching an audience.
36. As an operator, I want the time I choose interpreted in the Page's own timezone, so that a post scheduled for 8pm goes out at 8pm.

### Configuration and orientation

37. As an operator, I want to switch the Page I'm working on from anywhere in the app, so that I don't navigate back to change context.
38. As an operator, I want my Page choice remembered between visits, so that I resume where I left off.
39. As an operator, I want to see which RSS feeds each Page draws from, so that I understand why a particular item appeared.
40. As an operator, I want each feed to link to its source, so that I can check the feed itself.
41. As an operator, I want to see every Competitor Metricool is watching across all Pages, so that I can see how much of the 100-competitor allowance is spent.
41a. As an operator, I want to assign one Competitor to several Pages, so that the account limit does not decide how many Pages can watch a source.
41b. As an operator, I want to record why a Page reads a Competitor, so that the reasoning survives without a commit message.
41c. As an operator, I want to add and remove RSS feeds from a screen, so that changing a feed does not need a deploy.
41d. As an operator, I want a new feed probed before it is saved, so that a feed which does not answer never reaches the grid.
42. As an operator, I want Competitors that have published nothing to be listed first, so that a dead Competitor is obvious rather than merely absent.
43. As an operator, I want to see the instructions the writer works to, so that unexpected output is explicable.
44. As an operator, I want a health endpoint naming any missing configuration, so that a broken deploy says what is missing rather than failing obscurely.

### Safety and operability

45. As an operator, I want the service to refuse requests without a shared key, so that a public URL is not an open door.
46. As an operator, I want the health check to stay reachable without that key, so that the platform can probe it.
47. As an operator, I want a missing key to deny everything rather than allow everything, so that a misconfigured deploy fails loudly.
48. As an operator, I want the browser never to hold the key, so that anyone with developer tools cannot take it.
49. As an operator, I want Drafts and images to survive a redeploy, so that a deploy is not a data-loss event.
50. As an operator, I want the schema brought up to date on start, so that deploying code and migrating the database cannot get out of order.
51. As an operator, I want images stored under a path rather than a URL, so that changing bucket or project is configuration and not a database migration.
52. As a developer, I want the test suite to run offline in about a minute, so that I can work without a live database.

---

## Implementation Decisions

### Overall shape

Two deployables. A **Next.js workspace** with no database access, talking only
to the service over HTTP; and a **FastAPI service** owning all state, all
integrations, and all image work. The split is not ceremony: image compositing
and the AI calls are Python-side concerns, and keeping the browser out of the
database is what lets the service be the only place authorisation is enforced.

### Backend modules

**Source adapters** — three implementations behind one interface: Competitor
posts from Metricool, tweets from x.com, RSS items via feed parsing. This is the
one seam in the app that is genuinely a seam, which is why tests substitute here
rather than intercepting HTTP. A `SourceKind` carries an `is_factual` property
that decides whether a Source Item's subject binds the writer — derived from the
kind, never stored, because a stored copy is a second truth that drifts.

**Generate run** — the pipeline, exposed as a single call taking Source Item ids
and Page ids and returning Draft ids. The Draft row is inserted *before*
generation begins, so it doubles as the job record; that is why progress lives
on the Draft and there is no separate event table. Steps report as `queued` →
writing (20%) → drawing (60%) → done (100%).

**Writer** — an AI agent producing caption, hook, first comment, highlight
phrases and hashtags, with prompts held as files rather than database rows.
Retries on validation failure.

**Validators** — the brand rules as pure functions, one per rule: hook length,
no question in the hook, recap point count, emoji line starts, first-comment
paragraph count and length, birth/death year formatting. Pure functions because
they are the most testable thing in the app and must stay that way. Rules still
failing after the writer exhausts its retries are recorded on the Draft as
warnings rather than blocking it — the operator judges.

**Image** — hero generation (the paid call), text layout, and a compositor that
assembles hero, text panel, watermark and optional circular inset into the
finished card. Hero and composite are stored separately so that re-compositing
an edit does not re-pay for image generation.

**Media store** — one implementation, Supabase Storage, behind a small
protocol. The bucket is public because Metricool does not re-host images: the
URL must still resolve when Facebook fetches it at publish time. Rows store a
path, never a URL; the URL is computed on serialisation, which is what keeps a
row portable across projects and buckets.

**Publish** — Metricool only. Sends text, first comment, media URL, publication
date and a draft flag.

### Frontend modules

**Page scope** — a provider exposing the Pages, the selected Page and a setter,
backed by a cookie read by the server layout so the first render is already
correct. Every screen reads from it; the switcher lives in the shared screen
header so no screen can forget to render it.

**API client** — one module that knows the service is over HTTP. Requests go to
a relative path and are proxied by the Next server. It surfaces the service's
`detail` string verbatim, because those strings are written for the operator and
collapsing them to "Request failed" throws away the actionable part.

**Query layer** — a small read/invalidate mechanism where any write notifies
open queries, so the Review queue and an open Draft sheet cannot disagree.

**Screens** — Sources, Review, Schedule, Settings. Each is scoped to the
selected Page.

### Database

Five tables. The previous system had eight plus a 54-column templates table;
everything removed was configuration duplicated across rows, external state
mirrored locally, or tenancy ceremony. The two added since are both things an
operator has to change without a deploy — this API runs from a container image,
so a file written into it is gone at the next one.

- **Page** — identity and policy: name, Facebook page id, Metricool blog id,
  avatar and watermark asset paths. No `is_active`; a flag that is never false
  is not state.
- **Source Item** — one table, three kinds, with a uniqueness constraint on
  (kind, external id) so selecting the same item twice cannot create a second
  row.
- **Draft** — the generated post plus its progress, its warnings, its image
  paths, its inset geometry, and the Metricool post id. No `scheduled_at`
  (ADR-0001).
- **Feed** — one RSS feed a Page draws from, added and removed on Settings. No
  row points at one: a Source Item carries its publisher as text, so removing a
  feed changes tomorrow's grid and nothing already published.
- **Page Competitor** — which Competitors feed which Pages. Not a mirror of
  Metricool's list, which is still theirs and still never stored; an assignment
  on top of it, which they have no way to express.

**Competitor posts are a shared pool.** Metricool caps an account at 100
competitors *in total*, not per page, so five Pages that should each watch the
same twenty sources cannot each be given them. A source is configured once,
under whichever Page had room, and assigned to the Pages that read it.
`synced_for_page_id` records which set a post arrived through — provenance, not
ownership. A Page with no assignments falls back to the set it owns in
Metricool, which is what let the change ship without blanking every grid.

No `user_id` (ADR-0002). No `brand_key` (ADR-0003). Layout lives in
configuration, not on Page.

**Enum columns are stored as `VARCHAR`, never as a native Postgres enum.** Three
constraints have to hold at once: both backends must build the same schema so
the offline test fixture is testing production's shape; adding a member must not
require a migration; and the value must load back as the enum rather than as a
bare string, because the `is_factual` property is asked of rows read from the
database. Storing as a plain string satisfies the first two and silently breaks
the third.

**Migrations are Alembic**, run in-process at startup. Exactly one replica, so
nothing races for the migration lock and no deploy can ship code whose schema
change was forgotten. The suite builds its schema from the models rather than by
running migrations, so a schema check against the live database is the only
thing that can catch a missing revision, and it is a required pre-deploy step.

### API contract

Grouped by screen rather than by table.

| Area | Endpoints |
|---|---|
| Sources | list Competitor posts; list RSS items; look up a tweet; read the feed and Competitor configuration for a Page |
| Generate | start a run (returns `202` with Draft ids) |
| Drafts | list; read one; patch fields; regenerate image; upload/remove inset; delete; approve; un-approve; reject; publish |
| Schedule | read the planner live from Metricool |
| Pages | list; read one; patch |
| Prompts | read the writer's instructions |
| Health | boot state and the *names* of missing configuration |

Reads that browse — Competitor posts, RSS items, a tweet — do not write. A
Source Item becomes a row only when it is selected for generation.

### Integration decisions

These were each found by measurement and are pinned by tests.

- Metricool does not re-host images. The normalize endpoint echoes the URL back
  unchanged and returns no media id, so the image must remain publicly
  retrievable at publish time. Signed URLs were what left 0 of 105 of the old
  system's published posts with working images.
- `Accept: application/json` on Metricool GETs answers 500. Omit it.
- Publication date is naive local time with the timezone as a separate field; an
  offset suffix is rejected, on both the read and write side.
- Pinned model ids rot silently, and the provider's model list still reports
  models that fail on use. Verify with a real call.

### Authentication

A single shared secret in a request header, checked in middleware rather than as
a per-route dependency — a dependency is something the next route can be written
without, and that failure is silent. Middleware also covers the static asset
mount, which a dependency cannot reach. Only the health endpoint is exempt, so
the platform probe works.

The comparison is constant-time. An unset key **denies**: an empty constant-time
comparison against an empty header succeeds, so this requires an explicit check,
and getting it wrong produces a deploy that is wide open and looks healthy.

The browser never holds the key. The Next server proxies the service and
attaches the header on the way through, so the secret lives in that server's
environment and never enters a bundle. The variable must not carry the framework's
public prefix, which would inline it into client JavaScript at build time.

### Non-functional

- **One replica.** The stranded-Draft sweep marks every in-progress Draft as
  failed on startup and cannot distinguish "crashed" from "running in another
  process". A second worker would reap a live run. This is a correctness
  constraint, not a capacity choice.
- **One database and one bucket across environments.** A Draft id is part of the
  stored media path, so two databases handing out the same ids would collide in
  storage. The consequence is that there is no sandbox: local runs write
  production rows. Rehearsal mode is what keeps that off a real Page.
- **Timestamps are naive UTC** in the database, with the client treating them as
  UTC explicitly.
- **Assets are committed, not hosted.** The watermark and font ship with the
  code, because the old system read them from a bucket and printed the Page name
  as plain text when the key went missing — silently.

---

## Testing Decisions

**What makes a good test here.** Tests assert externally visible behaviour: the
rows that exist afterwards, the status code and body, the file that was written,
the transitions a Draft went through. They do not assert how a function reached
that state. No mocking library reaches past an interface — if a test needs to,
the module is the wrong shape.

**Substitution happens at the seam.** The three Source adapters are the seam, so
tests replace them there rather than intercepting HTTP. Media writes go to a
local directory through the same protocol the real store implements. Image
generation is refused by default in every test, because it is the one call that
costs money per invocation, and a suite billed for it once already; tests that
need pixels opt in explicitly.

**Reload, don't reconstruct.** A test that constructs a row and asserts on it
cannot catch a column that fails to round-trip. This is not hypothetical: a
change to the enum columns passed the entire suite while a stored kind loaded
back as a plain string, which would have raised at runtime on the property the
generate path depends on. Tests covering persistence must read the row back.

**Modules under test.** The validators (pure functions, exhaustively); the
generate run (with fakes for writer, image, compositor and media store,
asserting rows, progress transitions and that a failure leaves an error rather
than a stuck row); the routes, through a test client against a throwaway
database; the publish and schedule paths, pinning each integration trap above;
authentication, including the unauthenticated case, the wrong-key case, the open
health endpoint, the static asset mount, and the blank-key case.

**The gap tests cannot close.** The suite builds its schema from the models, so
it verifies the models and never the migrations. A schema diff against the live
database is the only check for a missing revision and belongs in the pre-deploy
routine, not in the suite.

**Browser verification is not optional.** A green suite has repeatedly not meant
a working screen. Changes with a rendered surface are driven in a real browser
before being called done.

---

## Out of Scope

- **Multi-tenancy.** No user accounts, no per-user data, no roles (ADR-0002).
  One operator.
- **Automatic publishing.** No configuration removes the human approval step.
- **A local schedule mirror.** Metricool's planner is the source of truth
  (ADR-0001). No due-post cron, no stale-job recovery, no status enum
  duplicating theirs.
- **Storing the Competitor list.** Configured in Metricool; the app stores their
  posts, never the list.
- **Networks other than Facebook.** The publish payload names a network, but
  nothing else in the system is built for a second one.
- **Horizontal scaling.** Single replica by design; supporting more means
  scoping the stranded sweep first.
- **A gate on the workspace itself.** The service is locked; the browser
  application is not. It runs locally today. Deploying it publicly needs its own
  decision, because it holds the key server-side and would hand a working UI to
  anyone who loaded it.
- **Analytics and reporting.** Metricool already does this.

---

## Further Notes

**Deliberate absences.** There is no queue, no worker, no Redis, no cron. Long
work runs as a background task in the same process, which is sound only because
of the single-replica constraint and is the first thing that has to change if
that constraint lifts.

**The old system remains the reference** for prior art and for what not to
repeat, and is still the only thing publishing today. It is read-only.

**Two Pages, live.** `CONTEXT.md` still describes v1 as having exactly one; The
Fact Feed was added as an insert, exactly as ADR-0003 predicted, which is the
best available evidence that the decision was right.

**Known and accepted.** The item collection does not clear when the Page is
switched. One brand rule warns on nearly every news-beat Draft, which is a
tuning problem rather than a correctness one.
