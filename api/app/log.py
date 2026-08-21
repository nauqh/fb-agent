"""The app's own logging. Minimal on purpose.

One logger, one sink, one format going to stderr (Railway captures it). No JSON,
no files, no per-module loggers. uvicorn keeps its own default lines; this only
covers what the app itself says — an outcome and, usually, how long it took.
That follows https://loggingsucks.com : log the thing that changed, once, at
the end, not every step towards it.
"""

import sys

from loguru import logger

from app.settings import settings


def setup_logging() -> None:
    """Install the one sink. Idempotent for a reloading uvicorn."""
    logger.remove()
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
    logger.info("logging ready (level={})", settings.log_level)

    _uvicorn_level()


def _uvicorn_level() -> None:
    """Raise uvicorn's verbosity to match ours.

    uvicorn prints an access line per request at INFO by default, which is
    exactly the noise DEBUG turns on — but it has no idea it is part of this
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
