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


@pytest.fixture(autouse=True)
def never_buy_an_image(monkeypatch):
    """No test may call the image model. Autouse, so opting in is deliberate.

    Every draft the run finishes now asks for a hero, and `hero.generate` is the
    one function in the app that spends money per call. Without this the suite
    bills Google on every `POST /generate` test — which it did, once, before
    this existed. Tests that need pixels use the `illustrated` fixture.
    """
    from app.image import hero

    def refuse(*_args, **_kwargs):
        raise AssertionError(
            "a test called hero.generate, which is a paid API call. Use the "
            "`illustrated` fixture."
        )

    monkeypatch.setattr(hero, "generate", refuse)


@pytest.fixture
def illustrated(monkeypatch):
    """A hero without the invoice. Returns a real, decodable PNG.

    Real bytes rather than a sentinel because the compositor genuinely opens
    them — a stub that is not an image tests the error path by accident.
    """
    import io

    from PIL import Image

    from app.image import hero

    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), (40, 70, 120)).save(buffer, format="PNG")
    png = buffer.getvalue()

    monkeypatch.setattr(
        hero,
        "generate",
        lambda *a, **k: hero.Hero(png, settings.gemini_image_model),
    )
    return png


@pytest.fixture
def a_photograph() -> bytes:
    """What an operator uploads for the circle. A real PNG, not a sentinel."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1200, 900), (200, 120, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    """Written images go to the test's own directory, not `api/media`.

    `media.store` is built at import from `settings.media_root`, so patching the
    setting after the fact changes nothing — the object is what has to move.
    """
    from app import media

    monkeypatch.setattr(media, "store", media.LocalMediaStore(str(tmp_path / "media")))
    return tmp_path / "media"


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
