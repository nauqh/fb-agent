# No local schedule state — Metricool's planner is the source of truth

The previous system mirrored every scheduled post into a `facebook_schedules`
table with a five-value status enum, a due-post cron, stale-`PROCESSING`
recovery, and a pull-on-read sync against Metricool. Production told us what
that mirror was worth: **0 rows, against 237 approved drafts.** Rows were
created at approve time, handed straight to Metricool, and later deleted. The
old code even says so out loud — `planner.ts:10`, *"Metricool web planner —
source of truth for scheduled publish time."*

So the new system keeps no schedule state. Approving a Draft pushes it to
Metricool and stores the returned post id on the Draft; anything the operator
needs to see about the queue is read live from `listMetricoolSchedulerPosts`.

## Consequences

- No cron, no scheduler process, no status enum, no drift, no reconciliation.
  Metricool already receives `autoPublish: true` and `firstCommentText`, so it
  owns publishing and the first comment as well.
- The calendar needs a live API call and is unavailable when Metricool is.
  Rescheduling and cancelling go to Metricool, not to us.
- If a publishing channel Metricool does not cover is ever added, this decision
  must be revisited — that channel would have nowhere to record its queue.
