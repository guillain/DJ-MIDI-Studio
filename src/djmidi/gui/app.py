from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from djmidi.gui.main_window import MainWindow
from djmidi.logging_config import configure_logging


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
    log_path = configure_logging(arguments.log_level, arguments.log_file)
    logger = logging.getLogger("djmidi.gui.app")
    logger.info("Starting DJ MIDI Studio")
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setOrganizationName("DJ MIDI Studio")
    app.setApplicationName("DJ MIDI Studio")
    window = MainWindow()
    window.show()
    result = app.exec()
    logger.info("DJ MIDI Studio stopped with exit code %s; log file: %s", result, log_path)
    return result


if __name__ == "__main__":
    sys.exit(run())
