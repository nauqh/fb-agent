"""Make the file: download, trim, CTA-append, upload — and consume the queue.

This is the worker's heart and the worker's loop in one module. The old tool
spread it over `processVideoJob.ts`, `ffmpegService.ts`, `videoWorker.ts` and
`startWorker.ts` (plus a Redis queue); here the *row is the job* — exactly the
pattern `generate` already set — and a daemon thread in the API process
replaces BullMQ + Upstash + the VPS worker (five videos a day is a couple of
minutes of CPU). The in-process thread and the single-writer deploy shape are
the two halves of one decision; both are commented where they matter.

Progress lands on the row at the old tool's waypoints (20/35/50/90/100), so a
polling client renders a moving bar and a crashed process leaves a row at the
waypoint it died at, which the startup sweep finds. A failure belongs on the
row — the operator sees the message and the loop continues. Same rule
`generate` lives by ("an exception here would land in a log nobody reads").

The ffmpeg half is subprocess, not a wrapper: the old tool used
`fluent-ffmpeg`, a Node wrapper that shells out to the `ffmpeg` *binary*; this
one calls the same binary with `subprocess.run` and a list of arguments — no
shell, no string interpolation, and the filtergraph lifted verbatim from
`ffmpegService.ts` because the geometry was already settled there:

- trim keeps the **first** N seconds (`-t N`), which is the tool's whole
  product: the hook that earned the views, capped at the operator's N.
- the CTA is scaled and padded to the *source* dimensions (letterbox, centred,
  `fps=30`), then concatenated after the hook with matching audio — the two
  clips become one file at the hook's resolution.
- output is H.264/AAC with `+faststart`, re-encoded rather than stream-copied;
  a copy could not join two differently-encoded clips.

The CTA clip is fetched at job time from `cta_template.cta_video_url`, not at
enqueue time: the clip library changes between the two, and the file the job
actually used is what the row should reflect. The URL must resolve when the
job runs, which is the same live-URL rule the images live by.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from loguru import logger
from sqlmodel import Session, select

from app.db import get_engine
from app.models import CtaTemplate, JobStatus, YoutubeJob
from app.settings import settings
from app.youtube import sources
from app.youtube import storage as ytstore

CTA_TIMEOUT = 120.0
CTA_MAX_BYTES = 200 * 1024 * 1024
POLL_SECONDS = 5.0

_TMP = Path(tempfile.gettempdir())


class FfmpegError(RuntimeError):
    """ffmpeg refused or is missing. The job row carries the message."""


# --- ffmpeg ------------------------------------------------------------


def ffmpeg_binary() -> str:
    override = settings.ffmpeg_path.strip()
    if override:
        if not Path(override).exists():
            raise FfmpegError(f"FFMPEG_PATH points at a missing file: {override}")
        return override
    found = shutil.which("ffmpeg")
    if found is None:
        raise FfmpegError(
            "ffmpeg is not installed. Install it (winget install Gyan.FFmpeg on "
            "Windows, apt-get install ffmpeg in the container) or set FFMPEG_PATH."
        )
    return found


def _ffprobe_binary() -> str:
    """`ffprobe` ships beside `ffmpeg`; `FFMPEG_PATH` names the directory.

    Both binaries come from the same install (winget, apt, brew), so if
    `FFMPEG_PATH` is set it points at a directory containing both. When PATH is
    set (post-winget shell, container) they are both found by `which`.
    """
    override = settings.ffmpeg_path.strip()
    if override:
        return str(Path(override).parent / "ffprobe")
    found = shutil.which("ffprobe")
    if found is None:
        raise FfmpegError(
            "ffprobe is not installed. It ships with ffmpeg — install ffmpeg."
        )
    return found


def probe_dimensions(video_path: str) -> tuple[int, int]:
    """Width × height of the hook clip, read before the concat filtergraph.

    The CTA is scaled to these — the output must come out at the source's
    resolution or the channel's Shorts look off-standard on mobile.
    """
    command = [
        _ffprobe_binary(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        video_path,
    ]
    result = _run(command)
    streams = (json.loads(result.stdout) or {}).get("streams") or []
    if not streams or not streams[0].get("width") or not streams[0].get("height"):
        raise FfmpegError(f"Could not read dimensions of {video_path}.")
    return int(streams[0]["width"]), int(streams[0]["height"])


def trim_video(input_path: str, output_path: str, seconds: int) -> None:
    """Keep the first `seconds` s. Worth stating since the tool's purpose is
    often misread: this is not removing a bad head, it is *keeping the hook*."""
    _run(
        [
            ffmpeg_binary(),
            "-y",
            "-i",
            input_path,
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )


def concat_with_cta(hook_path: str, cta_path: str, output_path: str) -> None:
    """Hook, then CTA, at the hook's dimensions. The old filtergraph verbatim."""
    width, height = probe_dimensions(hook_path)
    scale_pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    )
    _run(
        [
            ffmpeg_binary(),
            "-y",
            "-i",
            hook_path,
            "-i",
            cta_path,
            "-filter_complex",
            (
                f"[0:v]{scale_pad}[v0];"
                f"[1:v]{scale_pad}[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]"
            ),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )


def process_video(
    raw_path: str,
    cta_path: str,
    trim_seconds: int,
    trimmed_path: str,
    final_path: str,
) -> None:
    """Trim then append — the ordering of the output is the product."""
    trim_video(raw_path, trimmed_path, trim_seconds)
    concat_with_cta(trimmed_path, cta_path, final_path)


# --- job body ---------------------------------------------------------------


def run_job(job_id: int) -> None:
    """Process one job row, in its own session (the worker outlives its
    requester, exactly like `generate.run_drafts`)."""
    with Session(get_engine()) as session:
        job = session.get(YoutubeJob, job_id)
        if job is None or job.status is not JobStatus.PROCESSING:
            return
        _run_one(session, job)


def _run_one(session: Session, job: YoutubeJob) -> None:
    job_id = job.id
    raw_path = _tmp(f"raw_{job_id}.mp4")
    cta_path = _tmp(f"cta_{job_id}.mp4")
    trimmed_path = _tmp(f"trimmed_{job_id}.mp4")
    final_path = _tmp(f"final_{job_id}.mp4")
    temp_files = [raw_path, cta_path, trimmed_path, final_path]

    try:
        template = session.get(CtaTemplate, job.cta_template_id)
        if template is None:
            raise RuntimeError("CTA template not found")
        cta_url = (template.cta_video_url or "").strip()
        if not cta_url:
            raise RuntimeError(f"CTA template {template.id!r} has no video URL")

        _progress(session, job, "downloading the source", 20)
        title = _download_source(job, raw_path)
        if title:
            job.raw_title = title[:200]
            session.add(job)
            session.commit()

        _progress(session, job, "fetching the CTA clip", 35)
        _download_cta(cta_url, cta_path)

        _progress(session, job, "trimming and appending the CTA", 50)
        process_video(raw_path, cta_path, job.trim_duration, trimmed_path, final_path)

        _progress(session, job, "uploading the processed video", 90)
        _upload(job, session, final_path)
        _progress(session, job, "done", 100)
        logger.info(
            "youtube job {} completed {} ({}s trim, cta {})",
            job_id,
            job.raw_title or job.youtube_url or "upload",
            job.trim_duration,
            template.id,
        )
    except Exception as error:  # noqa: BLE001 — the row is where a failure goes
        logger.error(
            "youtube job {} failed: {}", job_id, f"{type(error).__name__}: {error}"
        )
        job.status = JobStatus.FAILED
        job.error_message = (f"{type(error).__name__}: {error}")[:500]
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 100
        session.add(job)
        session.commit()
    finally:
        for path in temp_files:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def _download_source(job: YoutubeJob, raw_path: str) -> str | None:
    """The source bytes and its title.

    A `channel_short` job downloads the concrete Short its URL resolved to
    (the resolution decides *which* video), while a `direct` job downloads the
    URL itself. The title comes back from yt-dlp as metadata — the same
    uncensored title the old tool stored and then offered as the schedule
    default.
    """
    try:
        if job.source_type == "channel_short":
            url = _resolve_short_url(job)
            return sources.download_video(url, raw_path)
        if not job.youtube_url:
            raise RuntimeError("job has no source URL")
        return sources.download_video(job.youtube_url, raw_path)
    except sources.YoutubeDlError as error:
        raise RuntimeError(str(error)) from error


def _resolve_short_url(job: YoutubeJob) -> str:
    """The URL to actually download for a ranked Short. Cached on the row when
    the discovery listing is fresh; falls back to a fresh lookup."""
    if job.resolved_short_url:
        return job.resolved_short_url
    if not job.channel_shorts_url:
        raise RuntimeError("channel_short job has no channel URL")
    short = sources.resolve_by_rank(job.channel_shorts_url, job.shorts_rank or 1)
    return short.url


def _download_cta(url: str, output_path: str) -> None:
    """The CTA clip, as bytes, from its public URL. The worker needs the file
    on disk twice per video, so the URL must still resolve at job time."""
    if not url.startswith("http://") and not url.startswith("https://"):
        raise RuntimeError(f"CTA URL is not http(s): {url}")
    try:
        response = httpx.get(url, timeout=CTA_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError(
            f"could not fetch CTA clip ({type(error).__name__}): {url}"
        ) from error
    if not response.content or len(response.content) > CTA_MAX_BYTES:
        raise RuntimeError("CTA clip is empty or larger than 200 MB")
    Path(output_path).write_bytes(response.content)


def _upload(job: YoutubeJob, session: Session, final_path: str) -> None:
    """Processed bytes → the bucket, then the row points at the path (and the
    URL the client/browser/Metricool fetch). The path stays relative so a
    bucket rename is an env change, not an UPDATE (the images' rule)."""
    data = Path(final_path).read_bytes()
    stored = ytstore.store.save(data, f"{job.id}_processed.mp4")
    job.processed_video_path = stored
    job.status = JobStatus.COMPLETED
    job.finished_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _progress(session: Session, job: YoutubeJob, step: str, pct: int) -> None:
    """Advance the progress columns only. `status` is owned by the lifecycle:
    QUEUED at insert, PROCESSING at claim, COMPLETED/FAILED at the end — if
    this function set it, the final `_progress(100)` after `_upload` would
    clobber the COMPLETED it just committed (the bug that made the row read
    `processing` forever while the log said completed)."""
    job.progress = pct
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _tmp(name: str) -> str:
    return str(_TMP / name)


def _run(command: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=60 * 10,
        )
    except subprocess.CalledProcessError as error:
        tail = (error.stderr or "").strip().splitlines()
        raise FfmpegError(
            "ffmpeg refused: " + ((tail[-1] if tail else "") or error)
        ) from error
    except (subprocess.TimeoutExpired, OSError) as error:
        raise FfmpegError(f"ffmpeg failed to run: {type(error).__name__}") from error


# --- the worker loop -------------------------------------------------------


def sweep_stranded(session: Session) -> int:
    """A restart mid-job leaves rows at `processing` with nothing filling
    them. Mark them failed. Safe only because there is exactly one worker
    process (two would kill live runs, which is why the deploy pins one)."""
    stranded = session.exec(
        select(YoutubeJob).where(YoutubeJob.status == JobStatus.PROCESSING)
    ).all()
    for job in stranded:
        job.status = JobStatus.FAILED
        job.error_message = "Interrupted by a restart before it finished."
        job.finished_at = datetime.now(timezone.utc)
        session.add(job)
    session.commit()
    return len(stranded)


def _claim(session: Session) -> YoutubeJob | None:
    """One queued job, oldest first, marked `processing` before return.

    No `FOR UPDATE SKIP LOCKED`: the single-worker rule is the deploy shape,
    and a second process would need more than a lock (the startup sweep would
    kill its live runs). The `start` docstring says so too.
    """
    job = session.exec(
        select(YoutubeJob)
        .where(YoutubeJob.status == JobStatus.QUEUED)
        .order_by(YoutubeJob.created_at)  # type: ignore[arg-type]
        .limit(1)
    ).first()
    if job is None:
        return None
    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()
    return job


def _one_pass() -> int:
    """Claim and run one job.

    Returns jobs_processed for the log line — logging lives at the boundary of
    a pass, never per step (the loggingsucks.com rule `generate` already
    quotes). The old tool's second half of every pass — reconciling overdue
    Metricool schedules — was cut with the publish scope (the `youtube_schedule`
    table and `schedule.py` are gone).
    """
    with Session(get_engine()) as session:
        job = _claim(session)
        # The id is read *inside* the session: `_claim` commits, the `with`
        # closes, and the returned instance goes detached — touching any
        # attribute after that raises DetachedInstanceError (which is exactly
        # what the first UI-driven run found). The id is all the next step needs.
        job_id = job.id if job is not None else None
    jobs = 0
    if job_id is not None:
        logger.info("youtube worker claiming job {}", job_id)
        run_job(job_id)
        jobs = 1
    return jobs


def run_forever() -> None:
    """The worker loop. Logs one line per pass only when something happened."""
    logger.info("youtube worker started (polling every {}s)", POLL_SECONDS)
    while True:
        try:
            jobs = _one_pass()
            if jobs:
                logger.info("youtube worker pass: {} job(s)", jobs)
        except Exception:  # noqa: BLE001 — one bad pass must not kill the loop
            logger.exception("youtube worker pass failed")
        time.sleep(POLL_SECONDS)


def start() -> threading.Thread | None:
    """Start the worker thread. Called from the app lifespan, and tests disable
    it by setting `youtube_worker_enabled` false (conftest autouse fixture —
    the thread must not run against the test database)."""
    if not settings.youtube_worker_enabled:
        logger.info("youtube worker disabled (youtube_worker_enabled=false)")
        return None

    thread = threading.Thread(target=run_forever, name="youtube-worker", daemon=True)
    thread.start()
    return thread