import logging
import os

import reger
from miniviki.core.errors import MinivikiError

DEFAULT_LOG_LEVEL = logging.INFO
LOG_LEVEL_ENV = "MINIVIKI_LOG_LEVEL"

# Stamped onto the handlers this module installs, so a second call can take its own
# back out without touching anything the host process set up.
HANDLER_MARKER = "_miniviki_owned"

# The ASGI server builds its Config -- and installs its handlers -- before the app
# factory is ever called. These are the loggers it claims with propagate=False.
SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def resolve_level(value: str | None = None) -> int:
    """`MINIVIKI_LOG_LEVEL` as a level int. An unknown name is a boot error, not a shrug."""
    raw = (value if value is not None else os.environ.get(LOG_LEVEL_ENV, "")).strip()
    if not raw:
        return DEFAULT_LOG_LEVEL
    level = logging.getLevelNamesMapping().get(raw.upper())
    if level is None:
        raise MinivikiError(
            f"{LOG_LEVEL_ENV}={raw!r} is not a log level. Try DEBUG, INFO, WARNING, ERROR."
        )
    return level


def adopt_server_loggers() -> None:
    """Take the server's loggers back from it.

    Its handlers are formatted by its own formatter, so leaving them in place makes
    half the output look like a different program. Dropping them and turning
    propagation back on routes everything through the root handler reger installed.
    """
    for name in SERVER_LOGGERS:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = True
        logger.setLevel(logging.NOTSET)


def setup_logging(level: int | None = None) -> None:
    """reger owns the format; everything else is persuaded to use it.

    Safe to call more than once -- reger appends a handler on every call, so last
    time's are removed first. Without that, a second boot in the same process
    prints every line twice.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARKER, False):
            root.removeHandler(handler)
    known = set(root.handlers)
    reger.setup_logging(level=resolve_level() if level is None else level)
    for handler in root.handlers:
        if handler not in known:
            setattr(handler, HANDLER_MARKER, True)
    adopt_server_loggers()
