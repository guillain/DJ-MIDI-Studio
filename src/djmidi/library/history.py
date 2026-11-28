"""Played-tracks history (issue #227): read Serato, Traktor and rekordbox history, read-only.

Two on-disk formats, both checked read-only against the maintainer's real
folders before writing this (never written to):

- **Serato** ``_Serato_/History/Sessions/<N>.session``: the same flat
  "4-char tag + u32 BE length" chunk stream as a crate
  (`serato_library.iter_chunks`) -- a ``vrsn`` header then one ``oent`` per
  history row, each wrapping an ``adat`` chunk. ``adat`` is itself a list of
  *numbered* fields (u32 BE field id, u32 BE length, value). Fields read here
  (checked across 250 real sessions / 9,527 rows): 2 = full file path
  (UTF-16BE, NUL-terminated; absolute POSIX on macOS, ``D:\\...`` for rows
  recorded on Windows), 6 = title, 7 = artist, 28 = start time (u64 BE Unix
  seconds), 31 = deck, 48 = session id (always equals the file's ``<N>``),
  50 = the "played" checkbox of Serato's history panel (1 byte; 0 on 777 of
  the 9,527 real rows). Every other field is skipped. ``history.database``
  (session summaries) is not needed and not read.
- **Traktor** ``History/history_<date>.nml``: a regular NML whose single
  ``HISTORY`` playlist lists ``PRIMARYKEY`` entries (``VOLUME/:DIR/:FILE``, as
  in `traktor_library`) each followed by an ``EXTENDEDDATA`` element:
  ``STARTDATE`` = ``year << 16 | month << 8 | day`` (real file
  ``history_2025y11m07d…`` carries 132713223 = 2025-11-07), ``STARTTIME`` =
  seconds since local midnight, ``DECK``, ``DURATION`` (seconds) and
  ``PLAYEDPUBLIC`` (1 = played to the audience, 0 = only pre-listened).
  Title/artist come from the file's own ``COLLECTION`` entries.

- **rekordbox** (#455) device export ``PIONEER/rekordbox/export.pdb`` (a USB
  stick, SD card or any folder rekordbox exported to): the sessions a player
  recorded ("HISTORY 001", ...) with their tracks in play order
  (`rekordbox_library.parse_history`). No play time and no deck are stored.
  Track paths are relative to the export's root (``/Contents/...``), so they
  are resolved against the folder holding ``PIONEER``.

Times are returned as timezone-aware datetimes in the computer's local zone
(Serato stores a Unix timestamp; Traktor stores local wall-clock time, read
as the computer's local zone).

A row whose played flag is off is kept (``PlayedEntry.played`` is False) so
a caller can show it, but it doesn't count as a play: "never played" means
no row with ``played`` set.
"""

from __future__ import annotations

import logging
import os
import struct
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import rekordbox_library, rekordbox_master
from .serato_library import iter_chunks
from .workspace import traktor_key_to_path

_LOGGER = logging.getLogger(__name__)

SOURCE_SERATO = "serato"
SOURCE_TRAKTOR = "traktor"
SOURCE_REKORDBOX = "rekordbox"

# Serato session-row field ids (see the module docstring).
_SERATO_PATH = 2
_SERATO_TITLE = 6
_SERATO_ARTIST = 7
_SERATO_START = 28
_SERATO_DECK = 31
_SERATO_PLAYED = 50

_NEVER = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class PlayedEntry:
    path: str
    played_at: datetime | None
    source: str
    session: str
    title: str | None = None
    artist: str | None = None
    deck: int | None = None
    duration: float | None = None
    played: bool = True


@dataclass
class HistorySession:
    source: str
    name: str
    entries: list[PlayedEntry] = field(default_factory=list)

    @property
    def started_at(self) -> datetime | None:
        times = [e.played_at for e in self.entries if e.played_at is not None]
        return min(times) if times else None


@dataclass
class TrackPlays:
    path: str
    play_count: int
    first_played: datetime | None
    last_played: datetime | None


