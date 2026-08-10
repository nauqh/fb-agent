"""The shared-secret lock on every route.

Written because the API spent its first day on a public Railway domain with no
authentication: every draft readable by anyone with the URL, `POST /generate`
spending Gemini budget on request, and the publish path reaching a real Facebook
page. These tests are what stop that returning quietly.
"""

from conftest import TEST_API_KEY  # tests/ is on sys.path, not a package
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def test_a_request_without_the_key_is_refused(engine, page, monkeypatch):
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    with TestClient(app) as anonymous:
        response = anonymous.get("/pages")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authorised"}


def test_a_request_with_the_wrong_key_is_refused(engine, page, monkeypatch):
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    with TestClient(app, headers={"X-API-Key": "wrong"}) as wrong:
        assert wrong.get("/pages").status_code == 401


def test_the_right_key_is_let_through(client):
    assert client.get("/pages").status_code == 200


def test_health_is_open_so_railway_can_probe_it(engine, monkeypatch):
    """The one exemption. A closed /health fails the platform health check,
    and the deploy never receives traffic to authenticate in the first place."""
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    with TestClient(app) as anonymous:
        response = anonymous.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_a_blank_key_denies_rather_than_allows(engine, page, monkeypatch):
    """The direction that matters. An unset `API_KEY` must not mean "open".

    A deploy missing the variable comes up refusing everything, which is
    noticed. The other way round it comes up serving everything to everyone,
    which looks exactly like a working deploy.
    """
    monkeypatch.setattr(settings, "api_key", "")
    with TestClient(app) as anonymous:
        assert anonymous.get("/pages").status_code == 401
        # And an empty header does not match an empty key.
        assert anonymous.get("/pages", headers={"X-API-Key": ""}).status_code == 401


def test_the_assets_mount_is_covered_too(client, engine, page, monkeypatch):
    """StaticFiles is not a route function, so a `Depends` could never have
    guarded it. The middleware does."""
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    with TestClient(app) as anonymous:
        assert anonymous.get("/assets/fonts/Arial-Bold.ttf").status_code == 401
    assert client.get("/assets/fonts/Arial-Bold.ttf").status_code == 200


def test_a_missing_key_is_reported_by_health(engine, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    with TestClient(app) as anonymous:
        assert "API_KEY" in anonymous.get("/health").json()["missing_secrets"]
