"""An unlimited recording of a live set: every MIDI event the Live Monitor
receives, streamed to a JSON Lines file in the workspace's ``Logs`` folder.

The Live Monitor's own log keeps the last 500 events (enough to read, not
to keep a set: a 2.5-hour set measured 218,573 events, 91% of them jog
ticks). The recorder writes each event as it comes, so memory never grows
with the set's length, and flushes about once a second so a crash loses
at most that second. One line per event::

    {"t": 717540.8592, "port": "DDJ-XP2", "dir": "in", "ch": 1,
     "type": "Note On", "d1": 27, "d2": 127}

``t`` is the computer's monotonic clock (seconds, not a date). Every other
MIDI message (SysEx, MIDI Clock, start/stop, song position, aftertouch,
program change, …) is kept too, as its raw bytes::

    {"t": 717541.02, "port": "XDJ-XZ (1)", "dir": "in", "type": "sysex", "b": [240, 0, 64, 5, 247]}

Beside it, with the same name (a dataset for post-treatment, every row on
the same clock ``t``; ``manifest["wall_offset"]`` + ``t`` = Unix time):

- ``<name>.manifest.json``: what was plugged in and running (written at
  start, updated at stop with the counts);
- ``<name>.tracks.jsonl``: each track the DJ software's history shows played
  (read-only), ``{"t", "source", "title", "artist", "path", "deck", "duration"}``;
- ``<name>.events.jsonl``: what the app saw, ``{"t", "kind", ...}`` (deck
  layer changes, deck alerts, macros played).

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
MANIFEST_SUFFIX = ".manifest.json"
TRACKS_SUFFIX = ".tracks.jsonl"
EVENTS_SUFFIX = ".events.jsonl"
DATASET_FORMAT = "djmidi-live-set/1"


def companion(path: Path, suffix: str) -> Path:
    """``live-….tracks.jsonl`` and the others, next to the MIDI recording."""
    return Path(path).with_name(Path(path).name.removesuffix(FILE_SUFFIX) + suffix)


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
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.directory = Path(directory)
        self._now = now
        self._clock = clock
        self._wall = wall
        self._handle: IO[str] | None = None
        self._side: dict[str, IO[str]] = {}
        self._last_flush = 0.0
        self.path: Path | None = None
        self.count = 0
        self.track_count = 0
        self.note_count = 0
        self._offset = 0.0
        self.manifest: dict[str, object] = {}

    @property
    def is_recording(self) -> bool:
        return self._handle is not None

    def start(self, manifest: dict[str, object] | None = None) -> Path:
        """Opens a new recording file (never overwriting one) and returns it;
        `manifest` (plain JSON values) goes in ``<name>.manifest.json``."""
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
        self.track_count = self.note_count = 0
        self._offset = self._wall() - self._last_flush
        self.manifest = {
            "format": DATASET_FORMAT,
            "started": round(self._wall(), 3),
            "clock": "t = monotonic seconds; Unix time = t + wall_offset",
            "wall_offset": round(self._offset, 4),
            **(manifest or {}),
        }
        self._write_manifest()
        _LOGGER.info("Live set recording started: %s", path)
        return path

    def record(self, event: MidiEvent) -> None:
        if self._handle is None:
            return
        self._write_row(event_row(event))

    def record_raw(self, port: str, direction: str, kind: str, data: list[int], timestamp: float) -> None:
        """A MIDI message the app doesn't otherwise read (SysEx, clock, …)."""
        if self._handle is None:
            return
        self._write_row({"t": round(timestamp, 4), "port": port, "dir": direction, "type": kind, "b": list(data)})

    def _write_row(self, row: dict[str, object]) -> None:
        assert self._handle is not None
        self._handle.write(json.dumps(row) + "\n")
        self.count += 1
        now = self._clock()
        if now - self._last_flush >= FLUSH_INTERVAL_S:
            self._handle.flush()
            self._last_flush = now

    def add_track(self, at: float, source: str, title: str, artist: str = "", path: str = "",
                  deck: int | None = None, duration: float | None = None) -> None:
        """A track the DJ software's history shows played at `at` (Unix time)."""
        row = {"t": round(at - self._offset, 3), "wall": round(at, 3), "source": source, "title": title,
               "artist": artist, "path": path, "deck": deck, "duration": duration}
        if self._side_write(TRACKS_SUFFIX, row):
            self.track_count += 1

    def note(self, kind: str, **data: object) -> None:
        """Something the app saw (``kind`` = "deck", "deck_alert", "macro", …)."""
        if self._side_write(EVENTS_SUFFIX, {"t": round(self._clock(), 4), "kind": kind, **data}):
            self.note_count += 1

    def _side_write(self, suffix: str, row: dict[str, object]) -> bool:
        if self._handle is None or self.path is None:
            return False
        handle = self._side.get(suffix)
        if handle is None:
            handle = self._side[suffix] = companion(self.path, suffix).open("a", encoding="utf-8")
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()  # rare rows: each one is kept
        return True

    def _write_manifest(self) -> None:
        if self.path is not None:
            text = json.dumps(self.manifest, ensure_ascii=False, indent=2)
            companion(self.path, MANIFEST_SUFFIX).write_text(text + "\n", encoding="utf-8")

    def stop(self) -> Path | None:
        """Closes the files; returns the MIDI one, or None when nothing was recording."""
        if self._handle is None:
            return None
        self._handle.close()
        self._handle = None
        for handle in self._side.values():
            handle.close()
        self._side.clear()
        self.manifest.update(
            stopped=round(self._wall(), 3), midi_events=self.count, tracks=self.track_count, app_events=self.note_count
        )
        try:
            self._write_manifest()
        except OSError:
            _LOGGER.exception("Live set manifest not updated")
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


def read_rows(path: Path) -> list[dict[str, object]]:
    """The rows of a companion JSON Lines file, [] when it doesn't exist."""
    path = Path(path)
    return list(read_recording(path)) if path.is_file() else []


__all__ = [
    "DATASET_FORMAT",
    "EVENTS_SUFFIX",
    "MANIFEST_SUFFIX",
    "TRACKS_SUFFIX",
    "SessionRecorder",
    "companion",
    "event_row",
    "read_recording",
    "read_rows",
    "recording_name",
]
