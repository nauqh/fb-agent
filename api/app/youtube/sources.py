"""Everything this tool does with a YouTube URL, in one place.

Parse it, list a channel's Shorts, rank them, download one. The old tool
spread these across `youtubeUrl.ts`, `youtubeChannelShortsApiService.ts`,
`ytdlpService.ts` and `youtubeDownloadService.ts`; they are one job — "turn a
pasted URL into the bytes of the right video" — and they share the same enemy
(YouTube's bot-check) and the same settings (cookies, proxy, API key).

The download half is yt-dlp as a library, not a CLI: the old tool shelled out
with hand-built argument strings (`ytdlpService.ts`); `YoutubeDL` takes a
params dict, so there is no exec, no escaping, and exceptions carry the message.

The strategy that costs real time to rediscover is ported wholesale:

- **Player-client rotation.** YouTube answers 429 / "Sign in to confirm" to a
  datacenter IP; the old tool retried the same download with the player client
  `tv_embedded,mweb` → `android,web` → `ios,mweb` until one passed. Each is a
  different player surface with a different bot-check posture.
- **Cookies.** A browser export on disk (`YTDLP_COOKIES_FILE`) is the only
  thing that survives the check reliably. The worker never writes this file,
  which is the old tool's work-copy discipline made moot.
- **A proxy knob.** Residential egress costs money; `YTDLP_PROXY_URL` stays an
  opt-in env var, exactly as the old VPS ran it.
- **The picker's two backends.** With `YOUTUBE_API_KEY` set, the channel list
  comes from the official Data API (handles, ≤180s filter, thumbnails);
  without it, from a yt-dlp flat playlist (no key, no thumbnails). The 180s
  filter is the definition of a Short: `contentDetails.duration` ≤ 3 minutes.

There is no Cobalt. The old production logs show Cobalt always answered
`error.api.youtube.login` from a datacenter IP and yt-dlp was the real path —
a second service that never won is not worth a dependency (docs/youtube-python-rebuild.md).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.settings import settings

# --- URL parsing -----------------------------------------------------------

VIDEO_ID = r"[\w-]{11}"

URL_PATTERNS = {
    "watch": re.compile(
        rf"^https?://(?:www\.)?youtube\.com/watch\?v={VIDEO_ID}(?:&[^\s]*)?$",
        re.I,
    ),
    "youtu_be": re.compile(
        rf"^https?://(?:www\.)?youtu\.be/{VIDEO_ID}(?:\?[^\s]*)?$", re.I
    ),
    "shorts": re.compile(
        rf"^https?://(?:www\.|m\.)?youtube\.com/shorts/{VIDEO_ID}(?:\?[^\s]*)?$",
        re.I,
    ),
    "embed": re.compile(
        rf"^https?://(?:www\.)?youtube\.com/embed/{VIDEO_ID}(?:\?[^\s]*)?$", re.I
    ),
    "channel_shorts": re.compile(
        r"^https?://(?:www\.|m\.)?youtube\.com/@[^/?#]+(?:/shorts)?(?:\?[^\s]*)?$",
        re.I,
    ),
}

MAX_SHORTS_LIMIT = 10
"""How many top Shorts a channel paste can enqueue at once. A clamp, and the
upper bound the picker renders — the old tool's identical constant."""

MAX_TRIM_SECONDS = 60
DEFAULT_TRIM_SECONDS = 3

SUPPORTED_URL_EXAMPLES = [
    "https://www.youtube.com/shorts/EM41yq0OUQ4",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/@handle/shorts",
]


@dataclass(frozen=True)
class YoutubeSource:
    """A parsed URL. `video` is one file; `channel_shorts` is a ranking."""

    type: str  # "video" | "channel_shorts"
    url: str
    shorts_index: int = 1


def normalize_channel_shorts_url(url: str) -> str:
    trimmed = url.strip().rstrip("/")
    return trimmed if trimmed.endswith("/shorts") else f"{trimmed}/shorts"


def parse_youtube_source(url: str, shorts_index: int = 1) -> YoutubeSource | None:
    trimmed = url.strip()
    if _is_single_video_url(trimmed):
        return YoutubeSource("video", trimmed)
    if URL_PATTERNS["channel_shorts"].match(trimmed):
        return YoutubeSource(
            "channel_shorts", normalize_channel_shorts_url(trimmed), shorts_index
        )
    return None


def _is_single_video_url(url: str) -> bool:
    return any(
        pattern.match(url)
        for name, pattern in URL_PATTERNS.items()
        if name != "channel_shorts"
    )


def is_short_url(url: str) -> bool:
    """Is this a Short-shaped URL, for scheduling defaults? The old tool kept
    the same helper (`youtubeShortsMetadata.ts`) beside the parser so a Short
    defaulted to `#Shorts` in the description."""
    trimmed = url.strip()
    return "/shorts/" in trimmed or bool(
        re.search(r"youtube\.com/@[^/?#]+(?:/shorts)?(?:\?|$)", trimmed, re.I)
    )


