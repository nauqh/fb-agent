"""The YouTube tool's HTTP surface.

Make a video: enqueue a job, pick a channel's Shorts, manage CTA clips, read
back job history, download the produced mp4. Everything here is the old tool's
API routes (`src/app/api/video/…` and `src/app/api/youtube/…`) under the
`/youtube` prefix, with the queue the in-process worker owns (`youtube_job`
rows).

The one request-facing shape worth calling out:

- **`POST /youtube/jobs`** returns ids immediately and the worker fills the
  rows — the operator never waits on the download/trim/concat.

Publishing used to live here too and was **cut** for v1 (the Q2 scope call):
no Metricool scheduling, no brands, no Instagram, no `youtube_schedule` table,
no reconcile. The schedule module, its routes and its table are gone; the
produce loop is the whole product for now.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    CtaTemplate,
    JobStatus,
    YoutubeJob,
)
from app.youtube import (
    sources,
)
from app.youtube import (
    storage as ytstore,
)

router = APIRouter(tags=["youtube"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class JobOut(BaseModel):
    """A job row, with the pieces the browser renders (CTA title, public URL)."""

    id: int
    youtube_url: str | None
    source_type: str | None
    status: str
    progress: int
    raw_title: str | None
    trim_duration: int
    error_message: str | None
    processed_video_path: str | None
    created_at: datetime
    finished_at: datetime | None
    cta_title: str | None


def _job_out(job: YoutubeJob, cta_titles: dict[int, str]) -> JobOut:
    return JobOut(
        id=job.id,  # type: ignore[arg-type]
        youtube_url=job.youtube_url,
        source_type=job.source_type,
        status=job.status.value,
        progress=job.progress,
        raw_title=job.raw_title,
        trim_duration=job.trim_duration,
        error_message=job.error_message,
        processed_video_path=job.processed_video_path,
        created_at=job.created_at,
        finished_at=job.finished_at,
        cta_title=cta_titles.get(job.cta_template_id),
    )


def _cta_titles(session: Session) -> dict[int, str]:
    rows = session.exec(select(CtaTemplate)).all()
    return {row.id: row.title for row in rows if row.id}  # type: ignore[union-attr]


class EnqueueRequest(BaseModel):
    """What a pasted URL (or an upload) becomes. Mirrors the old
    `POST /api/video` body."""

    url: str = ""
    cta_template_id: int
    trim_duration: int = 3
    shorts_limit: int = 1
    selected_short_ids: list[str] = []


# --- jobs ----------------------------------------------------------------


@router.post("/youtube/jobs", status_code=202)
def enqueue_job(body: EnqueueRequest, session: Session = Depends(get_session)):
    """Turn a URL into job row(s) and let the worker have them.

    A single video is one job. A channel URL is up to `shorts_limit` jobs,
    each a ranked Short — or, when `selected_short_ids` is set, exactly the
    picked ones (enriched with rank/view snapshot from the discovery listing,
    so the row keeps a record even after the channel's ranking shifts).
    """
    template = session.get(CtaTemplate, body.cta_template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="CTA template not found")

    source = sources.parse_youtube_source(body.url)
    if source is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid URL. Supported: /shorts/ID, watch?v=..., youtu.be/..., "
                "@channel/shorts."
            ),
        )

    trim = sources.clamp_trim_duration(body.trim_duration)
    shorts = _resolve_shorts_source(source, body)

    jobs: list[YoutubeJob] = []
    channel_url = source.url if source.type == "channel_shorts" else None
    for short in shorts:
        is_direct = source.type == "video" or bool(short.get("id"))
        job = YoutubeJob(
            youtube_url=short["url"] if is_direct else source.url,
            source_type="channel_short" if source.type == "channel_shorts" else "direct",
            youtube_short_id=short.get("id"),
            resolved_short_url=short["url"] if is_direct and source.type == "channel_shorts" else None,
            channel_shorts_url=channel_url,
            shorts_rank=short.get("rank"),
            view_count_snapshot=short.get("view_count"),
            like_count_snapshot=short.get("like_count"),
            trim_duration=trim,
            cta_template_id=template.id,
            status=JobStatus.QUEUED,
        )
        session.add(job)
        jobs.append(job)
    session.commit()

    ids = [job.id for job in jobs if job.id is not None]
    return {
        "message": f"Added {len(ids)} video(s) to the queue" if len(ids) > 1 else "Added to queue",
        "video_ids": ids,
        "source_type": source.type,
        "count": len(ids),
    }


def _resolve_shorts_source(source: sources.YoutubeSource, body: EnqueueRequest) -> list[dict]:
    """The concrete videos to enqueue from a source.

    Returns a list of `{url, id?, rank?, view_count?, like_count?}`. For a
    channel URL with selected ids, the listing is consulted so the rows carry
    the current rank/views of the picked Shorts."""
    if source.type == "video":
        return [{"url": source.url, "rank": 1}]
    if body.selected_short_ids:
        try:
            listed = {item.id: item for item in sources.list_channel_shorts(source.url)}
        except sources.DiscoveryError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        out = []
        for video_id in body.selected_short_ids:
            item = listed.get(video_id)
            out.append(
                {
                    "id": video_id,
                    "url": f"https://www.youtube.com/shorts/{video_id}",
                    "rank": item.rank if item else None,
                    "view_count": item.view_count if item else None,
                    "like_count": item.like_count if item else None,
                }
            )
        return out
    return [
        {
            "url": source.url,
            "rank": rank,
        }
        for rank in range(1, sources.clamp_shorts_limit(body.shorts_limit) + 1)
    ]


@router.get("/youtube/jobs")
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """History, newest first. The browser's job list."""
    rows = session.exec(
        select(YoutubeJob).order_by(YoutubeJob.created_at.desc()).limit(limit)  # type: ignore[arg-type]
    ).all()
    titles = _cta_titles(session)
    return {"jobs": [_job_out(job, titles) for job in rows]}


@router.get("/youtube/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(YoutubeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    return _job_out(job, _cta_titles(session))


@router.get("/youtube/jobs/{job_id}/download")
def download_job(job_id: int, session: Session = Depends(get_session)):
    """The produced mp4, streamed through the API — the `<video>` source and
    the download link in one. The browser talks to one origin (the proxy), so
    the bucket never has to be public to this screen.
    """
    job = session.get(YoutubeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    if job.status is not JobStatus.COMPLETED or not job.processed_video_path:
        raise HTTPException(status_code=409, detail="No processed video to download")
    try:
        data = ytstore.store.read(job.processed_video_path)
    except ytstore.YoutubeStoreError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    filename = f"short-{job_id}.mp4"
    return Response(
        content=data,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/youtube/jobs/{job_id}")
def delete_job(job_id: int, session: Session = Depends(get_session)):
    """History cleanup. Terminal rows only — deleting a live job would tear the
    work out from under the worker, and deleting a queued one loses it forever."""
    job = session.get(YoutubeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Live jobs cannot be deleted.")
    if job.processed_video_path:
        try:
            ytstore.store.delete(job.processed_video_path)
        except ytstore.YoutubeStoreError:
            raise HTTPException(status_code=500, detail="Could not remove the processed video")
    session.delete(job)
    session.commit()
    return {"success": True}


# --- channel shorts ------------------------------------------------------


@router.get("/youtube/channel-shorts")
def channel_shorts(url: str = Query(...), session: Session = Depends(get_session)):
    """The picker listing for `@channel/shorts`. One discovery call (API or
    yt-dlp, chosen inside `discovery`)."""
    source = sources.parse_youtube_source(url)
    if source is None or source.type != "channel_shorts":
        raise HTTPException(status_code=400, detail="URL must be a channel Shorts tab")
    try:
        shorts = sources.list_channel_shorts(source.url)
    except sources.DiscoveryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "channel_url": source.url,
        "shorts": [item.__dict__ for item in shorts],
        "count": len(shorts),
    }


# --- cta templates --------------------------------------------------------


@router.get("/youtube/config")
def youtube_config():
    """What the tool is configured with, read back from the server — the
    same rule `routes/config.py` records about layout.yml: a Settings screen
    showing a hand-kept copy of a config is a screen that can disagree with
    the run it claims to describe.

    Presence only, never values: `youtube_api_key_configured` is true whether
    the key is valid, and `cookies_configured` is true whether the export is
    still fresh. Those are runtime facts the operator learns from a failed
    download, not something a config screen can predict.
    """

    from app.settings import settings as app_settings

    return {
        "youtube_api_key_configured": bool(app_settings.youtube_api_key.strip()),
        "cookies_configured": bool(app_settings.ytdlp_cookies_file.strip()),
        "proxy_configured": bool(app_settings.ytdlp_proxy_url.strip()),
        "ffmpeg_configured": bool(app_settings.ffmpeg_path.strip()),
        "bucket": app_settings.supabase_youtube_bucket,
    }


@router.get("/youtube/cta-templates")
def list_cta_templates(session: Session = Depends(get_session)):
    rows = session.exec(select(CtaTemplate).order_by(CtaTemplate.created_at.desc())).all()  # type: ignore[arg-type]
    return {"templates": [row.model_dump() for row in rows]}


@router.post("/youtube/cta-templates")
def upload_cta_template(
    file: UploadFile,
    title: str | None = None,
    session: Session = Depends(get_session),
):
    """A clip in, a library row out. The bytes are read into memory and written
    to the bucket; the row stores the bucket *path* plus a public URL for the
    worker to fetch at job time."""
    data = file.file.read()
    file.file.close()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Clip is empty or larger than 200 MB")

    stored = ytstore.store.save(data, f"cta-{uuid4().hex[:10]}.mp4")
    row = CtaTemplate(title=title or file.filename or "CTA clip", cta_video_url=ytstore.store.public_url(stored))
    session.add(row)
    session.commit()
    return {**row.model_dump(), "public_url": row.cta_video_url}


@router.delete("/youtube/cta-templates/{template_id}")
def delete_cta_template(template_id: int, session: Session = Depends(get_session)):
    row = session.get(CtaTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No CTA template {template_id}")
    session.delete(row)
    session.commit()
    return {"success": True}
