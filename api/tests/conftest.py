"""A throwaway database per test, and a client bound to it.

Nothing here touches the network. The three adapters are the seam, so tests
substitute them there rather than intercepting HTTP — if a test ever needs to
mock past an adapter, the module is the wrong shape.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    # pytest puts the rootdir on sys.path only when it finds a package; `app`
    # sits beside `tests`, not under it.
    sys.path.insert(0, str(API_DIR))

from app import db as db_module  # noqa: E402
from app.models import Page  # noqa: E402
from app.settings import settings  # noqa: E402


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(db_module, "_engine", None)
    db_module.init_db()
    yield db_module.get_engine()
    monkeypatch.setattr(db_module, "_engine", None)


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def page(session) -> Page:
    page = Page(
        name="History Retraced",
        facebook_page_id="569035169625026",
        metricool_blog_id="4605385",
    )
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@pytest.fixture
def client(engine, page):
    from app.main import app

    return TestClient(app)
