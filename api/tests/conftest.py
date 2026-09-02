"""A throwaway database per test, and a client bound to it.

Nothing here touches the network. The three adapters are the seam, so tests
substitute them there rather than intercepting HTTP — if a test ever needs to
mock past an adapter, the module is the wrong shape.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    # pytest puts the rootdir on sys.path only when it finds a package; `app`
    # sits beside `tests`, not under it.
    sys.path.insert(0, str(API_DIR))

from app import db as db_module  # noqa: E402
from app.models import Feed, Page  # noqa: E402
from app.settings import settings  # noqa: E402


@pytest.fixture(autouse=True)
def youtube_worker_off(monkeypatch):
    """The in-process youtube worker must not run against the test database.

    The worker is a daemon thread started by the app lifespan; with this off,
    `TestClient(app)` boots clean and no thread ever claims a test job row.
    The worker's own loop is tested by driving `worker._one_pass` directly,
    which needs no thread.
    """
    monkeypatch.setattr(settings, "youtube_worker_enabled", False)


@pytest.fixture(autouse=True)
def youtube_media_root(tmp_path, monkeypatch):
    """Youtube store writes go to the test's own directory.

    `DirectoryYoutubeStore` is the real module's own dev/test store — the suite
    used to carry a duplicate of it, as did the Shorts dev server.
    """
    from app.youtube import storage as ytstore

    monkeypatch.setattr(
        ytstore, "store", ytstore.DirectoryYoutubeStore(str(tmp_path / "youtube"))
    )
    return tmp_path / "youtube"


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


class LocalMediaStore:
    """A `MediaStore` backed by a directory. The suite's only storage.

    This used to be the app's store. It lives here now because the app has one
    backend — Supabase — and a second production implementation would exist only
    to be the thing dev accidentally tested against instead.

    It stays as a *fake* because the alternative is worse: every test that saves
    a picture would need an HTTP mock, and 244 of them would go from a file
    write to a round trip through `httpx.MockTransport`. Same reason it keeps
    `path()`, which is not on the Protocol — tests assert against the file on
    disk rather than through the object that wrote it.
    """

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def save(self, data: bytes, name: str) -> str:
        bucket = datetime.now(timezone.utc).strftime("%Y-%m")
        target = self.root / bucket / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{bucket}/{name}"

    def read(self, stored: str) -> bytes:
        return self.path(stored).read_bytes()

    def delete(self, stored: str) -> None:
        self.path(stored).unlink(missing_ok=True)

    def path(self, stored: str) -> Path:
        return self.root / stored


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    """Written images go to the test's own directory, never to the bucket.

    Autouse, and the same shape as `never_buy_an_image`: the real store now
    talks to Supabase, so a test that slipped past this would write into a real
    bucket rather than into a directory nobody looks at.
    """
    from app import media

    monkeypatch.setattr(media, "store", LocalMediaStore(str(tmp_path / "media")))
    return tmp_path / "media"


def _configure_sqlite(dbapi_connection, _record) -> None:
    """Applied to every connection, not just the first. Neither is a perf knob.

    `foreign_keys` is off by default in SQLite and is per-connection. Without
    it, every foreign key declared in models.py is decorative — a draft can
    point at a page id that does not exist and nothing complains, so a test
    would pass on data Postgres rejects. Postgres enforces them unasked.

    `busy_timeout` defaults to 0, meaning a locked database fails instantly
    rather than waiting; a generate run commits from a background thread.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """A throwaway SQLite file per test. The only SQLite anywhere in this repo.

    Built here rather than by handing `app.db` a `sqlite://` URL, because that
    module is Postgres-only and rejects anything else. That refusal is the
    point: the app has exactly one backend, and SQLite is a property of the
    suite — offline, ~60s, no shared state between tests — not a second
    configuration the app supports.

    The two schemas agree because the enum columns are pinned to `VARCHAR` in
    models.py. Left as native Postgres enums, Postgres would build a schema this
    file cannot, and the suite could never have caught the bug that made a
    stored `SourceKind` load back as a bare `str`.

    `check_same_thread` is off because FastAPI runs background tasks on a
    different thread to the request that spawned them, and a generate run
    outlives its request.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _configure_sqlite)
    # Assigned, not configured: `get_engine` would refuse this URL.
    monkeypatch.setattr(db_module, "_engine", engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()
    monkeypatch.setattr(db_module, "_engine", None)


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def page(session) -> Page:
    """The Page, with feeds.

    The feeds are part of this fixture rather than a separate one because they
    stopped being configuration and became rows: `rss.curated_hosts` reads the
    table, and `POST /generate` refuses an RSS item whose host is not in it. A
    Page with no feeds is now a Page that cannot accept an RSS Source Item at
    all, which is a fair rule and a confusing test failure — it surfaces as a
    404 on the Draft that was never created.

    Two feeds, not one, so that a test asserting on the set cannot pass by
    accident on a single row. The hosts match the ones `test_generate.CURATED`
    and the adapter tests use.
    """
    page = Page(
        name="History Retraced",
        facebook_page_id="569035169625026",
        metricool_blog_id="4605385",
    )
    session.add(page)
    session.commit()
    session.refresh(page)

    session.add_all(
        [
            Feed(
                page_id=page.id,
                name="Smithsonian Magazine",
                url="https://www.smithsonianmag.com/rss/history/",
            ),
            Feed(
                page_id=page.id,
                name="All That's Interesting",
                url="https://allthatsinteresting.com/feed",
            ),
        ]
    )
    session.commit()
    return page


TEST_API_KEY = "test-key"


@pytest.fixture
def client(engine, page, monkeypatch):
    """A client that is already authenticated.

    The key is set and sent here rather than in each test because the 253 tests
    that predate authentication are about routes, not about the lock — making
    every one of them assert a header would say nothing they are for.
    `test_auth.py` covers the lock itself, including the unauthenticated case.
    """
    from app.main import app

    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})
