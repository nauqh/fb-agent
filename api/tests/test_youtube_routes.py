"""The youtube routes, offline.

The two routes that never touch the network — enqueueing a single video and
the job list — are exercised here against the test client. Scheduling and the
channel picker would need Metricool/YouTube stubs; those live in the module
tests (schedule body shape, reconcile fold), which is where the logic is.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import CtaTemplate, JobStatus, YoutubeJob


def _cta(session: Session) -> CtaTemplate:
    row = CtaTemplate(title="Follow us", cta_video_url="https://cta.example/f.mp4")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_enqueue_single_video(client: TestClient, session: Session):
    cta = _cta(session)
    response = client.post(
        "/youtube/jobs",
        json={
            "url": "https://www.youtube.com/shorts/EM41yq0OUQ4",
            "cta_template_id": cta.id,
            "trim_duration": 3,
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["count"] == 1
    assert len(payload["video_ids"]) == 1

    job = session.get(YoutubeJob, payload["video_ids"][0])
    assert job is not None
    assert job.status is JobStatus.QUEUED
    assert job.source_type == "direct"
    assert job.trim_duration == 3


def test_enqueue_invalid_url_is_400(client: TestClient, session: Session):
    cta = _cta(session)
    response = client.post(
        "/youtube/jobs",
        json={"url": "https://example.com/not-a-video", "cta_template_id": cta.id},
    )
    assert response.status_code == 400
    assert "Invalid URL" in response.json()["detail"]


def test_enqueue_missing_cta_is_404(client: TestClient, session: Session):
    response = client.post(
        "/youtube/jobs",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "cta_template_id": 999999},
    )
    assert response.status_code == 404


def test_list_jobs_empty(client: TestClient):
    response = client.get("/youtube/jobs")
    assert response.status_code == 200
    assert response.json()["jobs"] == []


def test_delete_live_job_is_409(client: TestClient, session: Session):
    cta = _cta(session)
    row = YoutubeJob(
        youtube_url="https://youtu.be/dQw4w9WgXcQ",
        source_type="direct",
        cta_template_id=cta.id,
        status=JobStatus.PROCESSING,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    response = client.delete(f"/youtube/jobs/{row.id}")
    assert response.status_code == 409