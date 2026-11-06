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


CRASH_LOG_SUFFIX = "-crash.log"
# How much of a crash trace is copied into the main log at the next start.
_CRASH_REPORT_MAX_CHARS = 20_000
_crash_file = None  # the open file faulthandler writes to (kept alive)


def crash_log_path(log_path: str | Path) -> Path:
    """``djmidi.log`` -> ``djmidi-crash.log``, in the same folder."""
    path = Path(log_path)
    return path.with_name(path.stem + CRASH_LOG_SUFFIX)


def enable_crash_log(log_path: str | Path, *, only_if_enabled: bool = False) -> Path | None:
    """Make a native crash (a Qt segfault, an abort) leave its Python stack.

    `faulthandler` writes every thread's Python stack to a file of its own
    beside the log -- not the rotating log itself, which may be renamed under
    it -- that stays empty while all goes well. A crash left in that file by
    the previous session is copied into the main log first (a warning) and
    the file archived as ``.1``. Safe to call again: a changed log folder
    moves the crash file with it (`only_if_enabled`: only then -- what a
    Preferences change uses, so tests never turn it on). Returns the crash
    file, or None if it is off or can't be opened (crash reporting is best
    effort, never fatal)."""
    global _crash_file
    import faulthandler

    if only_if_enabled and _crash_file is None:
        return None
    target = crash_log_path(log_path)
    if _crash_file is not None and Path(_crash_file.name) == target:
        return target
    _report_previous_crash(target)
    try:
        handle = open(target, "a", encoding="utf-8")  # noqa: SIM115 -- must outlive this call
    except OSError:
        logging.getLogger(LOGGER_NAME).warning("Could not open the crash log %s", target, exc_info=True)
        return None
    faulthandler.enable(file=handle, all_threads=True)
    if _crash_file is not None:
        _crash_file.close()
    _crash_file = handle
    return target


def _report_previous_crash(target: Path) -> None:
    try:
        text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    except OSError:
        return
    if not text.strip():
        return
    if len(text) > _CRASH_REPORT_MAX_CHARS:
        text = "…\n" + text[-_CRASH_REPORT_MAX_CHARS:]
    logging.getLogger(LOGGER_NAME).warning("The previous session crashed. Its Python stack:\n%s", text.rstrip())
    try:
        target.replace(target.with_name(target.name + ".1"))
    except OSError:
        pass


def current_log_path() -> Path | None:
    """Return the file path the active rotating log handler writes to, if any."""
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        if isinstance(handler, RotatingFileHandler):
            return Path(handler.baseFilename)
    return None


__all__ = [
    "configure_logging",
    "crash_log_path",
    "current_log_path",
    "default_log_path",
    "enable_crash_log",
    "normalize_level",
]
