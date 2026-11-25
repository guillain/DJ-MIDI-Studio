"""Keeps Qt's harmless audio-device chatter out of the terminal.

On macOS, Qt Multimedia lists the sound cards when the Mix Together tab
fills its audio menus. For a card with more than two channels (a DJ
controller's built-in interface, say) Core Audio gives the extra channels
the generic label "discrete" (400), which Qt's channel layouts have no name
for: Qt prints "audio device has unrecognized channel" once per channel,
and the info line "Using Qt multimedia with FFmpeg". Neither is a problem:
the channels play fine.

:func:`install` drops exactly those messages (counted, one DEBUG line per
card listing in the log) and passes every other Qt message on, unchanged, to
the handler that was there before (Qt's own, which prints to stderr).
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

_LOGGER = logging.getLogger(__name__)

# Prefixes of the messages that are noise, never a problem to report.
QUIET_PREFIXES = (
    "audio device has unrecognized channel",
    "Using Qt multimedia with FFmpeg",
)

_previous = None
_installed = False
dropped = 0


def is_noise(message: str) -> bool:
    return message.startswith(QUIET_PREFIXES)


def _handler(kind: QtMsgType, context, message: str) -> None:
    global dropped
    if is_noise(message):
        dropped += 1
        if message.startswith(QUIET_PREFIXES[0] + ", index: 2 "):  # the first extra channel of a card
            _LOGGER.debug("Qt Multimedia: a sound card has unnamed extra channels (harmless)")
        return
    if _previous is not None:
        _previous(kind, context, message)
    else:
        sys.stderr.write(message + "\n")


def install() -> None:
    """Idempotent: install once, before Qt Multimedia lists the devices."""
    global _previous, _installed
    if _installed:
        return
    _previous = qInstallMessageHandler(_handler)
    _installed = True


__all__ = ["QUIET_PREFIXES", "install", "is_noise"]