def default_history_dirs(music_dir: str | os.PathLike[str] | None = None) -> dict[str, Path]:
    """The usual history folders that actually exist: under ``~/Music``, and
    rekordbox's own library (master.db) beside it."""
    base = Path(music_dir) if music_dir is not None else _dj_home() / "Music"
    candidates = {
        SOURCE_SERATO: base / "_Serato_" / "History" / "Sessions",
        SOURCE_TRAKTOR: base / "_Traktor" / "History",
    }
    found: dict[str, Path] = {source: path for source, path in candidates.items() if path.is_dir()}
    master = rekordbox_master.default_master_db(base.parent)
    if master.is_file():  # rekordbox's own library on this computer
        found[SOURCE_REKORDBOX] = master.parent
    elif rekordbox_export(base) is not None:
        found[SOURCE_REKORDBOX] = base
    return found


def _dj_home() -> Path:
    override = os.environ.get("DJMIDI_DJ_HOME")  # tests never read the real home
    return Path(override) if override else Path.home()


def rekordbox_master_db(folder: str | os.PathLike[str]) -> Path | None:
    """rekordbox's own master.db: `folder` itself or the file inside it."""
    path = Path(folder)
    candidate = path if rekordbox_master.is_master_db(path) else path / rekordbox_master.MASTER_DB
    return candidate if candidate.is_file() else None


def rekordbox_export(folder: str | os.PathLike[str]) -> Path | None:
    """The rekordbox device export under `folder`: given the export's root,
    its ``PIONEER`` folder or ``PIONEER/rekordbox`` itself."""
    path = Path(folder)
    for candidate in (
        path / "PIONEER" / "rekordbox" / "export.pdb",
        path / "rekordbox" / "export.pdb",
        path / "export.pdb",
    ):
        if candidate.is_file() and candidate.parent.parent.name.upper() == "PIONEER":
            return candidate
    return None


def detect_source(folder: str | os.PathLike[str]) -> str | None:
    """Which history format a user-chosen folder holds, if any."""
    path = Path(folder)
    if (path / "Sessions").is_dir() or any(path.glob("*.session")):
        return SOURCE_SERATO
    if any(p for p in path.glob("*.nml") if not p.name.startswith("._")):
        return SOURCE_TRAKTOR
    if rekordbox_export(path) is not None or rekordbox_master_db(path) is not None:
        return SOURCE_REKORDBOX
    return None


# --- Serato ---------------------------------------------------------------


def iter_serato_fields(data: bytes) -> Iterable[tuple[int, bytes]]:
    """Yield (field id, value) from an ``adat`` payload; stops on truncation."""
    offset = 0
    while offset + 8 <= len(data):
        field_id, length = struct.unpack(">II", data[offset : offset + 8])
        end = offset + 8 + length
        if end > len(data):
            _LOGGER.warning("Serato history field %d runs past its row, stopping", field_id)
            return
        yield field_id, data[offset + 8 : end]
        offset = end


def _serato_text(value: bytes | None) -> str | None:
    if not value:
        return None
    text = value.decode("utf-16-be", errors="replace").rstrip("\0")
    return text or None


def _serato_int(value: bytes | None) -> int | None:
    if value is None or len(value) not in (1, 2, 4, 8):
        return None
    return int.from_bytes(value, "big")


def _serato_time(value: bytes | None) -> datetime | None:
    seconds = _serato_int(value)
    if not seconds:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).astimezone()
    except (OverflowError, OSError, ValueError):
        return None


def parse_serato_session(path: str | os.PathLike[str]) -> HistorySession:
    """Read one ``<N>.session`` file."""
    session = HistorySession(SOURCE_SERATO, f"Serato session {Path(path).stem}")
    data = Path(path).read_bytes()
    for tag, value in iter_chunks(data):
        if tag != "oent":
            continue
        for inner_tag, inner in iter_chunks(value):
            if inner_tag != "adat":
                continue
            fields = dict(iter_serato_fields(inner))
            track_path = _serato_text(fields.get(_SERATO_PATH))
            if not track_path:
                continue
            played = _serato_int(fields.get(_SERATO_PLAYED))
            session.entries.append(
                PlayedEntry(
                    path=track_path,
                    played_at=_serato_time(fields.get(_SERATO_START)),
                    source=SOURCE_SERATO,
                    session=session.name,
                    title=_serato_text(fields.get(_SERATO_TITLE)),
                    artist=_serato_text(fields.get(_SERATO_ARTIST)),
                    deck=_serato_int(fields.get(_SERATO_DECK)),
                    played=played != 0,
                )
            )
    return session


