import type { Draft, DraftStatus } from "@/lib/types";
import { WRITTEN, WRITTEN_BY_EXTERNAL_ID } from "@/lib/fixtures/generated";
import { db, emit, latency, nowIso } from "@/lib/store";

/**
 * `POST /generate`, `GET /drafts`, `GET /drafts/{id}`, `PATCH /drafts/{id}`,
 * approve · unapprove · reject · recomposite · regenerate-image.
 */

export interface DraftFilter {
  status?: DraftStatus | "all";
  pageId?: number;
}

export async function listDrafts(filter: DraftFilter = {}): Promise<Draft[]> {
  let rows = [...db.drafts];
  if (filter.status && filter.status !== "all") {
    rows = rows.filter((draft) => draft.status === filter.status);
  }
  if (filter.pageId !== undefined) {
    rows = rows.filter((draft) => draft.page_id === filter.pageId);
  }
  // No run identity exists on `draft`, so six Drafts from one press are
  // indistinguishable from six unrelated ones. Newest first is the only
  // ordering the schema supports. See docs/data-model.md.
  rows.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return latency(rows, 240);
}

export async function getDraft(id: number): Promise<Draft> {
  const draft = db.drafts.find((candidate) => candidate.id === id);
  if (!draft) throw new Error(`No draft ${id}`);
  // The poll target. Deliberately quick — the client hits this on an interval
  // while a row is generating.
  return latency(draft, 80);
}

/**
 * Operator edits. The written fields only; status moves through its own routes.
 *
 * `image_prompt` is in here because it is the only lever on a hero the model
 * refused — the writer produced it, so the operator has to be able to correct it
 * before paying for another generation.
 */
export type DraftEdit = Partial<
  Pick<
    Draft,
    | "hook"
    | "caption"
    | "first_comment"
    | "overlay_text"
    | "highlight_phrases"
    | "hashtags"
    | "image_prompt"
  >
>;

export async function updateDraft(id: number, edit: DraftEdit): Promise<Draft> {
  const draft = requireDraft(id);
  Object.assign(draft, edit, { updated_at: nowIso() });
  emit();
  return latency(draft, 260);
}

export async function approveDraft(id: number): Promise<Draft> {
  return setStatus(id, "approved");
}

export async function rejectDraft(id: number): Promise<Draft> {
  return setStatus(id, "rejected");
}

/**
 * `POST /drafts/{id}/unapprove` — Undo, for the toast.
 *
 * Approve is reversible right up until the v2 Metricool push, which is exactly
 * why the Quota it consumes is advisory: an approved Draft can come back.
 */
export async function returnToReview(id: number): Promise<Draft> {
  return setStatus(id, "review");
}

/**
 * `POST /drafts/{id}/recomposite` — redraw the panel over the stored hero.
 *
 * The cheap half. `hero_image_path` and `composed_image_path` are separate
 * columns precisely so that editing the overlay text does not re-pay for image
 * generation, so this rewrites only the composed path and needs a hero already
 * on disk.
 */
export async function recomposite(id: number): Promise<Draft> {
  const draft = requireDraft(id);
  if (!draft.hero_image_path) {
    throw new Error("No hero image to composite over — regenerate the hero first.");
  }
  draft.composed_image_path = `composed/${id}-${Date.now()}.png`;
  draft.updated_at = nowIso();
  emit();
  return latency(draft, 900);
}

/**
 * `POST /drafts/{id}/regenerate-image` — a new hero, then a recomposite.
 *
 * The expensive half: this is a paid `google-genai` call. It is also the only way
 * out of a Draft whose hero was refused, so it clears `error` — the text was
 * written and saved, and the row was only ever stuck on the image.
 */
export async function regenerateHero(id: number): Promise<Draft> {
  const draft = requireDraft(id);
  const stamp = Date.now();
  Object.assign(draft, {
    hero_image_path: `heroes/${id}-${stamp}.png`,
    composed_image_path: `composed/${id}-${stamp}.png`,
    error: null,
    progress_step: null,
    progress_pct: 100,
    updated_at: nowIso(),
  });
  emit();
  return latency(draft, 2_400);
}

