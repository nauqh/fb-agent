"""Four tiers of configuration, deliberately kept apart.

  config/layout.yml  how the image looks — frozen, identical for every Page
  prompts/*.txt      what the model is told — the product, edited constantly
  .env               secrets and model ids, which get retired upstream
  page rows          identity and publishing policy

Layout is parsed at import, so a bad value fails the boot rather than the
render. Prompts are read per call, so editing one needs no restart.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent
LAYOUT_PATH = API_DIR / "config" / "layout.yml"


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
    font: FontLayout

    @property
    def font_file(self) -> Path:
        return API_DIR / self.font.path


@lru_cache(maxsize=1)
def get_layout() -> Layout:
    with LAYOUT_PATH.open(encoding="utf-8") as handle:
        return Layout.model_validate(yaml.safe_load(handle))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(API_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_path: str = str(API_DIR / "fb_agent.db")
    media_root: str = str(API_DIR / "media")
    sql_echo: bool = False
    timezone: str = "Asia/Ho_Chi_Minh"

    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-3.5-flash"
    gemini_image_model: str = "gemini-2.5-flash-image"

    metricool_api_token: str = ""
    metricool_user_id: str = ""

    x_bearer_token: str = ""

    def missing_secrets(self) -> list[str]:
        """Named, never valued. Reported by /health so a blank .env is obvious."""
        required = {
            "GEMINI_API_KEY": self.gemini_api_key,
            "METRICOOL_API_TOKEN": self.metricool_api_token,
            "METRICOOL_USER_ID": self.metricool_user_id,
            "X_BEARER_TOKEN": self.x_bearer_token,
        }
        return sorted(name for name, value in required.items() if not value)


settings = Settings()
layout = get_layout()
