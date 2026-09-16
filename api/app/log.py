"""The app's own logging. Minimal on purpose.

One logger, one sink going to stderr (Railway captures it). No files, no
per-module loggers. uvicorn keeps its own default lines; this only covers what
the app itself says - an outcome and, usually, how long it took. That follows
https://loggingsucks.com : log the thing that changed, once, at the end, not
every step towards it.

**Two formats, one line each.** `LOG_FORMAT=json` emits Railway's shape - a
single-line object with `message` and `level` at the top and everything bound
with `logger.bind(...)` beside them, which Railway turns into attributes you can
filter on (`@draft_id:500`). Text is the default and is what a terminal gets;
JSON there would only make the same line harder to read. The same article argues
for the fields themselves: one wide event per unit of work, carrying the
high-cardinality things you would want to filter by - which for this app is a
draft, not an HTTP request (see `generate._run_one`).
"""

import json
import sys
import traceback

from loguru import logger

from app.settings import settings


def _json_sink(message) -> None:
    """Railway parses this; it must stay on one line to be parsed at all.

    `extra` is whatever `logger.bind()` put there, spread at the top level
    rather than nested, because that is what makes it a filterable attribute.
    """
    record = message.record
    payload = {
        "message": record["message"],
        "level": record["level"].name.lower(),
        "time": record["time"].isoformat(),
        "logger": record["name"],
        **record["extra"],
    }
    if record["exception"] is not None:
        payload["exception"] = "".join(
            traceback.format_exception(*record["exception"])
        )[:4000]
    # `default=str` rather than a converter per field: a value that is not JSON
    # is a log line, and losing the whole line to a TypeError is worse than
    # printing a repr of one field.
    sys.stderr.write(json.dumps(payload, default=str) + "\n")


def setup_logging() -> None:
    """Install the one sink. Idempotent for a reloading uvicorn."""
    logger.remove()
    as_json = settings.log_format.strip().lower() == "json"
    if as_json:
        logger.add(_json_sink, level=settings.log_level, backtrace=True, diagnose=False)
    else:
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan> - "
                "<level>{message}</level>"
            ),
            level=settings.log_level,
            colorize=False,
            backtrace=True,
            diagnose=True,
        )
    logger.info(
        "logging ready (level={}, format={})",
        settings.log_level,
        "json" if as_json else "text",
    )

    _uvicorn_level()


def _uvicorn_level() -> None:
    """Raise uvicorn's verbosity to match ours.

    uvicorn prints an access line per request at INFO by default, which is
    exactly the noise DEBUG turns on - but it has no idea it is part of this
    app's log. Gate the two loggers it owns (startup/error, access) on
    `LOG_LEVEL` so DEBUG shows every request and INFO keeps a quiet stream of
    app outcomes only.
    """
    import logging

    # uvicorn logs its access lines at INFO. Show them only when DEBUG is on;
    # otherwise raise uvicorn's loggers to WARNING so the stream stays app
    # outcomes, not one line per request. `LOG_LEVEL` sets *loguru*; this maps
    # it to the uvicorn loggers it owns.
    uvicorn_level = "INFO" if settings.log_level == "DEBUG" else "WARNING"
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(uvicorn_level)
