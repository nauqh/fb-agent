"""How yt-dlp gets a cookies file on a host with no persistent disk.

Production ran for weeks downloading anonymously from a datacenter IP while
`YTDLP_COOKIES_FILE` was set, because the name was configured and the file was
never in the image. Every job failed with the generic "session expired" line,
which sends an operator to re-export cookies that were not the problem.

Both halves of that are pinned here: a path that does not exist must not count
as cookies, and a base64 variable must become a file before any job runs.
"""

from __future__ import annotations

import base64

from app.settings import settings
from app.youtube import sources


def test_missing_explicit_file_is_not_cookies(monkeypatch, tmp_path):
    """A configured path that does not exist resolves to no cookies at all.

    The bug: the old code checked `.exists()` inline and silently fell through
    to an anonymous download, so a typo'd or absent path looked identical to
    working cookies from the outside.
    """
    monkeypatch.setattr(settings, "ytdlp_cookies_file", str(tmp_path / "gone.txt"))
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", tmp_path / "none.txt")

    assert sources._cookie_path() == ""


def test_explicit_file_wins_when_it_exists(monkeypatch, tmp_path):
    """A laptop with its own export keeps using it, variable or not."""
    export = tmp_path / "cookies.txt"
    export.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    from_env = tmp_path / "from-env.txt"
    from_env.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    monkeypatch.setattr(settings, "ytdlp_cookies_file", str(export))
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", from_env)

    assert sources._cookie_path() == str(export)


def test_env_var_is_used_when_no_file_is_configured(monkeypatch, tmp_path):
    """The Railway shape: no file on disk, a variable carrying the export."""
    from_env = tmp_path / "from-env.txt"
    from_env.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    monkeypatch.setattr(settings, "ytdlp_cookies_file", "")
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", from_env)

    assert sources._cookie_path() == str(from_env)


def test_install_writes_the_decoded_export(monkeypatch, tmp_path):
    target = tmp_path / "written.txt"
    body = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tX\ty\n"
    monkeypatch.setattr(
        settings,
        "ytdlp_cookies_b64",
        base64.b64encode(body.encode("utf-8")).decode("ascii"),
    )
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", target)

    assert sources.install_cookies_from_env() == str(target)
    assert target.read_text(encoding="utf-8") == body


def test_install_is_a_no_op_without_the_variable(monkeypatch, tmp_path):
    target = tmp_path / "written.txt"
    monkeypatch.setattr(settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", target)

    assert sources.install_cookies_from_env() is None
    assert not target.exists()


def test_bad_base64_does_not_stop_the_boot(monkeypatch, tmp_path):
    """Cookies are one tool's dependency. A mangled paste must not take the
    API — drafts, generate, publish — down with it."""
    target = tmp_path / "written.txt"
    monkeypatch.setattr(settings, "ytdlp_cookies_b64", "not base64 at all!!")
    monkeypatch.setattr(sources, "COOKIES_FROM_ENV", target)

    assert sources.install_cookies_from_env() is None
    assert not target.exists()
