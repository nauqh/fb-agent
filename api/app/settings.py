"""Five tiers of configuration, deliberately kept apart.

  config/layout.yml   how the image looks — identical for every Page, never
                      per-page
  config/sources.yml  how wide a window material is drawn from
  prompts/*.txt       what the model is told — the product, edited constantly
  .env                secrets and model ids, which get retired upstream
  page rows           identity and publishing policy
  feed rows           which feeds a Page draws from — the one list an operator
                      edits from a screen rather than from a diff

Both yml files are parsed at import, so a bad value fails the boot rather than
the render. Prompts are read per call, so editing one needs no restart.

Neither yml file has a per-page section, and for different reasons. `layout.yml`
must never grow one: every Page renders the same Composed Image form.
`sources.yml` lost the one it had — the per-page thing in it was the feed list,
and that is `feed` rows now, because the beats do not overlap (the old system's
four brands were history, general facts, scripture and hot tubs, and hot tub
news is noise on a history grid) *and* because it is the one list that has to
change without a deploy.

What stays in code rather than moving here: vendor base URLs, query-parameter
sets, the User-Agent, and the fetch limits that bound a window. Changing any of
those means changing the code that parses the response, so exposing them would
offer an edit that cannot safely be made. The test is whether an operator could
change the value without touching code.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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


Align = Literal["left", "center", "right"]
"""The three SVG `text-anchor` positions have, and nothing else does.

Typed here rather than on `LayoutPatch`, because this model is the one thing
both a `layout.yml` edit and a PATCH pass through. As a bare `str` the route
stored `text_align: "sideways"` and answered 200: the write is validated by
building the `Layout` it would produce, so anything this model accepts is a
value the compositor is later handed.
"""


class TextLayout(Frozen):
    font_size_px: int
    line_height_ratio: float
    align: Align
    color: str
    padding: PaddingLayout


Template = Literal["card", "full_overlay"]
"""Which of the two card forms a Page draws.

`card` is the original: hero on top, panel below it, the two dividing the height
between them. `full_overlay` is the old app's Template 2 — the photograph fills
the card and the panel is laid over its bottom, which only reads as one picture
if the panel is translucent (`panel.opacity`).

Two, and closed. A third would be a `template` table rather than a value, which
is what the old system had: `facebook_post_templates`, a row per page, every
field doubled with a `_full_overlay` twin.
"""


class BadgeLayout(Frozen):
    """The headline chip, bottom-left of a `full_overlay` card.

    Never drawn on a `card` — the old app made it a Template 2 feature and it is
    one: on a card the panel already starts where the badge would sit.

    Its *label* is not here. Style is layout, and the word is the Page's
    (`page.badge_text`), because "NEWS" on a history page is wrong in a way no
    layout value can be.
    """

    color: str
    text_color: str
    font_size_px: int
    radius_px: int
    padding_x_px: int
    padding_y_px: int
    gap_ratio: float
    """× image height → the gap between the badge and the top of the panel."""


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
    template: Template
    image: ImageLayout
    panel: PanelLayout
    text: TextLayout
    highlight: HighlightLayout
    watermark: WatermarkLayout
    badge: BadgeLayout
    portrait: PortraitLayout
    font: FontLayout

    @property
    def font_file(self) -> Path:
        return API_DIR / self.font.path


@lru_cache(maxsize=1)
def get_layout() -> Layout:
    with LAYOUT_PATH.open(encoding="utf-8") as handle:
        return Layout.model_validate(yaml.safe_load(handle))


class RssConfig(Frozen):
    since_days: int
    max_items: int


class CompetitorsConfig(Frozen):
    lookback_days: int
    grid_limit: int


class Sources(Frozen):
    """The two windows a grid is built inside. Both global, neither per-page.

    `feeds` used to be the third field here, a `dict[str, list[Feed]]` keyed by
    `page.name`, and it is a `feed` table now — see models.py. It moved because
    it is the one part of this file an operator has to be able to change without
    a deploy, and this API runs from a container image: a write to
    `config/sources.yml` lasts until the next deploy and disagrees with the
    committed copy until then.

    The windows stayed. They are not per-page (sources.yml records the
    measurement that settled it) and nothing about them wants a form, so they
    are still config in the sense this module means: an operator could change
    the value without touching code, and it is edited where a diff can be read.
    """

    rss: RssConfig
    competitors: CompetitorsConfig


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

    database_url: str = ""
    """SQLAlchemy URL. Supabase Postgres — there is no local file any more.

    Required, with no default, and that is the point: `database_path` used to
    default to `api/fb_agent.db`, so a misconfigured deploy came up *working*
    against an empty database it had just created, seeded nothing, and showed
    empty screens with no error. A blank value now fails the same way a missing
    API key does, by name, on `/health`.

    Use the **session** pooler, port 5432:

        postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

    Not the transaction pooler on 6543 — it does not support prepared
    statements, which psycopg uses by default, and the failure is intermittent
    rather than immediate. Not the direct `db.<ref>.supabase.co` host either:
    Supabase serves that over IPv6 only on projects of this age, and Railway
    egress is IPv4, so it fails to resolve from where this actually runs.
    """

    sql_echo: bool = False
    timezone: str = "Asia/Ho_Chi_Minh"

    @property
    def database_summary(self) -> str:
        """Host and database name, never the password.

        `/health` reported `database_path` verbatim, which was harmless while it
        was a filename. A URL with credentials in it is not, and the endpoint is
        unauthenticated.
        """
        if not self.database_url:
            return ""
        _, _, tail = self.database_url.rpartition("@")
        return tail or "(malformed)"

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

    api_key: str = ""
    """The shared secret every request must carry in `X-API-Key`. See main.py.

    Blank denies everything except `/health` rather than allowing everything.
    That direction is the entire point: the API sat on a public Railway domain
    with no authentication at all, and a misconfigured deploy that comes up
    *open* looks exactly like a working one until someone finds it.

    Not user login. One operator (ADR-0002), and the browser never holds this —
    `next.config.ts` proxies `/api/*` on the Next server, so the key lives in
    that server's environment and is added on the way through.
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
            "API_KEY": self.api_key,
            "DATABASE_URL": self.database_url,
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
