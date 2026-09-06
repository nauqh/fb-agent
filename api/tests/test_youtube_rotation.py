"""The player-client rotation, and which failures are allowed to reach it.

`_run` owns a three-client rotation whose entire purpose is surviving a
per-client refusal, and nothing pinned it. That gap shipped a bug: "The page
needs to be reloaded" was in neither signal list, so the first client raised
and the other two were never tried — a rotation that existed and did not run.

These tests are about the classification, not about yt-dlp. A message that
means "this client was refused" must rotate; a message that means "this video
is gone" must not, because burning six attempts on a dead video costs an
operator time and teaches YouTube the IP is worth watching.
"""

from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError

from app.youtube import sources


class _AlwaysFails:
    """A YoutubeDL that refuses with `message`, counting its constructions."""

    def __init__(self, message: str, attempts: list[dict]):
        self.message = message
        self.attempts = attempts

    def __call__(self, options: dict):
        self.attempts.append(options)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, *_args, **_kwargs):
        raise DownloadError(self.message)


@pytest.fixture
def no_sleep(monkeypatch):
    """The rotation sleeps 2s between clients. Not in a test suite it doesn't."""
    monkeypatch.setattr(sources.time, "sleep", lambda _seconds: None)


def _run_and_count(monkeypatch, message: str) -> list[dict]:
    attempts: list[dict] = []
    monkeypatch.setattr(sources, "YoutubeDL", _AlwaysFails(message, attempts))
    with pytest.raises(sources.YoutubeDlError):
        sources._run("https://www.youtube.com/shorts/tgmEHQv7ozQ")
    return attempts


def test_page_needs_reloading_rotates_every_client(monkeypatch, no_sleep):
    """The regression. Production raised on client one and stopped.

    YouTube forces SABR on the web surfaces and the extractor answers with
    this, but only when cookies are sent — so it appeared the day cookies
    started working, on `tv_embedded,mweb`, with `android,web` and `ios,mweb`
    never attempted.
    """
    attempts = _run_and_count(monkeypatch, "ERROR: [youtube] x: The page needs to be reloaded.")

    clients = [
        options["extractor_args"]["youtube"]["player_client"][0] for options in attempts
    ]
    assert clients[: len(sources.PLAYER_CLIENTS)] == list(sources.PLAYER_CLIENTS)


def test_a_dead_video_fails_on_the_first_client(monkeypatch, no_sleep):
    """The other half of the rule. A gone video is terminal, and rotating on it
    would spend six attempts to reach the same answer."""
    attempts = _run_and_count(monkeypatch, "ERROR: [youtube] x: This video is unavailable")

    assert len(attempts) == 1


def test_bot_signals_reach_the_rotation(monkeypatch, no_sleep):
    """Every signal in the list must actually rotate — the list is only useful
    if `_run` consults it, and this is the assertion that ties the two."""
    for signal in sources._BOT_SIGNALS:
        attempts = _run_and_count(monkeypatch, f"ERROR: [youtube] x: {signal}")
        assert len(attempts) > 1, f"{signal!r} did not rotate"