def read_serato_history(sessions_dir: str | os.PathLike[str]) -> list[HistorySession]:
    """Every ``*.session`` in `sessions_dir` (a ``History`` folder is accepted
    too: its ``Sessions`` child is used). Unreadable files are logged and skipped."""
    folder = Path(sessions_dir)
    if (folder / "Sessions").is_dir():
        folder = folder / "Sessions"
    return _read_all(sorted(folder.glob("*.session")), parse_serato_session)


# --- Traktor --------------------------------------------------------------


def decode_traktor_date(value: int) -> tuple[int, int, int] | None:
    """``STARTDATE`` → (year, month, day); ``None`` when it isn't a date."""
    year, month, day = value >> 16, (value >> 8) & 0xFF, value & 0xFF
    if not (1 <= month <= 12 and 1 <= day <= 31 and year >= 1900):
        return None
    return year, month, day


def _traktor_time(date_text: str | None, time_text: str | None) -> datetime | None:
    try:
        decoded = decode_traktor_date(int(date_text or ""))
        seconds = int(time_text or 0)
    except ValueError:
        return None
    if decoded is None:
        return None
    try:
        # Local wall-clock time: `astimezone()` on the naive value applies
        # the computer's zone, DST included.
        return (datetime(*decoded) + timedelta(seconds=seconds)).astimezone()  # noqa: DTZ001
    except ValueError:
        return None