export interface GenerateRequest {
  source_item_ids: number[];
  page_ids: number[];
  /** Set instead of source ids for a topic-only run. */
  topic?: string;
}

/**
 * The run.
 *
 * Inserts a placeholder row per (source × page) at `status='generating'` and
 * returns the ids immediately; a background timer fills each row in and
 * advances the progress columns. That is the real shape — the row *is* the job
 * record, which is why there is no queue and no event table.
 */
export async function generate(request: GenerateRequest): Promise<number[]> {
  const sources = request.source_item_ids.length > 0 ? request.source_item_ids : [null];
  const ids: number[] = [];
  // Which canned outputs this run has already handed out, so three Source
  // Items do not come back as the same story twice.
  const claimed = new Set<number>();

  for (const pageId of request.page_ids) {
    for (const sourceItemId of sources) {
      const draft: Draft = {
        id: db.nextDraftId++,
        page_id: pageId,
        source_item_id: sourceItemId,
        topic: sourceItemId === null ? (request.topic ?? null) : null,
        status: "generating",
        hook: null,
        caption: null,
        first_comment: null,
        overlay_text: null,
        highlight_phrases: [],
        hashtags: [],
        image_prompt: null,
        hero_image_path: null,
        composed_image_path: null,
        warnings: [],
        progress_step: "queued",
        progress_pct: 0,
        error: null,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      db.drafts.push(draft);
      ids.push(draft.id);

      const written = chooseWritten(sourceItemId, claimed);
      claimed.add(written);
      runInBackground(draft.id, written);
    }
  }

  emit();
  return latency(ids, 300);
}

/**
 * Writer → HeroImage → Compositor → MediaStore, faked on a timer.
 *
 * Every step writes `progress_step` and `progress_pct` to the row, because that
 * is the only channel the client has: it polls `GET /drafts/{id}` until status
 * leaves `generating`.
 */
function runInBackground(draftId: number, writtenIndex: number): void {
  const steps: { step: string; pct: number; at: number }[] = [
    { step: "writing", pct: 12, at: 700 },
    { step: "validating", pct: 34, at: 2_600 },
    { step: "hero image", pct: 58, at: 4_200 },
    { step: "compositing", pct: 84, at: 6_400 },
  ];

  for (const { step, pct, at } of steps) {
    setTimeout(() => {
      const draft = db.drafts.find((candidate) => candidate.id === draftId);
      if (!draft || draft.status !== "generating") return;
      draft.progress_step = step;
      draft.progress_pct = pct;
      draft.updated_at = nowIso();
      emit();
    }, at);
  }

  setTimeout(() => {
    const draft = db.drafts.find((candidate) => candidate.id === draftId);
    if (!draft || draft.status !== "generating") return;

    Object.assign(draft, { ...WRITTEN[writtenIndex] }, {
      status: "review" as const,
      hero_image_path: `heroes/${draftId}.png`,
      composed_image_path: `composed/${draftId}.png`,
      progress_step: null,
      progress_pct: 100,
      updated_at: nowIso(),
    });
    emit();
  }, 8_000);
}

/**
 * Which canned output this Source Item gets.
 *
 * Its own, if one was written for it and nothing else in this run has taken it;
 * otherwise the first output still unclaimed. Only once the pool is exhausted
 * does a run repeat itself.
 */
function chooseWritten(sourceItemId: number | null, claimed: Set<number>): number {
  const source = db.sourceItems.find((item) => item.id === sourceItemId);
  const matched = source ? WRITTEN_BY_EXTERNAL_ID[source.external_id] : undefined;
  if (matched !== undefined && !claimed.has(matched)) return matched;

  const free = WRITTEN.findIndex((_, index) => !claimed.has(index));
  return free === -1 ? claimed.size % WRITTEN.length : free;
}

function requireDraft(id: number): Draft {
  const draft = db.drafts.find((candidate) => candidate.id === id);
  if (!draft) throw new Error(`No draft ${id}`);
  return draft;
}

async function setStatus(id: number, status: DraftStatus): Promise<Draft> {
  const draft = requireDraft(id);
  draft.status = status;
  draft.updated_at = nowIso();
  emit();
  return latency(draft, 220);
}
