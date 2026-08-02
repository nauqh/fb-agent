# Single operator — no `user_id`, no tenancy

Every table in the previous system carried a `user_id` and a matching Postgres
RLS policy. Production had two users, one owning 459 of 464 drafts; the other
five look like a test account. The tenancy was ceremony.

SQLite has no RLS, so keeping `user_id` would mean hand-writing the filter into
every query with no database backstop when one is forgotten — strictly worse
than what it replaced. The concept is therefore removed entirely. Access
control is a single shared credential on the FastAPI app.

## Consequences

- Every table loses a column, every query loses a predicate, and there is no
  auth provider, session store, or login flow to maintain.
- Re-introducing multi-tenancy later is a migration across **every** table plus
  an audit of every query. This is the decision most expensive to reverse, and
  it was taken deliberately on the evidence that a second tenant never
  materialised over the previous system's lifetime.
