"""The job processor, offline.

No network and no ffmpeg. The pipeline's two seams — the download and the
trim/concat — are stubbed at the module boundary (`process._download_source`
and `ffmpeg.process_video`), so the test proves the *orchestration*: progress
lands, the CTA is fetched, the final file reaches storage, and a failure marks
the row `failed` with the message the operator sees. The real yt-dlp/ffmpeg
integration is the spike, not the suite.

The one piece that is exercised for real is the CTA download
(`_download_cta`): httpx against a local file URL would be a fake too, so it is
stubbed by writing the CTA file into place before the run.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.models import CtaTemplate, JobStatus, YoutubeJob
from app.youtube import process


@pytest.fixture
def job(session: Session) -> YoutubeJob:
    cta = CtaTemplate(
        title="Follow us",
        cta_video_url="https://cta.example/follow.mp4",
    )
    session.add(cta)
    session.commit()
    session.refresh(cta)

    row = YoutubeJob(
        youtube_url="https://www.youtube.com/shorts/EM41yq0OUQ4",
        source_type="direct",
        trim_duration=3,
        cta_template_id=cta.id,
        status=JobStatus.PROCESSING,
        # The real worker sets this in `_claim`; the fixture models the post-
        # claim state a `run_job` call finds.
        started_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _stub_download(monkeypatch, title: str | None = "Original title"):
    """The download seam. Records the URL it was asked for and returns a title.

    Leaves a real (tiny) file so the subsequent steps find something.
    """

    def fake(job, output_path):
        open(output_path, "wb").write(b"video-bytes")
        return title

    monkeypatch.setattr(process, "_download_source", fake)
    return fake


def _stub_ffmpeg(monkeypatch):
    """The trim/concat seam. Produces a real final file."""
    import pathlib

    def fake(raw, cta, seconds, trimmed, final):
        pathlib.Path(final).write_bytes(b"processed-bytes")

    monkeypatch.setattr(process, "process_video", fake)


def _stub_cta(monkeypatch):
    """The CTA-to-disk seam. The fixture's `cta.example` URL must not be
    fetched over the network; write the clip into place."""
    import pathlib

    def fake(url: str, output_path: str) -> None:
        pathlib.Path(output_path).write_bytes(b"cta-bytes")

    monkeypatch.setattr(process, "_download_cta", fake)


def test_run_job_completes(job, session, monkeypatch):
    _stub_download(monkeypatch)
    _stub_cta(monkeypatch)
    _stub_ffmpeg(monkeypatch)

    process.run_job(job.id)  # type: ignore[arg-type]

    session.expire_all()
    updated = session.get(YoutubeJob, job.id)
    assert updated.status == JobStatus.COMPLETED
    assert updated.progress == 100
    assert updated.processed_video_path is not None
    assert updated.raw_title == "Original title"
    assert updated.started_at is not None
    assert updated.finished_at is not None
    assert updated.error_message is None


def test_run_job_download_failure_marks_failed(job, session, monkeypatch):
    def fail(url, output_path):
        raise RuntimeError("YouTube refused the download (session expired)")

    monkeypatch.setattr(process, "_download_source", fail)

    process.run_job(job.id)  # type: ignore[arg-type]

    session.expire_all()
    updated = session.get(YoutubeJob, job.id)
    assert updated.status == JobStatus.FAILED
    assert "YouTube refused" in (updated.error_message or "")
    assert updated.finished_at is not None