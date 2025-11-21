"""Project-wide logging utilities."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

DEFAULT_LEVEL = logging.INFO
VERBOSITY_TO_LEVEL = {
    -2: logging.ERROR,
    -1: logging.WARNING,
    0: logging.INFO,
    1: logging.DEBUG,
}


def _level_for_counts(verbose: int = 0, quiet: int = 0) -> int:
    delta = max(-2, min(2, verbose - quiet))
    return VERBOSITY_TO_LEVEL.get(delta, logging.DEBUG if delta > 0 else logging.ERROR)


def configure_logging(*, verbose: int = 0, quiet: int = 0, stream: TextIO | None = None) -> None:
    """Configure root logging for CLI usage."""
    level = _level_for_counts(verbose, quiet)
    handler_stream = stream or sys.stderr

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(handler_stream)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


__all__ = ["configure_logging"]
