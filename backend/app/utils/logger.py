"""Central logging configuration for the backend."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%H:%M:%S"

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger exactly once.

    Args:
        level: Logging level name, e.g. ``"DEBUG"`` or ``"INFO"``.
    """
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.addHandler(handler)
    # Quieten noisy third-party loggers.
    for noisy in ("uvicorn.access", "matplotlib", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (``visionshield.<name>``)."""
    return logging.getLogger(f"visionshield.{name}")
