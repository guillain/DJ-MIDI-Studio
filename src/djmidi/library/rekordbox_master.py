"""rekordbox's own library (``master.db``, rekordbox 6 and 7) and its
OneLibrary device exports (``exportLibrary.db``), read-only.

``master.db`` is the collection rekordbox keeps on the computer: every
track, playlist and history session. It is a SQLCipher-encrypted SQLite
database. The key is not ours: the optional ``pyrekordbox`` package (MIT,
https://github.com/dylanljones/pyrekordbox, ``uv sync --extra rekordbox``)
opens it, and this module only runs plain SQL on what it opens.

Never the DJ's file: :func:`read_library` copies ``master.db`` (and its
``-wal`` / ``-shm`` companions) to a temporary folder, reads the copy and
deletes it. Nothing is ever written back, whether or not rekordbox runs.

Table and column names (``djmdContent``, ``djmdPlaylist``,
``djmdSongPlaylist``, ``djmdHistory``, ``djmdSongHistory``) were read from
a real rekordbox 7 ``master.db`` (2026-11-28). Smart playlists
(``Attribute`` 4) hold rules, not tracks, and are skipped.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MASTER_DB = "master.db"
ONELIBRARY_DB = "exportLibrary.db"
_COMPANIONS = ("-wal", "-shm")

_FOLDER = 1


class MasterDbError(RuntimeError):
    """master.db could not be opened or read."""


class MasterDbUnavailable(MasterDbError):
    """pyrekordbox (the optional 'rekordbox' extra) is not installed."""


@dataclass
class MasterTrack:
    id: str
    path: str
    title: str = ""
    artist: str = ""
    bpm: float | None = None
    duration: float | None = None


@dataclass
class MasterHistory:
    name: str
    entries: list[tuple[str, datetime | None]] = field(default_factory=list)  # (track id, added at)


@dataclass
class MasterLibrary:
    tracks: dict[str, MasterTrack] = field(default_factory=dict)
    playlists: dict[str, list[str]] = field(default_factory=dict)  # name -> track paths, in order
    histories: list[MasterHistory] = field(default_factory=list)


Opener = Callable[[Path], tuple[Any, Callable[[], None]]]


def default_master_db(home: Path | None = None) -> Path:
    """Where rekordbox keeps master.db on this computer."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata and home is None else (home or Path.home()) / "AppData" / "Roaming"
        return base / "Pioneer" / "rekordbox" / MASTER_DB
    return (home or Path.home()) / "Library" / "Pioneer" / "rekordbox" / MASTER_DB


def is_master_db(path: str | os.PathLike[str]) -> bool:
    return Path(path).name.lower() == MASTER_DB


def is_onelibrary(path: str | os.PathLike[str]) -> bool:
    """A OneLibrary device export (formerly Device Library Plus), the newer
    encrypted USB format next to export.pdb."""
    return Path(path).name.lower() == ONELIBRARY_DB.lower()


def available() -> bool:
    try:
        import pyrekordbox  # noqa: F401
    except ImportError:
        return False
    return True


def _open_with_pyrekordbox(path: Path) -> tuple[Any, Callable[[], None]]:
    try:
        if is_onelibrary(path):
            from pyrekordbox.onelibrary import OneLibrary as Database
        else:
            from pyrekordbox.masterdb import MasterDatabase as Database
    except ImportError as exc:
        raise MasterDbUnavailable(str(exc)) from exc
    database = Database(path=str(path))
    connection = database.engine.raw_connection()

    def close() -> None:
        connection.close()
        database.close()

    return connection, close


def read_library(path: str | os.PathLike[str], opener: Opener | None = None) -> MasterLibrary:
    """Tracks, playlists and history of a master.db or of a OneLibrary
    export (exportLibrary.db), read from a copy. A OneLibrary export's track
    paths stay relative to the device root, as rekordbox wrote them."""
    source = Path(path)
    if not source.is_file():
        raise MasterDbError(f"{source} not found")
    with tempfile.TemporaryDirectory(prefix="djmidi-rekordbox-") as folder:
        copy = Path(folder) / (ONELIBRARY_DB if is_onelibrary(source) else MASTER_DB)
        shutil.copy2(source, copy)
        for suffix in _COMPANIONS:
            companion = source.with_name(source.name + suffix)
            if companion.is_file():
                shutil.copy2(companion, copy.with_name(copy.name + suffix))
        try:
            connection, close = (opener or _open_with_pyrekordbox)(copy)
        except MasterDbUnavailable:
            raise
        except Exception as exc:  # SQLCipher / SQLAlchemy errors: a wrong key or a damaged copy
            raise MasterDbError(str(exc)) from exc
        try:
            return _read(connection.cursor(), _ONELIBRARY_SQL if is_onelibrary(source) else _MASTER_SQL)
        except Exception as exc:
            raise MasterDbError(str(exc)) from exc
        finally:
            close()


