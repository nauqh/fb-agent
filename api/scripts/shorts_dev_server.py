"""Temporary dev server for the Shorts UI — no production database.

The app's real backend is Supabase Postgres and `app/db.py` refuses anything
else, and touching the production database is off-limits. So this script is
the test-suite's trick, lifted to a process: point the engine at a throwaway
sqlite file, point the youtube store at a local directory, seed the CTA clip
from the repo root, and run the real app + the real worker against it.

Nothing writes anywhere but `api/.shorts-dev/` (gitignored). The API key is read
from `web/.env.local` so the Next proxy's `x-api-key` header authenticates.

ffmpeg is resolved by the app itself — `FFMPEG_PATH` if set, else PATH. If it
is on neither, the job fails with `ffmpeg is not installed`; install it
(`winget install Gyan.FFmpeg`) rather than editing this file.

Usage:
    uv run python scripts/shorts_dev_server.py [port]
"""
from __future__ import annotations

import http.server
import pathlib
import re
import shutil
import socketserver
import sys
import threading

API_DIR = pathlib.Path(__file__).resolve().parent.parent
ROOT = API_DIR.parent
sys.path.insert(0, str(API_DIR))

import uvicorn  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app import db as db_module  # noqa: E402
from app import main as main_module  # noqa: E402
from app.models import CtaTemplate  # noqa: E402
from app.settings import settings  # noqa: E402
from app.youtube import storage as ytstore  # noqa: E402


def _api_key_from_web_env() -> str:
    env_local = ROOT / "web" / ".env.local"
    if not env_local.exists():
        raise SystemExit("web/.env.local not found — cannot read the API key")
    match = re.search(r"^API_KEY=(.+)$", env_local.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("API_KEY not in web/.env.local")
    return match.group(1).strip()


def _serve_directory(directory: pathlib.Path) -> int:
    """Serve `directory` unauthenticated on a free port; return the port.

    Separate from the app on purpose. The real CTA and processed-video URLs are
    external (a public bucket), and the app's key middleware guards every path
    it owns — the worker's bare `httpx.get` of a CTA clip must not meet that
    guard.

    Port 0 asks the OS for a free port instead of naming one. Windows lets a
    second process bind a port that is already bound, so a fixed port can look
    like it started while an older server keeps answering (the trap recorded in
    CLAUDE.md); asking for 0 cannot collide.
    """

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):  # silence the per-request log
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def _repoint_local_ctas(session: Session, media_port: int) -> int:
    """Rewrite the port of every `127.0.0.1` CTA url. Returns how many changed."""
    changed = 0
    for template in session.exec(select(CtaTemplate)).all():
        url = template.cta_video_url or ""
        fixed = re.sub(r"^http://127\.0\.0\.1:\d+/", f"http://127.0.0.1:{media_port}/", url)
        if fixed != url:
            template.cta_video_url = fixed
            session.add(template)
            changed += 1
    if changed:
        session.commit()
    return changed


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    # A stable dev directory, not a volatile temp dir: the CTA clip and the
    # processed videos must survive restarts, or the browser loses the
    # audio/video the moment Windows cleans temp (which is exactly what the
    # first "no preview" run hit).
    dev_root = API_DIR / ".shorts-dev"
    scratch = dev_root / "run"
    media = scratch / "media"
    media.mkdir(parents=True, exist_ok=True)
    print(f"dev root: {dev_root}")

    engine = create_engine(
        f"sqlite:///{scratch / 'dev.db'}",
        connect_args={"check_same_thread": False},
    )
    db_module._engine = engine
    SQLModel.metadata.create_all(engine)  # never alembic

    # The real app's startup migrates via alembic — a no-op here, since the
    # shim builds its schema from the models.
    main_module.init_db = lambda: None  # type: ignore[assignment]

    settings.api_key = _api_key_from_web_env()

    # Uploaded CTA clips and processed videos land in one directory, served by
    # one static server, so every `public_url` the worker hands out resolves.
    media_port = _serve_directory(media)
    ytstore.store = ytstore.DirectoryYoutubeStore(
        str(media), base_url=f"http://127.0.0.1:{media_port}"
    )

    cta_source = ROOT / "BibleFocusApp.mp4"
    if cta_source.exists():
        shutil.copy2(cta_source, media / cta_source.name)
        cta_url = f"http://127.0.0.1:{media_port}/{cta_source.name}"
        with Session(engine) as session:
            if session.exec(select(CtaTemplate)).first() is None:
                session.add(CtaTemplate(title="Bible Focus", cta_video_url=cta_url))
                session.commit()
                print(f"seeded CTA 'Bible Focus' -> {cta_url}")
            else:
                # The database outlives the process but the media port does not,
                # so every localhost CTA row is stale the moment this restarts.
                # A job would download the clip from a dead port and fail deep in
                # ffmpeg. Re-point them at the port this run actually opened.
                moved = _repoint_local_ctas(session, media_port)
                if moved:
                    print(f"re-pointed {moved} CTA url(s) at :{media_port}")
    else:
        # Not fatal: Shorts Settings can upload one, and that is the real path
        # an operator takes. Jobs just cannot run until there is a template.
        print(
            f"no CTA seeded — {cta_source} is missing. "
            "Upload a clip on /shorts/settings before queueing a job."
        )

    print(f"serving on :{port} with API key {settings.api_key[:4]}…")
    uvicorn.run(main_module.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
