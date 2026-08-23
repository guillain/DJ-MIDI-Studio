from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from djmidi.gui.main_window import MainWindow
from djmidi.gui.theme import apply_theme
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
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    
    # An explicit --log-file always wins over the persisted preference; the
    # preference is only a fallback default for launches with no CLI override.
    preferences = PluginPreferences.load(default_preferences_path())
    preferred_log_path = arguments.log_file or preferences.log_path or None

    log_path = configure_logging(arguments.log_level, preferred_log_path)
    logger = logging.getLogger("djmidi.gui.app")
    logger.info("Starting DJ MIDI Studio")
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setOrganizationName("DJ MIDI Studio")
    app.setApplicationName("DJ MIDI Studio")
    apply_theme(app)
    window = MainWindow()
    window.show()
    result = app.exec()
    logger.info("DJ MIDI Studio stopped with exit code %s; log file: %s", result, log_path)
    return result


if __name__ == "__main__":
    sys.exit(run())