# The queries per format; each returns the same columns. OneLibrary column
# names come from a real exportLibrary.db written by rekordbox 7 (2026-11-28):
# no deleted flag, no time in the history tables, ``attribute`` 0 = playlist,
# 1 = folder (the only values seen; other kinds are skipped).
_MASTER_SQL = {
    "tracks": "SELECT c.ID, c.FolderPath, c.Title, a.Name, c.BPM, c.Length FROM djmdContent c "
    "LEFT JOIN djmdArtist a ON a.ID = c.ArtistID WHERE COALESCE(c.rb_local_deleted, 0) = 0",
    "playlists": "SELECT ID, Name, Attribute, ParentID FROM djmdPlaylist WHERE COALESCE(rb_local_deleted, 0) = 0 ORDER BY Seq",
    "playlist_songs": "SELECT PlaylistID, ContentID, created_at FROM djmdSongPlaylist "
    "WHERE COALESCE(rb_local_deleted, 0) = 0 ORDER BY PlaylistID, TrackNo",
    "histories": "SELECT ID, Name, Attribute FROM djmdHistory WHERE COALESCE(rb_local_deleted, 0) = 0 ORDER BY DateCreated",
    "history_songs": "SELECT HistoryID, ContentID, created_at FROM djmdSongHistory "
    "WHERE COALESCE(rb_local_deleted, 0) = 0 ORDER BY HistoryID, TrackNo",
    "playlist_kinds": (0,),
}
_ONELIBRARY_SQL = {
    "tracks": "SELECT c.content_id, c.path, c.title, a.name, c.bpmx100, c.length FROM content c "
    "LEFT JOIN artist a ON a.artist_id = c.artist_id_artist",
    "playlists": "SELECT playlist_id, name, attribute, playlist_id_parent FROM playlist ORDER BY sequenceNo",
    "playlist_songs": "SELECT playlist_id, content_id, NULL FROM playlist_content ORDER BY playlist_id, sequenceNo",
    "histories": "SELECT history_id, name, attribute FROM history ORDER BY sequenceNo",
    "history_songs": "SELECT history_id, content_id, NULL FROM history_content ORDER BY history_id, sequenceNo",
    "playlist_kinds": (0,),
}


def _read(cur: Any, sql: dict[str, Any]) -> MasterLibrary:
    library = MasterLibrary()
    cur.execute(sql["tracks"])
    for track_id, folder_path, title, artist, bpm, length in cur.fetchall():
        if not folder_path:
            continue
        library.tracks[str(track_id)] = MasterTrack(
            id=str(track_id),
            path=str(folder_path),
            title=title or "",
            artist=artist or "",
            bpm=bpm / 100 if bpm else None,  # stored in hundredths
            duration=float(length) if length else None,
        )

    cur.execute(sql["playlists"])
    rows = [(str(i), name or "", attribute, str(parent)) for i, name, attribute, parent in cur.fetchall()]
    names = {i: name for i, name, _a, _p in rows}
    parents = {i: parent for i, _n, _a, parent in rows}
    songs = _songs(cur, sql["playlist_songs"])
    for playlist_id, name, attribute, _parent in rows:
        if attribute not in sql["playlist_kinds"]:  # folders, smart playlists
            continue
        full = name
        parent, seen = parents.get(playlist_id), {playlist_id}
        while parent in names and parent not in seen:
            seen.add(parent)
            full = f"{names[parent]} / {full}"
            parent = parents.get(parent)
        library.playlists[full] = [library.tracks[t].path for t, _at in songs.get(playlist_id, []) if t in library.tracks]

    cur.execute(sql["histories"])
    history_rows = cur.fetchall()
    history_songs = _songs(cur, sql["history_songs"])
    for history_id, name, attribute in history_rows:
        entries = history_songs.get(str(history_id), [])
        if attribute == _FOLDER or not entries:
            continue
        library.histories.append(MasterHistory(name or "", [(t, at) for t, at in entries if t in library.tracks]))
    return library


def _songs(cur: Any, query: str) -> dict[str, list[tuple[str, datetime | None]]]:
    cur.execute(query)
    found: dict[str, list[tuple[str, datetime | None]]] = {}
    for owner_id, content_id, created in cur.fetchall():
        found.setdefault(str(owner_id), []).append((str(content_id), parse_time(created)))
    return found


def parse_time(text: object) -> datetime | None:
    """rekordbox's ``2026-01-17 20:41:30.485 +00:00``, with or without the
    milliseconds (UTC when no offset is written)."""
    if not isinstance(text, str):
        return text if isinstance(text, datetime) else None
    try:
        found = datetime.fromisoformat(" ".join(text.split()).replace(" +", "+").replace(" -", "-"))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


__all__ = [
    "MASTER_DB",
    "ONELIBRARY_DB",
    "MasterDbError",
    "MasterDbUnavailable",
    "MasterHistory",
    "MasterLibrary",
    "MasterTrack",
    "available",
    "default_master_db",
    "is_master_db",
    "is_onelibrary",
    "parse_time",
    "read_library",
]