def _int(text: str | None) -> int | None:
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def _float(text: str | None) -> float | None:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def parse_traktor_history(path: str | os.PathLike[str]) -> HistorySession:
    """Read one Traktor ``History/*.nml`` file."""
    root = ET.parse(path).getroot()
    session = HistorySession(SOURCE_TRAKTOR, f"Traktor {Path(path).stem}")
    names: dict[str, tuple[str | None, str | None]] = {}
    for entry in root.iterfind("COLLECTION/ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        key = location.get("VOLUME", "") + location.get("DIR", "") + location.get("FILE", "")
        names[key] = (entry.get("TITLE") or None, entry.get("ARTIST") or None)
    for playlist_entry in root.iter("ENTRY"):
        primary = playlist_entry.find("PRIMARYKEY")
        if primary is None or primary.get("TYPE") != "TRACK" or not primary.get("KEY"):
            continue
        key = primary.get("KEY", "")
        extended = playlist_entry.find("EXTENDEDDATA")
        attrs = extended.attrib if extended is not None else {}
        title, artist = names.get(key, (None, None))
        session.entries.append(
            PlayedEntry(
                path=traktor_key_to_path(key),
                played_at=_traktor_time(attrs.get("STARTDATE"), attrs.get("STARTTIME")),
                source=SOURCE_TRAKTOR,
                session=session.name,
                title=title,
                artist=artist,
                deck=_int(attrs.get("DECK")),
                duration=_float(attrs.get("DURATION")),
                played=attrs.get("PLAYEDPUBLIC", "1") != "0",
            )
        )
    return session


def read_traktor_history(history_dir: str | os.PathLike[str]) -> list[HistorySession]:
    """Every ``*.nml`` in a Traktor ``History`` folder; bad files are skipped."""
    return _read_all(sorted(Path(history_dir).glob("*.nml")), parse_traktor_history)


# --- rekordbox ------------------------------------------------------------


def read_rekordbox_history(folder: str | os.PathLike[str]) -> list[HistorySession]:
    """The history sessions of rekordbox's master.db in `folder` (read from a
    copy), else of the rekordbox export under `folder`."""
    master = rekordbox_master_db(folder)
    if master is not None:
        return read_rekordbox_master_history(master)
    pdb = rekordbox_export(folder)
    if pdb is None:
        return []
    try:
        tracks = {track.id: track for track in rekordbox_library.parse_export(pdb)}
        sessions = rekordbox_library.parse_history(pdb)
    except (OSError, ValueError, struct.error) as exc:
        _LOGGER.warning("Skipping unreadable rekordbox export %s: %s", pdb, exc)
        return []
    root = pdb.parent.parent.parent  # the folder holding PIONEER
    result = []
    for session in sessions:
        entries = []
        for track_id in session.track_ids:
            track = tracks.get(track_id)
            if track is None:
                continue
            entries.append(
                PlayedEntry(
                    path=str(root / track.file_path.lstrip("/")),
                    played_at=None,
                    source=SOURCE_REKORDBOX,
                    session=session.name,
                    title=track.title or None,
                    artist=track.artist or None,
                    duration=float(track.duration_seconds) if track.duration_seconds else None,
                )
            )
        if entries:
            result.append(HistorySession(SOURCE_REKORDBOX, session.name, entries))
    return result


# --- combining ------------------------------------------------------------


def _read_all(paths, reader) -> list[HistorySession]:
    sessions = []
    for path in paths:
        if path.name.startswith("._"):
            # macOS AppleDouble sidecars (real Traktor History folder has one
            # per file on a non-HFS volume) -- metadata, not history.
            continue
        try:
            session = reader(path)
        except (OSError, ET.ParseError) as exc:
            _LOGGER.warning("Skipping unreadable history file %s: %s", path, exc)
            continue
        if session.entries:
            sessions.append(session)
    return sessions


def read_rekordbox_master_history(master: str | os.PathLike[str]) -> list[HistorySession]:
    """rekordbox's own history (master.db): one session per day folder entry,
    each track with the time rekordbox added it to the history."""
    try:
        library = rekordbox_master.read_library(master)
    except (OSError, rekordbox_master.MasterDbError) as exc:
        _LOGGER.warning("Skipping unreadable rekordbox library %s: %s", master, exc)
        return []
    result = []
    for history in library.histories:
        entries = []
        for track_id, added_at in history.entries:
            track = library.tracks[track_id]
            entries.append(
                PlayedEntry(
                    path=track.path,
                    played_at=added_at,
                    source=SOURCE_REKORDBOX,
                    session=history.name,
                    title=track.title or None,
                    artist=track.artist or None,
                    duration=track.duration,
                )
            )
        if entries:
            result.append(HistorySession(SOURCE_REKORDBOX, history.name, entries))
    return result


def read_history(dirs: dict[str, str | os.PathLike[str]]) -> list[HistorySession]:
    """Sessions from every ``{source: folder}`` pair, newest first."""
    readers = {
        SOURCE_SERATO: read_serato_history,
        SOURCE_TRAKTOR: read_traktor_history,
        SOURCE_REKORDBOX: read_rekordbox_history,
    }
    sessions: list[HistorySession] = []
    for source, folder in dirs.items():
        sessions.extend(readers[source](folder))
    sessions.sort(key=lambda s: s.started_at or _NEVER, reverse=True)
    return sessions


def summarize_plays(sessions: Iterable[HistorySession]) -> dict[str, TrackPlays]:
    """Per path: how many times it was played, first and last time."""
    plays: dict[str, TrackPlays] = {}
    for session in sessions:
        for entry in session.entries:
            if not entry.played:
                continue
            current = plays.get(entry.path)
            if current is None:
                plays[entry.path] = TrackPlays(entry.path, 1, entry.played_at, entry.played_at)
                continue
            current.play_count += 1
            if entry.played_at is not None:
                if current.first_played is None or entry.played_at < current.first_played:
                    current.first_played = entry.played_at
                if current.last_played is None or entry.played_at > current.last_played:
                    current.last_played = entry.played_at
    return plays


def never_played(library_paths: Iterable[str], sessions: Iterable[HistorySession]) -> list[str]:
    """The library paths with no played row in `sessions`, in input order."""
    played = summarize_plays(sessions)
    return [path for path in library_paths if path not in played]
