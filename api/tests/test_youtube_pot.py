"""The PO token provider sits beside the cookies, not instead of them.

The mweb / android / ios clients of the rotation skip every GVS format
without a PO token now (pinned in yt-dlp's per-client policy tables), so the
fallbacks behind `default,web_embedded` were armed but hollow. The
bgutil-ytdlp-pot-provider plugin fills them from an HTTP token server; the
only thing this codebase owns is where that server answers, which is the
`youtubepot-bgutilhttp:base_url` extractor arg the plugin reads.

Everything else is the plugin's job: registration with yt-dlp's provider
framework, the unreachable-server warning, the proxy forwarding that keeps
the token's IP bound to the same egress the download uses.
"""

from __future__ import annotations

from app.settings import settings
from app.youtube import sources


def test_pot_server_url_reaches_the_extractor_args(monkeypatch):
    monkeypatch.setattr(
        settings, "ytdlp_pot_server_url", "http://pot:4416"
    )
    options = sources._base_options(
        "mweb", use_cookies=True, channel_tab=False
    )
    assert options["extractor_args"]["youtubepot-bgutilhttp"] == {
        "base_url": ["http://pot:4416"]
    }


def test_unset_pot_server_stays_out_of_the_args(monkeypatch):
    """Unset means today's behavior exactly — no arg, no warnings changed."""
    monkeypatch.setattr(settings, "ytdlp_pot_server_url", "")
    options = sources._base_options(
        "mweb", use_cookies=True, channel_tab=False
    )
    assert "youtubepot-bgutilhttp" not in options["extractor_args"]


def test_pot_and_cookies_are_layers_not_alternatives(monkeypatch, tmp_path):
    """The build this sits on top of: cookies still ride along with the
    token arg present. The token attests the client; the cookies are the
    session. Neither replaces the other."""
    export = tmp_path / "cookies.txt"
    export.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setattr(settings, "ytdlp_cookies_file", str(export))
    monkeypatch.setattr(settings, "ytdlp_pot_server_url", "http://pot:4416")

    options = sources._base_options(
        "default,web_embedded", use_cookies=True, channel_tab=False
    )
    assert options["cookiefile"] == str(export)
    assert options["extractor_args"]["youtubepot-bgutilhttp"] == {
        "base_url": ["http://pot:4416"]
    }


def test_the_plugin_shipped_into_the_environment():
    """`uv sync --frozen` in the container installs from the lock; if the
    plugin ever drops out of it, downloads still "work" — tokenless, warning
    once, hollow fallbacks — and nothing in the API surface would say so.
    Import it and check it registered with yt-dlp's provider framework."""
    import yt_dlp_plugins.extractor.getpot_bgutil_http as plugin  # noqa: F401
    from yt_dlp.extractor.youtube.pot._registry import _pot_providers

    # _pot_providers is a globals.Indirect wrapping the class-name -> class dict
    assert "BgUtilHTTP" in _pot_providers.value
