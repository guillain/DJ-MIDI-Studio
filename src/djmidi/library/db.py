from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
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

-- Audio-analysis estimates for tracks missing a BPM or key tag (issue
-- #224). Suggestions only: nothing here reaches a file until the user
-- applies it through the undoable tag write. Keyed to the file's mtime so
-- a file changed since (e.g. tagged in Serato) drops its stale estimate;
-- a row with both values NULL records an attempt that found nothing, so
-- the job doesn't retry that file every run.
CREATE TABLE IF NOT EXISTS analysis_suggestions (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    mtime REAL NOT NULL,
    bpm REAL,
    key TEXT
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

-- Small per-library UI choices remembered between sessions (issue #211:
-- the last "Auto: mix path" options), as JSON-encoded values. Living in
-- the library index keeps them out of preferences.json, and the test
-- suite's `:memory:` index keeps tests away from the real values.
CREATE TABLE IF NOT EXISTS library_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Persistent log of risky writes to real files (issue #261): bulk tag
-- writes, copies moved to the Trash, and later cover art / renames. One
-- `change_log` row per operation, one `change_items` row per file with its
-- before/after state as JSON, so the Change history window can inspect and
-- revert an entry after a restart (the QUndoStack only lives a session).
CREATE TABLE IF NOT EXISTS change_log (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    reverted_at REAL
);

CREATE TABLE IF NOT EXISTS change_items (
    change_id INTEGER NOT NULL REFERENCES change_log(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    path TEXT NOT NULL,
    before TEXT NOT NULL DEFAULT '{}',
    after TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (change_id, position)
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
class ChangeItem:
    path: str
    before: dict[str, object]
    after: dict[str, object]


@dataclass
class ChangeRecord:
    id: int
    created_at: float
    kind: str
    summary: str
    reverted_at: float | None = None
    items: list[ChangeItem] = field(default_factory=list)
    item_count: int = 0


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

    def mark_paths_missing(self, paths: Iterable[str]) -> int:
        """Flag the tracks at `paths` missing (issue #208: copies moved to
        the Trash). Like a scan, never deletes a row. Returns how many rows
        changed."""
        changed = 0
        with self._conn:
            for path in paths:
                cur = self._conn.execute("UPDATE tracks SET missing = 1 WHERE path = ? AND missing = 0", (str(path),))
                changed += cur.rowcount
        return changed

    def playlists_containing(self, paths: Iterable[str]) -> dict[str, list[str]]:
        """Name of every playlist of this app listing each of `paths`
        (a path no playlist lists is left out)."""
        result: dict[str, list[str]] = {}
        for path in paths:
            rows = self._conn.execute(
                """
                SELECT DISTINCT p.name FROM playlist_tracks pt JOIN playlists p ON p.id = pt.playlist_id
                WHERE pt.path = ? ORDER BY p.name COLLATE NOCASE
                """,
                (str(path),),
            ).fetchall()
            if rows:
                result[str(path)] = [r[0] for r in rows]
        return result

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

    def relink_tracks(self, links: Iterable[tuple[int, str, int, int, float]]) -> int:
        """Point missing tracks at the files they moved to (issue #190).

        Each link is ``(missing_track_id, new_path, root_id, size, mtime)``.
        This app's index only: playlist entries naming the old path follow
        the new one, and the old row's cached tags move over when the new
        file has none yet. If `new_path` is already indexed the stale row is
        dropped; otherwise the missing row itself takes the new path. All
        links commit together or not at all. Returns how many were applied
        (a link whose row is gone or no longer missing is skipped)."""
        applied = 0
        with self._conn:
            for missing_id, new_path, root_id, size, mtime in links:
                row = self._conn.execute(
                    "SELECT path FROM tracks WHERE id = ? AND missing = 1", (missing_id,)
                ).fetchone()
                if row is None:
                    continue
                old_path, new_path = row[0], str(new_path)
                target = self._conn.execute("SELECT id FROM tracks WHERE path = ?", (new_path,)).fetchone()
                if target is None:
                    self._conn.execute(
                        "UPDATE tracks SET path = ?, root_id = ?, size = ?, mtime = ?, missing = 0 WHERE id = ?",
                        (new_path, root_id, size, mtime, missing_id),
                    )
                else:
                    has_cache = self._conn.execute(
                        "SELECT 1 FROM track_metadata WHERE track_id = ?", (target[0],)
                    ).fetchone()
                    if has_cache is None:
                        self._conn.execute(
                            "UPDATE track_metadata SET track_id = ? WHERE track_id = ?", (target[0], missing_id)
                        )
                    self._conn.execute("DELETE FROM track_metadata WHERE track_id = ?", (missing_id,))
                    self._conn.execute("DELETE FROM tracks WHERE id = ?", (missing_id,))
                self._conn.execute("UPDATE playlist_tracks SET path = ? WHERE path = ?", (new_path, old_path))
                applied += 1
        return applied

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

    # --- analysis suggestions (issue #224) ------------------------------

    def tracks_needing_analysis(self) -> list[TrackRecord]:
        """Present tracks whose up-to-date cached tags lack a BPM or a key
        and that haven't been analysed since the file last changed."""
        rows = self._conn.execute(
            """
            SELECT t.id, t.root_id, t.path, t.size, t.mtime, t.missing
            FROM tracks t
            JOIN track_metadata m ON m.track_id = t.id AND m.mtime = t.mtime
            LEFT JOIN analysis_suggestions s ON s.track_id = t.id AND s.mtime = t.mtime
            WHERE t.missing = 0 AND s.track_id IS NULL
              AND (m.bpm IS NULL OR m.key IS NULL OR TRIM(m.key) = '')
            ORDER BY t.path
            """
        ).fetchall()
        return [
            TrackRecord(id=r[0], root_id=r[1], path=r[2], size=r[3], mtime=r[4], missing=bool(r[5])) for r in rows
        ]

    def set_analysis_suggestion(self, track_id: int, mtime: float, bpm: float | None, key: str | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO analysis_suggestions (track_id, mtime, bpm, key) VALUES (?, ?, ?, ?)",
            (track_id, mtime, bpm, key),
        )

    def carry_analysis_suggestion(self, track_id: int, old_mtime: float, new_mtime: float) -> None:
        """Keep a track's estimate current across a tag-only write this app
        made itself (the file's mtime moved, its audio didn't)."""
        self._conn.execute(
            "UPDATE analysis_suggestions SET mtime = ? WHERE track_id = ? AND mtime = ?",
            (new_mtime, track_id, old_mtime),
        )

    def analysis_suggestions(self) -> dict[int, tuple[float | None, str | None]]:
        """Track id -> (suggested BPM, suggested key), current estimates only
        (a file changed since its analysis is left out)."""
        rows = self._conn.execute(
            """
            SELECT s.track_id, s.bpm, s.key FROM analysis_suggestions s
            JOIN tracks t ON t.id = s.track_id AND t.mtime = s.mtime
            WHERE s.bpm IS NOT NULL OR s.key IS NOT NULL
            """
        ).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

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

    def get_setting(self, key: str, default: object = None) -> object:
        """A remembered UI choice, or `default` when unset or unreadable."""
        row = self._conn.execute("SELECT value FROM library_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def set_setting(self, key: str, value: object) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO library_settings (key, value) VALUES (?, ?)", (key, json.dumps(value))
        )
        self._conn.commit()

    # --- change log (issue #261) -----------------------------------------

    def add_change(self, kind: str, summary: str, items: Iterable[ChangeItem], created_at: float) -> int:
        """Record one operation and its per-file before/after states."""
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO change_log (created_at, kind, summary) VALUES (?, ?, ?)", (created_at, kind, summary)
            )
            change_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO change_items (change_id, position, path, before, after) VALUES (?, ?, ?, ?, ?)",
                [
                    (change_id, position, item.path, json.dumps(item.before), json.dumps(item.after))
                    for position, item in enumerate(items)
                ],
            )
        return change_id

    def list_changes(self, limit: int | None = None) -> list[ChangeRecord]:
        """Logged operations, newest first, without their items (see
        `get_change`); `item_count` says how many files each touched."""
        query = """
            SELECT c.id, c.created_at, c.kind, c.summary, c.reverted_at,
                   (SELECT COUNT(*) FROM change_items i WHERE i.change_id = c.id)
            FROM change_log c ORDER BY c.created_at DESC, c.id DESC
        """
        params: tuple[object, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        return [
            ChangeRecord(id=r[0], created_at=r[1], kind=r[2], summary=r[3], reverted_at=r[4], item_count=r[5])
            for r in self._conn.execute(query, params)
        ]

    def get_change(self, change_id: int) -> ChangeRecord | None:
        row = self._conn.execute(
            "SELECT id, created_at, kind, summary, reverted_at FROM change_log WHERE id = ?", (change_id,)
        ).fetchone()
        if row is None:
            return None
        items = [
            ChangeItem(path=r[0], before=_json_dict(r[1]), after=_json_dict(r[2]))
            for r in self._conn.execute(
                "SELECT path, before, after FROM change_items WHERE change_id = ? ORDER BY position", (change_id,)
            )
        ]
        return ChangeRecord(
            id=row[0], created_at=row[1], kind=row[2], summary=row[3], reverted_at=row[4], items=items,
            item_count=len(items),
        )

    def mark_change_reverted(self, change_id: int, reverted_at: float) -> None:
        self._conn.execute("UPDATE change_log SET reverted_at = ? WHERE id = ?", (reverted_at, change_id))
        self._conn.commit()

    def prune_changes(self, keep: int) -> int:
        """Drop all but the `keep` newest operations. Returns how many went."""
        with self._conn:
            cur = self._conn.execute(
                """
                DELETE FROM change_log WHERE id NOT IN (
                    SELECT id FROM change_log ORDER BY created_at DESC, id DESC LIMIT ?
                )
                """,
                (keep,),
            )
        return cur.rowcount

    def mark_path_present(self, path: str | Path, size: int, mtime: float) -> bool:
        """Un-flag a track whose file is back (a Trash move reverted). When
        its row is gone (folded into the kept copy by a playlist repoint), it
        is re-added under the indexed root containing it. Returns False when
        no root contains `path`."""
        path_str = str(path)
        root_id = None
        existing = self.get_track_by_path(path_str)
        if existing is not None:
            root_id = existing.root_id
        else:
            for root in self.list_roots():
                if Path(path_str).is_relative_to(root.path):
                    root_id = root.id
                    break
        if root_id is None:
            return False
        self.upsert_track(root_id, path_str, size, mtime)
        self._conn.commit()
        return True


def _json_dict(text: str) -> dict[str, object]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
