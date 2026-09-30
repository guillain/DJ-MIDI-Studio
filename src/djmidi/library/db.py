from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Self

from .metadata import TrackMetadata

_SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES roots(id),
    path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    missing INTEGER NOT NULL DEFAULT 0
);

-- A *cache* of each file's managed tags (issue #132), never the source of
-- truth: the real file is. Re-read whenever the file's mtime moves past
-- the one recorded here, so a tag edited in Serato/Traktor shows up again.
CREATE TABLE IF NOT EXISTS track_metadata (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    mtime REAL NOT NULL,
    title TEXT, artist TEXT, album TEXT, genre TEXT, bpm REAL, key TEXT,
    comment TEXT, rating TEXT, energy TEXT
);

-- This app's own playlists (imported from Serato/Traktor/Rekordbox,
-- generated, or hand-built). Never a live DJ-software playlist file --
-- exporting one writes a new file at a path the user picks.
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (playlist_id, position)
);

-- User edits to the in-memory taxonomy registry (issue #127), replayed on
-- top of the built-in family modules at startup: categories created or
-- changed here, and built-in ones the user deleted/merged away.
CREATE TABLE IF NOT EXISTS user_categories (
    canonical TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS removed_categories (
    canonical TEXT PRIMARY KEY
);
"""

_METADATA_COLUMNS = tuple(f.name for f in fields(TrackMetadata))


def default_library_db_path() -> Path:
    """Where the real app keeps its library index -- beside preferences.json.

    `DJMIDI_LIBRARY_DB` overrides it (the test suite points it at
    ``:memory:`` so constructing a window never touches the real index)."""
    override = os.environ.get("DJMIDI_LIBRARY_DB")
    if override:
        return Path(override)
    from djmidi.plugins.preferences import default_preferences_path

    return default_preferences_path().parent / "library.sqlite3"


@dataclass
class LibraryRoot:
    id: int
    path: str


@dataclass
class PlaylistRecord:
    id: int
    name: str
    source: str
    track_count: int = 0


@dataclass
class StoredCategory:
    family: str
    name: str
    aliases: tuple[str, ...] = ()

    @property
    def canonical(self) -> str:
        return f"{self.family}%%{self.name}"


@dataclass
class TrackRecord:
    id: int
    root_id: int
    path: str
    size: int
    mtime: float
    missing: bool


class LibraryDB:
    """The local, read/write source of truth for the scanned library index.

    Never touches the real audio files themselves -- only their path, size,
    and mtime, so a scan can tell an unchanged file from one that needs
    re-reading without opening it.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def commit(self) -> None:
        self._conn.commit()

    def add_root(self, path: str | Path) -> LibraryRoot:
        path_str = str(path)
        self._conn.execute("INSERT OR IGNORE INTO roots (path) VALUES (?)", (path_str,))
        self._conn.commit()
        row = self._conn.execute("SELECT id FROM roots WHERE path = ?", (path_str,)).fetchone()
        return LibraryRoot(id=row[0], path=path_str)

    def remove_root(self, root_id: int) -> None:
        self._conn.execute("DELETE FROM tracks WHERE root_id = ?", (root_id,))
        self._conn.execute("DELETE FROM roots WHERE id = ?", (root_id,))
        self._conn.commit()

    def list_roots(self) -> list[LibraryRoot]:
        rows = self._conn.execute("SELECT id, path FROM roots ORDER BY path").fetchall()
        return [LibraryRoot(id=r[0], path=r[1]) for r in rows]

    def upsert_track(self, root_id: int, path: str | Path, size: int, mtime: float) -> None:
        self._conn.execute(
            """
            INSERT INTO tracks (root_id, path, size, mtime, missing)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(path) DO UPDATE SET
                size = excluded.size,
                mtime = excluded.mtime,
                missing = 0
            """,
            (root_id, str(path), size, mtime),
        )

    def mark_missing_except(self, root_id: int, seen_paths: Iterable[str]) -> int:
        """Flag every non-missing track under `root_id` not in `seen_paths`.

        Never deletes a row -- a file that moved or was temporarily
        unavailable (e.g. an unmounted external drive) stays in the index as
        `missing` rather than losing its history.
        """
        seen = list(seen_paths)
        params: list[object] = [root_id]
        query = "UPDATE tracks SET missing = 1 WHERE root_id = ? AND missing = 0"
        if seen:
            placeholders = ",".join("?" for _ in seen)
            query += f" AND path NOT IN ({placeholders})"
            params.extend(seen)
        cur = self._conn.execute(query, params)
        self._conn.commit()
        return cur.rowcount

    def list_tracks(self, root_id: int | None = None, include_missing: bool = True) -> list[TrackRecord]:
        query = "SELECT id, root_id, path, size, mtime, missing FROM tracks"
        params: list[object] = []
        clauses = []
        if root_id is not None:
            clauses.append("root_id = ?")
            params.append(root_id)
        if not include_missing:
            clauses.append("missing = 0")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY path"
        rows = self._conn.execute(query, params).fetchall()
        return [
            TrackRecord(id=r[0], root_id=r[1], path=r[2], size=r[3], mtime=r[4], missing=bool(r[5])) for r in rows
        ]

    def get_track_by_path(self, path: str | Path) -> TrackRecord | None:
        row = self._conn.execute(
            "SELECT id, root_id, path, size, mtime, missing FROM tracks WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return TrackRecord(id=row[0], root_id=row[1], path=row[2], size=row[3], mtime=row[4], missing=bool(row[5]))

    # --- metadata cache -------------------------------------------------

    def set_cached_metadata(self, track_id: int, mtime: float, metadata: TrackMetadata) -> None:
        values = [getattr(metadata, name) for name in _METADATA_COLUMNS]
        columns = ", ".join(_METADATA_COLUMNS)
        placeholders = ", ".join("?" for _ in _METADATA_COLUMNS)
        self._conn.execute(
            f"INSERT OR REPLACE INTO track_metadata (track_id, mtime, {columns}) VALUES (?, ?, {placeholders})",
            (track_id, mtime, *values),
        )

    def get_cached_metadata(self, track_id: int) -> tuple[float, TrackMetadata] | None:
        columns = ", ".join(_METADATA_COLUMNS)
        row = self._conn.execute(
            f"SELECT mtime, {columns} FROM track_metadata WHERE track_id = ?", (track_id,)
        ).fetchone()
        if row is None:
            return None
        return row[0], TrackMetadata(**dict(zip(_METADATA_COLUMNS, row[1:], strict=True)))

    def tracks_needing_metadata(self) -> list[TrackRecord]:
        """Present tracks with no cached tags, or whose file changed since."""
        rows = self._conn.execute(
            """
            SELECT t.id, t.root_id, t.path, t.size, t.mtime, t.missing
            FROM tracks t LEFT JOIN track_metadata m ON m.track_id = t.id
            WHERE t.missing = 0 AND (m.track_id IS NULL OR m.mtime != t.mtime)
            ORDER BY t.path
            """
        ).fetchall()
        return [
            TrackRecord(id=r[0], root_id=r[1], path=r[2], size=r[3], mtime=r[4], missing=bool(r[5])) for r in rows
        ]

    def list_tracks_with_metadata(self) -> list[tuple[TrackRecord, TrackMetadata | None]]:
        columns = ", ".join(f"m.{name}" for name in _METADATA_COLUMNS)
        rows = self._conn.execute(
            f"""
            SELECT t.id, t.root_id, t.path, t.size, t.mtime, t.missing, m.track_id, {columns}
            FROM tracks t LEFT JOIN track_metadata m ON m.track_id = t.id
            ORDER BY t.path
            """
        ).fetchall()
        result: list[tuple[TrackRecord, TrackMetadata | None]] = []
        for r in rows:
            record = TrackRecord(id=r[0], root_id=r[1], path=r[2], size=r[3], mtime=r[4], missing=bool(r[5]))
            metadata = None
            if r[6] is not None:
                metadata = TrackMetadata(**dict(zip(_METADATA_COLUMNS, r[7:], strict=True)))
            result.append((record, metadata))
        return result

    # --- playlists --------------------------------------------------------

    def create_playlist(self, name: str, paths: Iterable[str], source: str = "manual") -> int:
        cur = self._conn.execute("INSERT INTO playlists (name, source) VALUES (?, ?)", (name, source))
        playlist_id = int(cur.lastrowid)
        self._write_playlist_paths(playlist_id, paths)
        self._conn.commit()
        return playlist_id

    def set_playlist_paths(self, playlist_id: int, paths: Iterable[str]) -> None:
        self._conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
        self._write_playlist_paths(playlist_id, paths)
        self._conn.commit()

    def _write_playlist_paths(self, playlist_id: int, paths: Iterable[str]) -> None:
        self._conn.executemany(
            "INSERT INTO playlist_tracks (playlist_id, position, path) VALUES (?, ?, ?)",
            [(playlist_id, position, str(path)) for position, path in enumerate(paths)],
        )

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        self._conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))
        self._conn.commit()

    def delete_playlist(self, playlist_id: int) -> None:
        self._conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
        self._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self._conn.commit()

    def list_playlists(self) -> list[PlaylistRecord]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.source, COUNT(pt.path)
            FROM playlists p LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
            GROUP BY p.id ORDER BY p.name COLLATE NOCASE, p.id
            """
        ).fetchall()
        return [PlaylistRecord(id=r[0], name=r[1], source=r[2], track_count=r[3]) for r in rows]

    def playlist_paths(self, playlist_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT path FROM playlist_tracks WHERE playlist_id = ? ORDER BY position", (playlist_id,)
        ).fetchall()
        return [r[0] for r in rows]

    # --- taxonomy overrides ----------------------------------------------

    def save_category(self, category: StoredCategory) -> None:
        self._conn.execute("DELETE FROM removed_categories WHERE canonical = ?", (category.canonical,))
        self._conn.execute(
            "INSERT OR REPLACE INTO user_categories (canonical, family, name, aliases) VALUES (?, ?, ?, ?)",
            (category.canonical, category.family, category.name, json.dumps(sorted(category.aliases))),
        )
        self._conn.commit()

    def remove_category(self, canonical: str) -> None:
        self._conn.execute("DELETE FROM user_categories WHERE canonical = ?", (canonical,))
        self._conn.execute("INSERT OR IGNORE INTO removed_categories (canonical) VALUES (?)", (canonical,))
        self._conn.commit()

    def category_overrides(self) -> tuple[list[StoredCategory], list[str]]:
        saved = [
            StoredCategory(family=r[0], name=r[1], aliases=tuple(json.loads(r[2])))
            for r in self._conn.execute("SELECT family, name, aliases FROM user_categories ORDER BY canonical")
        ]
        removed = [r[0] for r in self._conn.execute("SELECT canonical FROM removed_categories ORDER BY canonical")]
        return saved, removed
