"""The shared tracklist of Mix Together (remote mix, phase 11), Qt-free.

Every DJ's computer reads its own DJ software's play history (Serato or
Traktor, read-only, with `library.history`) and shares each new track on the
control line, so every computer shows the same tracklist: who played what,
and when. A DJ whose software doesn't write its history during the set can
type the track by hand.

- `HistoryWatcher` re-reads only the newest history file of each folder, and
  only when it changed, keeping the tracks played since the session started.
  Nothing is ever written to the history folders.
- `SharedTracklist` keeps the rows of every DJ. A row travels as
  ``{"k": "trk", "from": dj, "n": serial, "t": title, "a": artist, "at": unix}``;
  each computer sends its own rows again every few seconds, so a DJ who joins
  late, or a lost packet, still ends up with the whole list.
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from djmidi.library import history

_LOGGER = logging.getLogger(__name__)

MESSAGE_KIND = "trk"
RESEND_EVERY = 20  # dialog ticks (250 ms): own rows again every 5 s
_MAX_TEXT = 200


@dataclass(frozen=True)
class TrackRow:
    dj: int
    serial: int
    title: str
    artist: str
    at: float  # Unix seconds

    def label(self) -> str:
        return f"{self.artist} – {self.title}" if self.artist else self.title


def _clean(value: object) -> str:
    return value.strip()[:_MAX_TEXT] if isinstance(value, str) else ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class SharedTracklist:
    """This computer's copy of the tracklist: its own rows and the others'."""

    def __init__(self, me: int) -> None:
        self.me = me
        self._serial = 0
        self._rows: dict[tuple[int, int], TrackRow] = {}

    @property
    def rows(self) -> list[TrackRow]:
        return sorted(self._rows.values(), key=lambda row: (row.at, row.dj, row.serial))

    def add(self, title: str, artist: str, at: float) -> dict | None:
        """A track this DJ played: keep it and return the message to send."""
        title, artist = _clean(title), _clean(artist)
        if not title:
            return None
        self._serial += 1
        row = TrackRow(self.me, self._serial, title, artist, float(at))
        self._rows[(row.dj, row.serial)] = row
        return _message(row)

    def own_messages(self) -> list[dict]:
        return [_message(row) for row in self.rows if row.dj == self.me]

    def receive(self, message: dict) -> TrackRow | None:
        """Another DJ's row, the first time it arrives."""
        if message.get("k") != MESSAGE_KIND:
            return None
        dj, serial, at = message.get("from"), message.get("n"), message.get("at")
        title = _clean(message.get("t"))
        if not _is_int(dj) or not _is_int(serial) or dj == self.me or not title:
            return None
        if not isinstance(at, (int, float)) or isinstance(at, bool) or (dj, serial) in self._rows:
            return None
        row = TrackRow(dj, serial, title, _clean(message.get("a")), float(at))
        self._rows[(dj, serial)] = row
        return row


def _message(row: TrackRow) -> dict:
    return {"k": MESSAGE_KIND, "from": row.dj, "n": row.serial, "t": row.title, "a": row.artist, "at": row.at}


# Where a DJ looks a track up: each site's public search page, opened only when the DJ clicks.
SEARCH_SITES = (
    ("Beatport", "https://www.beatport.com/search?q={q}"),
    ("Bandcamp", "https://bandcamp.com/search?q={q}"),
    ("Discogs", "https://www.discogs.com/search/?q={q}&type=all"),
    ("YouTube", "https://www.youtube.com/results?search_query={q}"),
)


def search_urls(row: TrackRow) -> list[tuple[str, str]]:
    """(site, search URL) for a track: its artist and title, nothing else."""
    from urllib.parse import quote_plus

    query = quote_plus(f"{row.artist} {row.title}".strip())
    return [(site, url.format(q=query)) for site, url in SEARCH_SITES]


def for_listeners(rows: list[TrackRow], name_of) -> list[dict]:
    """Every row with its DJ's name (``who``), for listeners who don't know the room."""
    return [{**_message(row), "who": name_of(row.dj)} for row in rows]


def listener_name(message: dict) -> str:
    return _clean(message.get("who"))


def text_export(rows: list[TrackRow], name_of, started: datetime | None = None) -> str:
    """The tracklist as plain text, one line per track (for a post or a description)."""
    lines = []
    if started is not None:
        lines.append(f"Mix Together — {started:%Y-%m-%d %H:%M}")
        lines.append("")
    for row in rows:
        lines.append(f"{datetime.fromtimestamp(row.at):%H:%M}  {name_of(row.dj)} — {row.label()}")  # noqa: DTZ006
    return "\n".join(lines) + "\n"


def tracklist_name(started: datetime) -> str:
    return f"mix-together-tracklist-{started:%Y%m%d-%H%M%S}.txt"


_PATTERNS = {history.SOURCE_SERATO: "*.session", history.SOURCE_TRAKTOR: "*.nml"}
_PARSERS = {history.SOURCE_SERATO: history.parse_serato_session, history.SOURCE_TRAKTOR: history.parse_traktor_history}


def watchable_folder(folder: str | os.PathLike[str]) -> tuple[str, Path] | None:
    """(source, folder of history files) for a Serato or Traktor history folder."""
    path = Path(folder)
    source = history.detect_source(path)
    if source == history.SOURCE_SERATO and (path / "Sessions").is_dir():
        path = path / "Sessions"
    return (source, path) if source in _PATTERNS else None


class HistoryWatcher:
    """New tracks in the DJ software's history since `since` (read-only)."""

    def __init__(self, folders: dict[str, Path], since: datetime) -> None:
        self.folders = dict(folders)
        self.since = since
        self._mtimes: dict[Path, int] = {}
        self._seen: set[tuple[str, float | None]] = set()
        self.error: str | None = None

    def poll(self) -> list[history.PlayedEntry]:
        found = []
        for source, folder in self.folders.items():
            newest = _newest(folder, _PATTERNS[source])
            if newest is None:
                continue
            try:
                mtime = newest.stat().st_mtime_ns
                if self._mtimes.get(newest) == mtime:
                    continue
                session = _PARSERS[source](newest)
            except (OSError, ET.ParseError, ValueError) as exc:
                self.error = str(exc)
                _LOGGER.warning("History not read from %s: %s", newest, exc)
                continue
            self.error = None
            self._mtimes[newest] = mtime
            for entry in session.entries:
                at = entry.played_at
                if not entry.played or at is None or at < self.since:
                    continue
                key = (entry.path, at.timestamp())
                if key not in self._seen:
                    self._seen.add(key)
                    found.append(entry)
        found.sort(key=lambda entry: entry.played_at)
        return found


def _newest(folder: Path, pattern: str) -> Path | None:
    try:
        files = [p for p in folder.glob(pattern) if not p.name.startswith("._")]
        return max(files, key=lambda p: p.stat().st_mtime_ns) if files else None
    except OSError:
        return None


def entry_texts(entry: history.PlayedEntry) -> tuple[str, str]:
    """Title and artist of a history row, the file name when the row has no title."""
    title = entry.title or Path(entry.path.replace("\\", "/")).stem
    return title, entry.artist or ""
