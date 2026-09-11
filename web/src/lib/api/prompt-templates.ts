import type { PromptTemplate } from "@/lib/types";
import { del, get, post, put } from "@/lib/api/client";

/**
 * The prompt-template library: named post styles, selectable at run time.
 *
 * `GET · POST /prompts/templates`, `PUT · DELETE /prompts/templates/{id}`.
 *
 * Each template stores **deltas, never copies** - a blank field inherits the
 * Page's prompt chain (see `PromptTemplate`). That is the same contract
 * `setPromptFile` has, and for the same measured reason: full copies drift.
 *
 * These are rows, not files, for the same reason a Page's prompt override is:
 * Railway's filesystem is ephemeral, so a written file would vanish on the
 * next redeploy.
 */

export async function listPromptTemplates(pageId?: number): Promise<PromptTemplate[]> {
  // Page-scoped (client, 2026-09-10): with pageId, that Page's styles only.
  return get<PromptTemplate[]>(
    pageId === undefined ? "/prompts/templates" : `/prompts/templates?page_id=${pageId}`,
  );
}

export interface TemplateBody {
  name: string;
  /** The Page the style belongs to - every style is one Page's. */
  page_id: number;
  /** Blank clears the field - the template then inherits that prompt. */
  system_prompt?: string | null;
  overlay_prompt?: string | null;
  image_prompt?: string | null;
}

export async function createPromptTemplate(body: TemplateBody): Promise<PromptTemplate> {
  return post<PromptTemplate>("/prompts/templates", body);
}

export async function updatePromptTemplate(
  id: number,
  body: TemplateBody,
): Promise<PromptTemplate> {
  return put<PromptTemplate>(`/prompts/templates/${id}`, body);
}

/** Unpins the drafts generated under it server-side; nothing to do here. */
export async function deletePromptTemplate(id: number): Promise<void> {
  await del(`/prompts/templates/${id}`);
}
