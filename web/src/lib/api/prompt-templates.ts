import type { PromptTemplate } from "@/lib/types";
import { del, get, post, postRead, put } from "@/lib/api/client";

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

export interface TemplatePreview {
  /** Everything the text model is sent as instructions, this style included. */
  writer: string;
  /** The image model's system instruction. A separate request. */
  hero: string;
}

/**
 * What the model is sent if this style is used - composed server-side by the
 * same functions a real run calls, so the preview cannot drift from the run.
 *
 * Takes the form's current text, not an id: a style is a **delta layered onto**
 * the Page's prompts, and the operator was writing it against text they could
 * not see. `POST /prompts/templates/preview`.
 */
export async function previewPromptTemplate(body: TemplateBody): Promise<TemplatePreview> {
  // `postRead`: composing a preview stores nothing, and a POST that announced
  // itself as a write would refetch every open query on the screen.
  return postRead<TemplatePreview>("/prompts/templates/preview", body);
}

/**
 * The same two strings for the Page alone, with no style picked.
 *
 * A style with every field blank layers nothing (`agent._instructions` appends
 * a POST STYLE block only when a layer has text), so the composer above
 * already answers this - and answers it with the functions a real run calls.
 * A second endpoint would be a second copy of the layering rules.
 */
export async function previewPagePrompts(pageId: number): Promise<TemplatePreview> {
  return previewPromptTemplate({ name: "", page_id: pageId });
}
