"""FastAPI app. Four screens' worth of routes hang off this.

Pages and sources so far; generate and drafts arrive with Phase 3. See
docs/plan.md.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sqlmodel import Session

from app import generate
from app.db import get_engine, init_db
from app.routes import config, drafts, pages, prompts, schedule, sources
from app.settings import API_DIR, layout, settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # A restart mid-run leaves rows at `generating` with nothing filling them.
    # Safe to sweep only because there is exactly one writer process.
    with Session(get_engine()) as session:
        stranded = generate.sweep_stranded(session)
    if stranded:
        print(f"swept {stranded} draft(s) stranded by a restart")
    yield


app = FastAPI(title="Facebook Agent", version="0.1.0", lifespan=lifespan)

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

app.include_router(config.router)
app.include_router(drafts.router)
app.include_router(pages.router)
app.include_router(prompts.router)
app.include_router(schedule.router)
app.include_router(sources.router)


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
