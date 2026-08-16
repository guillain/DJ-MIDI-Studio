"""Application logging configuration.

Logging is deliberately configured by the executable entry point, not at
module import time. Library modules can safely use ``logging.getLogger`` and
applications/tests choose the destination and verbosity explicitly.
"""

from __future__ import annotations

import logging
import os
import platform
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "djmidi"
DEFAULT_LOG_FILENAME = "djmidi.log"
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3
_LEVEL_NAMES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def default_log_path() -> Path:
    """Return a platform-neutral per-user log location."""
    override = os.environ.get("DJMIDI_LOG_DIR")
    if override:
        return Path(override) / DEFAULT_LOG_FILENAME
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "DJ-MIDI-Studio" / "logs" / DEFAULT_LOG_FILENAME
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Logs" / "DJ-MIDI-Studio" / DEFAULT_LOG_FILENAME
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "djmidi" / "logs" / DEFAULT_LOG_FILENAME


def normalize_level(level: str | int) -> int:
    if isinstance(level, int):
        if level not in {getattr(logging, name) for name in _LEVEL_NAMES}:
            raise ValueError(f"Unsupported logging level: {level!r}")
        return level
    normalized = level.strip().upper()
    if normalized not in _LEVEL_NAMES:
        raise ValueError(f"Unsupported logging level: {level!r}")
    return getattr(logging, normalized)


def configure_logging(
    level: str | int = "INFO",
    log_path: str | Path | None = None,
    *,
    console: bool = False,
) -> Path:
    """Configure the rotating execution log and return its path."""
    explicit_path = log_path is not None
    target = Path(log_path) if explicit_path else default_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if explicit_path:
            raise
        target = Path(tempfile.gettempdir()) / "djmidi" / DEFAULT_LOG_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(normalize_level(level))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    try:
        file_handler = RotatingFileHandler(
            target,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # The directory may exist while a stale log file or its permissions
        # still prevent opening it (common after running a packaged app with
        # another user or through sudo).  Keep an implicit default logging
        # path non-fatal; an explicitly requested path must still fail loudly.
        if explicit_path:
            raise
        target = Path(tempfile.gettempdir()) / "djmidi" / DEFAULT_LOG_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            target,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    logger.info("Logging configured at %s", logging.getLevelName(logger.level))
    return target


__all__ = ["configure_logging", "default_log_path", "normalize_level"]