def clamp_trim_duration(value: object) -> int:
    parsed = _as_int(value)
    if parsed is None or parsed < 1:
        return DEFAULT_TRIM_SECONDS
    return min(parsed, MAX_TRIM_SECONDS)


def clamp_shorts_limit(value: object) -> int:
    parsed = _as_int(value)
    if parsed is None or parsed < 1:
        return 1
    return min(parsed, MAX_SHORTS_LIMIT)


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# --- channel Shorts ranking ------------------------------------------------

class DiscoveryError(RuntimeError):
    """The channel could not be listed. Raised with the reason the operator
    should see, never a bare HTTP status."""


@dataclass(frozen=True)
class ChannelShort:
    id: str
    url: str
    title: str | None
    view_count: int
    like_count: int | None
    duration: int | None
    thumbnail_url: str | None
    rank: int


SHORT_DURATION_SECONDS = 180
SEARCH_PAGE_SIZE = 50
RANKED_CACHE_TTL_MS = 5 * 60 * 1000
GOOGLE_BASE = "https://www.googleapis.com/youtube/v3"

_ranked_cache: dict[str, tuple[float, list[ChannelShort]]] = {}


def list_channel_shorts(channel_url: str) -> list[ChannelShort]:
    """The channel's Shorts, ranked by view count. API when the key is set,
    yt-dlp flat listing otherwise (only that one has no quota)."""
    if settings.youtube_api_key.strip():
        return _via_api(channel_url)
    return _via_ytdlp(channel_url)


def resolve_by_rank(channel_url: str, rank: int) -> ChannelShort:
    """`@channel/shorts` rank #N → one concrete Short.

    The worker's channel path resolves here before downloading — a channel URL
    is a ranking, not a file (see `parse_youtube_source`).
    """
    ranked = list_channel_shorts(channel_url)
    index = rank - 1
    if index < 0 or index >= len(ranked):
        raise DiscoveryError(
            f"Short #{rank} is out of range — the channel listed {len(ranked)} Shorts."
        )
    return ranked[index]


def _handle_of(channel_url: str) -> str | None:
    match = re.search(r"youtube\.com/@([^/?#]+)", channel_url, re.I)
    return match.group(1) if match else None


def _via_api(channel_url: str) -> list[ChannelShort]:
    handle = _handle_of(channel_url)
    if not handle:
        raise DiscoveryError("Could not read the @handle from the channel URL.")

    key = settings.youtube_api_key.strip()
    channel_id = _channel_id(handle, key)
    candidates = _search_shorts(channel_id, key)
    if not candidates:
        return []
    details = _video_details(candidates, key)

    ranked: list[ChannelShort] = []
    for video_id in candidates:
        meta = details.get(video_id)
        if not meta or meta["duration"] > SHORT_DURATION_SECONDS:
            continue
        ranked.append(
            ChannelShort(
                id=video_id,
                url=f"https://www.youtube.com/shorts/{video_id}",
                title=meta["title"],
                view_count=meta["views"],
                like_count=None,
                duration=meta["duration"],
                thumbnail_url=meta["thumbnail"],
                rank=0,
            )
        )
    ranked.sort(key=lambda item: item.view_count, reverse=True)
    _assign_ranks(ranked)
    return ranked


def _via_ytdlp(channel_url: str) -> list[ChannelShort]:
    cache_key = channel_url
    cached = _ranked_cache.get(cache_key)
    if cached and cached[0] > time.time() * 1000:
        return cached[1]

    entries = flat_playlist_entries(channel_url)
    items: list[ChannelShort] = []
    for entry in entries:
        video_id = str(entry.get("id") or "")
        items.append(
            ChannelShort(
                id=video_id,
                url=str(entry.get("url") or f"https://www.youtube.com/shorts/{video_id}"),
                title=str(entry.get("title") or "") or None,
                view_count=int(entry.get("view_count") or 0),
                like_count=None,
                duration=None,
                thumbnail_url=None,
                rank=0,
            )
        )
    items.sort(key=lambda item: item.view_count, reverse=True)
    _assign_ranks(items)
    _ranked_cache[cache_key] = (time.time() * 1000 + RANKED_CACHE_TTL_MS, items)
    return items


def _assign_ranks(items: list[ChannelShort]) -> None:
    for index, item in enumerate(items):
        object.__setattr__(item, "rank", index + 1)


def _channel_id(handle: str, key: str) -> str:
    data = _api_get(
        "channels",
        {"part": "id", "forHandle": handle},
        key,
        "resolve the channel",
    )
    channel_id = (data.get("items") or [{}])[0].get("id")
    if not channel_id:
        raise DiscoveryError(f"No channel found for @{handle}.")
    return str(channel_id)


