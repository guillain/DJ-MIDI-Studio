from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

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
"""


@dataclass
class LibraryRoot:
    id: int
    path: str


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
