"""FastAPI app. Four screens' worth of routes hang off this.

Pages and sources so far; generate and drafts arrive with Phase 3. See
docs/plan.md.
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import generate
from app.db import get_engine, init_db
from app.log import logger, setup_logging
from app.routes import (
    competitors,
    config,
    drafts,
    feeds,
    overview,
    pages,
    prompts,
    schedule,
    sources,
)
from app.settings import API_DIR, layout, settings
from app.youtube import process as youtube_worker
from app.youtube import routes as youtube_routes
from app.youtube import sources as youtube_sources


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    # A restart mid-run leaves rows at `generating` with nothing filling them.
    # Safe to sweep only because there is exactly one writer process.
    with Session(get_engine()) as session:
        stranded = generate.sweep_stranded(session)
    if stranded:
        logger.info("swept {} draft(s) stranded by a restart", stranded)
    # Same for processed videos: a restart mid-job leaves `youtube_job` rows at
    # `processing`.
    with Session(get_engine()) as session:
        job_stranded = youtube_worker.sweep_stranded(session)
    if job_stranded:
        logger.info("swept {} youtube job(s) stranded by a restart", job_stranded)
    # Before any job runs: turn YTDLP_COOKIES_B64 into the file yt-dlp wants.
    # A host that rebuilds its disk every deploy can only be handed a variable.
    youtube_sources.install_cookies_from_env()
    # The one consumer of `youtube_job` rows. Five videos a day; a daemon thread
    # in the API process replaces the old VPS pm2 worker + Redis queue.
    youtube_worker.start()
    yield


app = FastAPI(title="Facebook Agent", version="0.1.0", lifespan=lifespan)

OPEN_PATHS = frozenset({"/health"})
"""Reachable without the key. Railway probes `/health` before routing traffic.

It reports the database host, the bucket name and which secrets are missing —
never a secret's value — which is the most that can be given away here without
making the probe useless.
"""


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """The whole of the authentication. One shared secret in `X-API-Key`.

    Middleware rather than a `Depends` on each router: a dependency is something
    the next route can be written without, and the failure is silent — a new
    endpoint that is simply unprotected. This cannot be forgotten.

    It also covers the `/assets` mount, which `Depends` could not: those are
    served by StaticFiles, not by a route function.

    Nothing is exempt but `/health`. The API sat on a public Railway domain with
    no authentication at all — every draft, caption and image URL readable by
    anyone with the address, `POST /generate` spending Gemini budget on demand,
    and the publish path reaching a real Facebook page with
    `METRICOOL_PUBLISH_AS_DRAFT` as the only thing in the way.

    A blank `API_KEY` denies everything rather than allowing everything, and
    that needs the explicit check below: `compare_digest("", "")` is **True**,
    so an unset key plus a request with no header would otherwise authenticate
    successfully. That was written here as a comment claiming the opposite until
    `test_a_blank_key_denies_rather_than_allows` disagreed — the failure mode
    being a deploy that comes up wide open and looks exactly like a working one.
    """
    if request.url.path not in OPEN_PATHS:
        sent = request.headers.get("x-api-key", "")
        # Constant-time. `==` on a secret returns as soon as two bytes differ,
        # so response timing leaks the key one character at a time to anyone
        # patient enough to measure it.
        if not settings.api_key or not secrets.compare_digest(sent, settings.api_key):
            return JSONResponse({"detail": "Not authorised"}, status_code=401)
    return await call_next(request)

# There is no `/media` mount. Draft pictures live in a Supabase bucket and the
# browser fetches them from there directly — the API serves the *URL* on the row
# (`Draft.composed_image_url`) and never the bytes. Re-adding a mount here would
# be a second, staler way to reach the same picture.

# The committed assets — watermarks, the font — served so the browser can show
# the same file the compositor draws with. `page.watermark_image_path` is
# already relative to API_DIR, so `/assets/...` addresses it directly.
#
# Without this the frontend kept its own copy under `web/public/watermarks/`,
# hand-synced, and the two disagreed the moment the Page pointed somewhere new.
app.mount(
    "/assets",
    StaticFiles(directory=str(API_DIR / "assets"), check_dir=False),
    name="assets",
)

app.include_router(competitors.router)
app.include_router(config.router)
app.include_router(drafts.router)
app.include_router(feeds.router)
app.include_router(overview.router)
app.include_router(pages.router)
app.include_router(prompts.router)
app.include_router(schedule.router)
app.include_router(sources.router)
app.include_router(youtube_routes.router)


@app.get("/health")
def health() -> dict:
    """Boot state, no secret values — only the names of missing ones."""
    missing = settings.missing_secrets()
    return {
        "ok": not missing,
        # Host and database only. This endpoint is unauthenticated and the URL
        # now carries a password.
        "database": settings.database_summary,
        "media_bucket": settings.supabase_bucket,
        "font_present": layout.font_file.exists(),
        "image_size": f"{layout.image.width}x{layout.image.height}",
        "models": {
            "text": settings.gemini_text_model,
            "image": settings.gemini_image_model,
        },
        "missing_secrets": missing,
    }
