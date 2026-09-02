/**
 * The Shorts workspace's API: make a video, manage CTA clips, read history.
 *
 * Mirrors `api/app/youtube/routes.py`. Three verbs matter to this screen:
 *
 * - `POST /youtube/jobs` returns ids immediately and the worker fills the row
 *   — the operator never waits on the download/trim/concat.
 * - `GET /youtube/jobs/{id}` is polled while a row is in flight, the same
 *   pattern the rail uses for `generating`.
 * - `GET /youtube/jobs/{id}/download` serves the produced mp4 — it doubles as
 *   the `<video>` source and the download link, so the browser only talks to
 *   one origin and the bucket never needs to be public to this screen.
 */

import { del, get, post, postForm } from "@/lib/api/client";

export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface YoutubeJob {
  id: number;
  youtube_url: string | null;
  source_type: string | null;
  status: JobStatus;
  progress: number;
  raw_title: string | null;
  trim_duration: number;
  error_message: string | null;
  processed_video_path: string | null;
  created_at: string;
  finished_at: string | null;
  cta_title: string | null;
}

export interface CtaTemplate {
  id: number;
  title: string;
  cta_video_url: string;
  created_at: string;
}

function downloadHref(jobId: number): string {
  // A bare link target, not a fetch: the browser handles the stream, the
  // Content-Disposition, and the auth header via the proxy.
  return `/api/youtube/jobs/${jobId}/download`;
}

export interface EnqueueResult {
  message: string;
  video_ids: number[];
  source_type: string;
  count: number;
}

/** Paste → job row(s). `selected_short_ids` is for a channel picker (v2). */
export async function enqueueVideo(
  url: string,
  ctaTemplateId: number,
  trimDuration: number,
): Promise<EnqueueResult> {
  return post<EnqueueResult>("/youtube/jobs", {
    url,
    cta_template_id: ctaTemplateId,
    trim_duration: trimDuration,
  });
}

export async function listJobs(limit = 50): Promise<YoutubeJob[]> {
  const data = await get<{ jobs: YoutubeJob[] }>("/youtube/jobs", { limit });
  return data.jobs;
}

export async function getJob(jobId: number): Promise<YoutubeJob> {
  return get<YoutubeJob>(`/youtube/jobs/${jobId}`);
}

export async function deleteJob(jobId: number): Promise<void> {
  await del(`/youtube/jobs/${jobId}`);
}

export async function listCtaTemplates(): Promise<CtaTemplate[]> {
  const data = await get<{ templates: CtaTemplate[] }>("/youtube/cta-templates");
  return data.templates;
}

/** A clip in, a library row out. `title` rides as a form field. */
export async function uploadCtaTemplate(file: File, title: string): Promise<CtaTemplate> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  return postForm<CtaTemplate>("/youtube/cta-templates", body);
}

export async function deleteCtaTemplate(id: number): Promise<void> {
  await del(`/youtube/cta-templates/${id}`);
}

/** Presence-only readout of the tool's config — see `GET /youtube/config`. */
export interface YoutubeConfig {
  youtube_api_key_configured: boolean;
  cookies_configured: boolean;
  proxy_configured: boolean;
  ffmpeg_configured: boolean;
  bucket: string;
}

export async function getYoutubeConfig(): Promise<YoutubeConfig> {
  return get<YoutubeConfig>("/youtube/config");
}

export { downloadHref };