def _search_shorts(channel_id: str, key: str) -> list[str]:
    data = _api_get(
        "search",
        {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": str(SEARCH_PAGE_SIZE),
        },
        key,
        "list the channel's videos",
    )
    return [
        str(item["id"]["videoId"])
        for item in (data.get("items") or [])
        if (item.get("id") or {}).get("videoId")
    ]


def _video_details(video_ids: list[str], key: str) -> dict[str, dict]:
    data = _api_get(
        "videos",
        {"part": "snippet,contentDetails,statistics", "id": ",".join(video_ids)},
        key,
        "read video details",
    )
    out: dict[str, dict] = {}
    for item in data.get("items") or []:
        video_id = str(item.get("id") or "")
        if not video_id:
            continue
        snippet = item.get("snippet") or {}
        thumbs = snippet.get("thumbnails") or {}
        out[video_id] = {
            "title": str(snippet.get("title") or "") or None,
            "views": int((item.get("statistics") or {}).get("viewCount") or 0),
            "duration": _parse_iso_duration(
                str((item.get("contentDetails") or {}).get("duration") or "")
            ),
            "thumbnail": str(
                (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url") or ""
            ) or None,
        }
    return out


def _api_get(path: str, params: dict[str, str], key: str, what: str) -> dict:
    url = f"{GOOGLE_BASE}/{path}"
    url += "?" + "&".join(f"{k}={v}" for k, v in ({**params, "key": key}).items())
    try:
        response = httpx.get(url, timeout=30)
    except httpx.HTTPError as error:
        raise DiscoveryError(f"YouTube did not answer ({what}): {type(error).__name__}") from error
    if response.is_error:
        detail = (
            (response.json() or {}).get("error", {}).get("message")
            if response.headers.get("content-type", "").startswith("application/json")
            else ""
        )
        raise DiscoveryError(
            f"YouTube refused to {what} ({response.status_code}): {str(detail)[:200]}"
        )
    return response.json()


def _parse_iso_duration(iso: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


# --- download --------------------------------------------------------------

class YoutubeDlError(RuntimeError):
    """A download that failed, with a message an operator can act on."""


FORMAT = (
    "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo+bestaudio/best"
)

PLAYER_CLIENTS = (
    "tv_embedded,mweb",
    "android,web",
    "ios,mweb",
)

_BOT_SIGNALS = (
    "429",
    "too many requests",
    "sign in to confirm",
    "not a bot",
    "requested format is not available",
)
"""Messages that mean "the client was blocked" — worth trying another player
surface for. Anything else is a real failure and retrying a different client
would only bury the actual message.

`requested format is not available` is **not** in the old tool's rotation list
(`ytdlp-errors.ts` excludes it from cookie errors, `isBotOrRateLimit` lacks
it — the old tool failed fast). Kept here as an owned change: a blocked client
can surface as a missing format rather than an explicit refusal, and a rotation
costs a couple of seconds against the hours a fail-fast can cost on a VPS."""

_COOKIE_SIGNALS = (
    "login required",
    "invalid or expired cookies",
    "cookies are required",
    "please sign in to view",
    "cookies are no longer valid",
    "cookies have been rotated",
    "cookies file missing",
    "does not look like a netscape format cookies file",
)
"""Retry-once hints for a stale browser export — the old tool's
`isCookieError` list, ported with the additions. The retry drops the cookie
file when a proxy is set, or fails loud with the re-export message when it is
not (see `_run`).

`this video is unavailable` is deliberately **not** here: a genuinely gone
video is a terminal failure, never a cookie problem, and misreading it as one
would burn the retry budget and the operator's time chasing a fresh export for
a video that will not come back."""


def download_video(url: str, output_path: str) -> str | None:
    """Download one video to `output_path`. Returns its title, if yt-dlp gave one.

    `output_path` is final — yt-dlp merges to it when it must split the
    bestvideo+bestaudio pair. The caller owns cleanup.
    """
    info = _run(url, output_path=output_path)
    return (info.get("title") or "").strip() or None


def flat_playlist_entries(url: str) -> list[dict]:
    """The channel tab as `--flat-playlist` JSON rows — id, title, view count.

    Used for ranking a channel's Shorts when no `YOUTUBE_API_KEY` is
    configured; `_via_ytdlp` is the caller."""
    info = _run(url, channel_tab=True, download=False)
    entries: list[dict] = []
    for entry in (info.get("entries") or []):
        if isinstance(entry, dict) and entry.get("id"):
            entries.append(entry)
    return entries


def _base_options(player_client: str, *, use_cookies: bool, channel_tab: bool) -> dict:
    extractor_args: dict[str, dict] = {
        "youtube": {"player_client": [player_client]},
    }
    if channel_tab:
        # Channel tabs hit YouTube's auth wall even when the videos themselves
        # are public — that wall is what the old tool's
        # `youtubetab:skip=authcheck` existed for.
        extractor_args["youtubetab"] = {"skip": ["authcheck"]}

    options: dict = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "extractor_args": extractor_args,
        # The JS-challenge solver, pinned by the old tool's global args
        # (`--js-runtimes node --remote-components ejs:github`) and kept
        # verbatim: `node` as the JS engine and the EJS solver fetched from
        # GitHub. Without both, a bot-challenged video fails where the old
        # tool got through — same values, same `{}` shape the API wants.
        "js_runtimes": {"node": {}},
        "remote_components": {"ejs:github": {}},
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "sleep_interval": 2,
        "max_sleep_interval": 8,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": {"default": "%(id)s.%(ext)s"},
    }

    cookies = settings.ytdlp_cookies_file.strip()
    if use_cookies and cookies and Path(cookies).exists():
        options["cookiefile"] = cookies
    elif not use_cookies:
        options["cookiefile"] = None

    proxy = settings.ytdlp_proxy_url.strip()
    if proxy:
        options["proxy"] = proxy

    return options


def _run(
    url: str,
    *,
    output_path: str | None = None,
    channel_tab: bool = False,
    download: bool = True,
) -> dict:
    """Run a download (or a listing) with the player-client rotation.

    The rotation is the port of the old outer loop: each client is tried in
    order, and only a `_BOT_SIGNALS` miss moves to the next one. A cookie
    failure gets one retry without the file before the rotation even starts,
    because a stale export fails identically under every client.
    """
    last_error: Exception | None = None

    for attempt in (0, 1):
        use_cookies = attempt == 0
        for player_client in PLAYER_CLIENTS:
            try:
                with YoutubeDL(
                    {
                        **_base_options(player_client, use_cookies=use_cookies, channel_tab=channel_tab),
                        **({"outtmpl": {"default": output_path}} if output_path else {}),
                    }
                ) as ydl:
                    info = ydl.extract_info(url, download=download)
                return info or {}
            except DownloadError as error:
                message = str(error)
                last_error = error

                if use_cookies and _has_signal(message, _COOKIE_SIGNALS):
                    # One pass without the file — but only when that pass has a
                    # proxy to hide behind, which is how `withCookieErrorFallback`
                    # gated it. Retrying anonymously from a datacenter IP is
                    # guaranteed to bot-block again *and* teaches the checker the
                    # IP is worth blocking, so without a proxy a cookie failure
                    # is a terminal error with a message telling the operator the
                    # export is dead: the old tool's exact refusal.
                    if not settings.ytdlp_proxy_url.strip():
                        raise YoutubeDlError(
                            "YouTube refused the download (cookies expired or "
                            "stale), and no download proxy is configured. "
                            "Re-export the cookies file (YTDLP_COOKIES_FILE), "
                            "or set YTDLP_PROXY_URL before retrying without "
                            "cookies."
                        )
                    break
                if not _has_signal(message, _BOT_SIGNALS):
                    raise YoutubeDlError(_friendly(message)) from error

                # A 429 / bot-check is a rate limit, not a dead end — but it
                # has to be treated like one. The old tool slept 2s between
                # player clients (`ytdlpService.ts`), and it ran each attempt
                # as a fresh CLI spawn; this one is in-process, so hammering
                # the next client instantly is *more* aggressive than the old
                # tool was, and a rate limit answered by four quick attempts is
                # how downloads get the whole IP blocked. Same breather, kept.
                logger.warning(
                    "[yt-dlp] {} failed with client {}, trying next in 2s",
                    url,
                    player_client,
                )
                time.sleep(2)

    raise YoutubeDlError(_friendly(str(last_error))) from last_error


def _has_signal(message: str, signals: tuple[str, ...]) -> bool:
    lowered = message.lower()
    return any(signal in lowered for signal in signals)


def _friendly(message: str) -> str:
    """An operator-facing line instead of a yt-dlp stack fragment.

    The old tool had a whole error-mapping module (`ytdlp-errors.ts`) for this;
    the three cases that ever mattered were the expired session, the refused
    proxy, and everything else. `_BOT_SIGNALS` are handled by rotation, so
    what stays here are the cookie hint and the proxy hint.
    """
    lowered = message.lower()
    if any(s in lowered for s in _COOKIE_SIGNALS) or "sign in" in lowered:
        return (
            "YouTube refused the download (session expired or bot check). "
            "Re-export the cookies file (YTDLP_COOKIES_FILE) and retry."
        )
    if "proxy" in lowered:
        return (
            "The download proxy refused the connection. Check YTDLP_PROXY_URL "
            "and that the proxy is running."
        )
    return message[:500]