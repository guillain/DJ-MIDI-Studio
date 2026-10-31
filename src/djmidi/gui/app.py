from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from djmidi import startup_timing
from djmidi.gui.freeze_watchdog import FreezeWatchdog
from djmidi.gui.main_window import MainWindow
from djmidi.gui.theme import apply_theme
from djmidi.gui.translation import install_translators
from djmidi.logging_config import configure_logging
from djmidi.plugins.preferences import PluginPreferences, default_preferences_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="djmidi")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
        help="execution log verbosity (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="write the execution log to this file instead of the platform default",
    )
    parser.add_argument(
        "--startup-screenshot",
        default=None,
        metavar="PATH",
        help="save a PNG of the main window shortly after startup (CI smoke test)",
    )
    parser.add_argument(
        "--startup-screenshot-delay-ms",
        type=int,
        default=STARTUP_SCREENSHOT_DELAY_MS,
        help=argparse.SUPPRESS,
    )
    return parser


# Long enough for the first event-loop turns (deferred layout, lazy tab
# content) to paint, short enough to land well inside the smoke test's window.
STARTUP_SCREENSHOT_DELAY_MS = 2000


def save_window_screenshot(window: QWidget, path: str | os.PathLike[str]) -> bool:
    """Grab ``window`` into a PNG at ``path``; return whether it was written.

    Writes to a temporary sibling first and renames it, so a watcher polling for
    ``path`` (scripts/smoke_test_executable.py) never sees a half-written file.
    ``QWidget.grab()`` renders the widget itself rather than reading the screen,
    so it works on the offscreen platform and needs no screen-capture permission.
    """
    logger = logging.getLogger("djmidi.gui.app")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    if not window.grab().save(str(temporary), "PNG"):
        logger.error("Could not write startup screenshot to %s", target)
        return False
    os.replace(temporary, target)
    logger.info("Startup screenshot saved to %s", target)
    return True


def log_startup_timing(timer: startup_timing.StartupTimer) -> None:
    """Log how long startup took, once the window is on screen (issue #264)."""
    elapsed = timer.mark(startup_timing.FIRST_WINDOW_MILESTONE)
    logging.getLogger("djmidi.gui.app").info(
        "Startup: time to first window %.0f ms -- %s", elapsed * 1000, timer.summary()
    )


def run(argv: list[str] | None = None) -> int:
    timer = startup_timing.take()
    timer.mark("imports")
    parser = build_argument_parser()
    arguments, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    
    # An explicit --log-file always wins over the persisted preference; the
    # preference is only a fallback default for launches with no CLI override.
    preferences = PluginPreferences.load(default_preferences_path())
    preferred_log_path = arguments.log_file or preferences.log_path or None

    log_path = configure_logging(arguments.log_level, preferred_log_path)
    logger = logging.getLogger("djmidi.gui.app")
    logger.info("Starting DJ MIDI Studio")
    timer.mark("preferences and logging")
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setOrganizationName("DJ MIDI Studio")
    app.setApplicationName("DJ MIDI Studio")
    apply_theme(app, preferences.theme)
    timer.mark("Qt application")
    # Before any widget exists: tr() is resolved when a widget sets its text.
    install_translators(app, preferences.language)
    window = MainWindow()
    timer.mark("main window built")
    if arguments.startup_screenshot:
        window.first_run_wizard_enabled = False
    window.show()
    timer.mark("window shown")
    # The first event-loop turn is when the shown window actually paints.
    QTimer.singleShot(0, lambda: log_startup_timing(timer))
    if arguments.startup_screenshot:
        QTimer.singleShot(
            max(0, arguments.startup_screenshot_delay_ms),
            lambda: save_window_screenshot(window, arguments.startup_screenshot),
        )
    # Logs where the GUI thread is stuck if the window stops responding.
    watchdog = FreezeWatchdog()
    watchdog.start()
    result = app.exec()
    watchdog.stop()
    logger.info("DJ MIDI Studio stopped with exit code %s; log file: %s", result, log_path)
    return result


if __name__ == "__main__":
    sys.exit(run())
