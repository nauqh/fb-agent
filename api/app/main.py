"""FastAPI app. Four screens' worth of routes hang off this.

Pages and sources so far; generate and drafts arrive with Phase 3. See
docs/plan.md.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sqlmodel import Session

from app import generate
from app.db import get_engine, init_db
from app.routes import drafts, pages, prompts, sources
from app.settings import layout, settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    # A restart mid-run leaves rows at `generating` with nothing filling them.
    # Safe to sweep only because there is exactly one writer process.
    with Session(get_engine()) as session:
        stranded = generate.sweep_stranded(session)
    if stranded:
        print(f"swept {stranded} draft(s) stranded by a restart")
    yield


app = FastAPI(title="Facebook Agent", version="0.1.0", lifespan=lifespan)

app.mount(
    "/media",
    StaticFiles(directory=settings.media_root, check_dir=False),
    name="media",
)

app.include_router(drafts.router)
app.include_router(pages.router)
app.include_router(prompts.router)
app.include_router(sources.router)


@app.get("/health")
def health() -> dict:
    """Boot state, no secret values — only the names of missing ones."""
    missing = settings.missing_secrets()
    return {
        "ok": not missing,
        "database": settings.database_path,
        "media_root": settings.media_root,
        "font_present": layout.font_file.exists(),
        "image_size": f"{layout.image.width}x{layout.image.height}",
        "models": {
            "text": settings.gemini_text_model,
            "image": settings.gemini_image_model,
        },
        "missing_secrets": missing,
    }
