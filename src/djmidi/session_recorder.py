"""An unlimited recording of a live set: every MIDI event the Live Monitor
receives, streamed to a JSON Lines file in the workspace's ``Logs`` folder.

The Live Monitor's own log keeps the last 500 events (enough to read, not
to keep a set: a 2.5-hour set measured 218,573 events, 91% of them jog
ticks). The recorder writes each event as it comes, so memory never grows
with the set's length, and flushes about once a second so a crash loses
at most that second. One line per event::

    {"t": 1794850781.8856, "port": "DDJ-XP2", "dir": "in", "ch": 1,
     "type": "Note On", "d1": 27, "d2": 127}

Qt-free; reading a recording back is :func:`read_recording`.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import IO

from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

FLUSH_INTERVAL_S = 1.0
FILE_PREFIX = "live-"
FILE_SUFFIX = ".jsonl"


def recording_name(now: datetime) -> str:
    return f"{FILE_PREFIX}{now:%Y%m%d-%H%M%S}{FILE_SUFFIX}"


def _number(text: str) -> int | str:
    try:
        return int(text)
    except ValueError:
        return text


def event_row(event: MidiEvent) -> dict[str, object]:
    return {
        "t": round(event.timestamp, 4),
        "port": event.port,
        "dir": event.direction,
        "ch": _number(event.channel),
        "type": event.event_type,
        "d1": _number(event.data1),
        "d2": _number(event.data2),
    }


class SessionRecorder:
    """Records to a new file per :meth:`start` in ``directory``."""

    def __init__(
        self,
        directory: Path,
        now: Callable[[], datetime] = datetime.now,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.directory = Path(directory)
        self._now = now
        self._clock = clock
        self._handle: IO[str] | None = None
        self._last_flush = 0.0
        self.path: Path | None = None
        self.count = 0

    @property
    def is_recording(self) -> bool:
        return self._handle is not None

    def start(self) -> Path:
        """Opens a new recording file (never overwriting one) and returns it."""
        if self._handle is not None:
            return self.path  # type: ignore[return-value]
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / recording_name(self._now())
        number = 2
        while path.exists():
            path = self.directory / f"{path.stem.split('~')[0]}~{number}{FILE_SUFFIX}"
            number += 1
        self._handle = path.open("x", encoding="utf-8")
        self.path, self.count, self._last_flush = path, 0, self._clock()
        _LOGGER.info("Live set recording started: %s", path)
        return path

    def record(self, event: MidiEvent) -> None:
        if self._handle is None:
            return
        self._handle.write(json.dumps(event_row(event)) + "\n")
        self.count += 1
        now = self._clock()
        if now - self._last_flush >= FLUSH_INTERVAL_S:
            self._handle.flush()
            self._last_flush = now

    def stop(self) -> Path | None:
        """Closes the file; returns it, or None when nothing was recording."""
        if self._handle is None:
            return None
        self._handle.close()
        self._handle = None
        _LOGGER.info("Live set recording stopped: %d event(s) in %s", self.count, self.path)
        return self.path


def read_recording(path: Path) -> Iterator[dict[str, object]]:
    """Every event row of a recording, skipping a line cut short by a crash."""
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


__all__ = ["SessionRecorder", "event_row", "read_recording", "recording_name"]
