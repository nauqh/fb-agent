"""The app's own logging. Minimal on purpose.

One logger, one sink going to stderr (Railway captures it). No files, no
per-module loggers. uvicorn keeps its own default lines; this only covers what
the app itself says - an outcome and, usually, how long it took. That follows
https://loggingsucks.com : log the thing that changed, once, at the end, not
every step towards it.

**JSON, always, one line each.** Railway's shape: a single-line object with
`message` and `level` at the top and everything bound with `logger.bind(...)`
beside them, which Railway turns into attributes you can filter on
(`@draft_id:500`). There was a `LOG_FORMAT` toggle with text as the default; it
meant production printed text until someone remembered to set and deploy a
variable, which is how the first JSON deploy went. Removed at the operator's
request (2026-09-16), so local output is JSON too. The same article argues
for the fields themselves: one wide event per unit of work, carrying the
high-cardinality things you would want to filter by - which for this app is a
draft, not an HTTP request (see `generate._run_one`).
"""

import inspect
import json
import logging
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


class _Intercept(logging.Handler):
    """stdlib `logging` into loguru, so it gets the same sink and format.

    uvicorn reports an unhandled exception through stdlib ("Exception in ASGI
    application" and a traceback). Left on its own handler that is plain text,
    which Railway splits into one entry per traceback line with no level. The
    body is loguru's documented recipe: the frame walk puts the caller's module
    in `name` rather than `logging/__init__`.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    """Install the one sink. Idempotent for a reloading uvicorn."""
    logger.remove()
    logger.add(_json_sink, level=settings.log_level, backtrace=True, diagnose=False)
    logger.info("Logging ready (level={})", settings.log_level)

    _uvicorn_level()


def _uvicorn_level() -> None:
    """Raise uvicorn's verbosity to match ours, and send it through loguru.

    uvicorn prints an access line per request at INFO by default, which is
    exactly the noise DEBUG turns on - but it has no idea it is part of this
    app's log. Gate the two loggers it owns (startup/error, access) on
    `LOG_LEVEL` so DEBUG shows every request and INFO keeps a quiet stream of
    app outcomes only.
    """
    # uvicorn logs its access lines at INFO. Show them only when DEBUG is on;
    # otherwise raise uvicorn's loggers to WARNING so the stream stays app
    # outcomes, not one line per request. `LOG_LEVEL` sets *loguru*; this maps
    # it to the uvicorn loggers it owns.
    uvicorn_level = "INFO" if settings.log_level == "DEBUG" else "WARNING"
    # Root at WARNING, so libraries' warnings arrive too without httpx's INFO
    # line for every Gemini and Metricool call. uvicorn's own handlers are
    # dropped for propagation to the root's, or each line would print twice.
    logging.basicConfig(handlers=[_Intercept()], level=logging.WARNING, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        stdlib = logging.getLogger(name)
        stdlib.setLevel(uvicorn_level)
        stdlib.handlers = []
        stdlib.propagate = True
