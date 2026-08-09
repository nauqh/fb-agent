"""Five tiers of configuration, deliberately kept apart.

  config/layout.yml   how the image looks — identical for every Page, never
                      per-page
  config/sources.yml  where material comes from — per-page by nature
  prompts/*.txt       what the model is told — the product, edited constantly
  .env                secrets and model ids, which get retired upstream
  page rows           identity and publishing policy

Both yml files are parsed at import, so a bad value fails the boot rather than
the render. Prompts are read per call, so editing one needs no restart.

The split between the two yml files is the point: `layout.yml` describes the one
Composed Image form and must never grow a per-page section, while `sources.yml`
is per-page because the beats do not overlap — the old system's four brands were
history, general facts, scripture and hot tubs, and hot tub news is noise on a
history grid.

What stays in code rather than moving here: vendor base URLs, query-parameter
sets, the User-Agent, and the fetch limits that bound a window. Changing any of
those means changing the code that parses the response, so exposing them would
offer an edit that cannot safely be made. The test is whether an operator could
change the value without touching code.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent
LAYOUT_PATH = API_DIR / "config" / "layout.yml"
SOURCES_PATH = API_DIR / "config" / "sources.yml"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ImageLayout(Frozen):
    width: int
    height: int
    edge_margin_ratio: float


class PanelLayout(Frozen):
    ratio: float
    """Minimum share of image height. The panel grows to fit, up to max_ratio."""
    max_ratio: float
    color: str
    opacity: float


class PaddingLayout(Frozen):
    left_px: int
    right_px: int
    top_px: int
    bottom_px: int


class TextLayout(Frozen):
    font_size_px: int
    line_height_ratio: float
    align: str
    color: str
    padding: PaddingLayout


class HighlightLayout(Frozen):
    color: str


class WatermarkLayout(Frozen):
    max_px: int
    top_ratio: float


class PortraitLayout(Frozen):
    size_px: int
    min_px: int
    max_width_ratio: float
    ring_pad_px: int
    border_width_px: int
    border_color: str

    def clamp(self, size_px: int | None, image_width: int) -> int:
        """The diameter actually drawn. `None` means the default.

        Both ends matter: below `min_px` the disc is a smudge, and above
        `max_width_ratio` it stops being an inset and starts being the picture.
        Applied on write *and* on draw, because a row can predate a change to
        either bound.
        """
        return round(
            min(
                image_width * self.max_width_ratio,
                max(self.min_px, self.size_px if size_px is None else size_px),
            )
        )

    def ring_size(self, size_px: int | None, image_width: int) -> int:
        """The drawn size: disc plus the padding the stroke needs on each side."""
        return self.clamp(size_px, image_width) + self.ring_pad_px * 2


class FontLayout(Frozen):
    family: str
    weight: str
    """`family` must match the TTF's name table, not the file name. resvg
    substitutes a serif face silently when it does not — "Arial Bold" renders,
    it just does not render Arial. The file is family "Arial", subfamily "Bold",
    so it is selected as family + weight."""

    path: str


class Layout(Frozen):
    image: ImageLayout
    panel: PanelLayout
    text: TextLayout
    highlight: HighlightLayout
    watermark: WatermarkLayout
    portrait: PortraitLayout
    font: FontLayout

    @property
    def font_file(self) -> Path:
        return API_DIR / self.font.path


@lru_cache(maxsize=1)
def get_layout() -> Layout:
    with LAYOUT_PATH.open(encoding="utf-8") as handle:
        return Layout.model_validate(yaml.safe_load(handle))


class Feed(Frozen):
    name: str
    """The byline. Curated, not the feed's own <title>, which is written for
    feed readers and reads badly on a card."""

    url: str


class RssConfig(Frozen):
    since_days: int
    max_items: int


class CompetitorsConfig(Frozen):
    lookback_days: int
    grid_limit: int


class Sources(Frozen):
    """Where Source Items come from. Per-page, unlike `Layout`.

    Kept apart from layout.yml because that file describes the one Composed
    Image form and must never grow a per-page section, whereas this one is
    per-page by nature — the beats do not overlap.
    """

    rss: RssConfig
    competitors: CompetitorsConfig
    feeds: dict[str, list[Feed]]
    """Keyed by `page.name`."""

    def feeds_for(self, page_name: str) -> list[Feed]:
        """Raises:
        KeyError: the Page has no entry. Loud on purpose — an empty grid is
            indistinguishable from a quiet week, and that is how the old system
            lost its watermark for months without one failed post.
        """
        try:
            return self.feeds[page_name]
        except KeyError:
            raise KeyError(
                f"No feeds configured for {page_name!r} in config/sources.yml. "
                f"Configured: {sorted(self.feeds)}"
            ) from None

    @property
    def curated_hosts(self) -> set[str]:
        """Every host any Page draws from.

        The union rather than one Page's, because `POST /sources` has no Page —
        an RSS item is not tied to one (only a competitor post is). The guard it
        backs asks "is this one of ours", which is what it needs to ask.
        """
        return {
            urlsplit(feed.url).hostname or ""
            for feeds in self.feeds.values()
            for feed in feeds
        }


@lru_cache(maxsize=1)
def get_sources() -> Sources:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return Sources.model_validate(yaml.safe_load(handle))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(API_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_path: str = str(API_DIR / "fb_agent.db")
    sql_echo: bool = False
    timezone: str = "Asia/Ho_Chi_Minh"

    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-3.5-flash"
    """Verified against the key before being set, which is the only way to know.

    `gemini-2.5-flash` was the default here for exactly one session and answered
    404 *"no longer available to new users"* — the third pinned id to rot in this
    repo, after `gemini-2.0-flash` and a retired image model. It was still listed
    by `models.list()` while 404ing on use, so the catalogue is not evidence; a
    real call is.

    This is a pinned version and will rot the same way eventually. When it does,
    `gemini-flash-latest` is the alias to fall back to — Google repoints it, so
    it cannot expire on somebody else's schedule.
    """
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_image_fallback_models: str = ""
    """Comma-separated, tried in order after the configured model. Empty disables.

    Env rather than code because these **will** rot, and unlike the text chain
    there is no alias to hide behind. The writer can end on `gemini-flash-latest`,
    which Google repoints; there is no `-latest` for an image model, so every
    link here is a pinned version that expires on somebody else's schedule. The
    old repo already shipped `fix(gemini): replace retired image fallback model`
    once — see design.md on why model ids are deployment config.

    `gemini-2.5-flash-image` is the default because it is the model the old system
    actually shipped heroes on (decisions.md), so its output is known to be
    acceptable for this brand rather than merely available.
    """

    metricool_api_token: str = ""
    metricool_user_id: str = ""

    metricool_publish_as_draft: bool = True
    """Push to Metricool's planner as a draft rather than a queued post.

    On by default, and it should stay on until a real push has been watched
    through end to end. The difference between the two values is the difference
    between a row in a planner and a post on a page with an audience — there is
    no dry run for the second one, and no undo that happens before people see it.
    """

    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "fb-agent-media"
    """Where a composite goes so that Metricool can fetch it.

    **Not a MediaStore.** Heroes, insets and working composites stay on local
    disk; exactly one JPEG per publish is uploaded here, because that is the only
    file anything outside this machine ever needs to read. Measured before
    choosing: a composite is 1.21MB as PNG and 0.27MB as JPEG, so publishing
    twice a day costs ~16MB a month against a 1GB free tier.

    The bucket must be **public**. A signed URL would expire, and Metricool does
    not take its own copy — verified against the live API, which echoed both a
    JPEG and a PNG back unchanged rather than re-hosting them, contradicting
    their own documentation. Facebook fetches the URL when the post goes out, so
    it has to still resolve then.
    """

    x_bearer_token: str = ""

    @property
    def image_fallback_chain(self) -> tuple[str, ...]:
        """The configured model first, then the fallbacks. Never empty."""
        rest = (
            name.strip()
            for name in self.gemini_image_fallback_models.split(",")
            if name.strip() and name.strip() != self.gemini_image_model
        )
        return (self.gemini_image_model, *rest)

    def missing_secrets(self) -> list[str]:
        """Named, never valued. Reported by /health so a blank .env is obvious."""
        required = {
            "GEMINI_API_KEY": self.gemini_api_key,
            "METRICOOL_API_TOKEN": self.metricool_api_token,
            "METRICOOL_USER_ID": self.metricool_user_id,
            "X_BEARER_TOKEN": self.x_bearer_token,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_KEY": self.supabase_service_key,
        }
        return sorted(name for name, value in required.items() if not value)


settings = Settings()
layout = get_layout()
sources = get_sources()
