"""Gig journal (issue #405): a free-text note per gig/session, browsable
alongside the play history this app already reads from Serato/Traktor, for
post-gig review ("what worked, what didn't"). Lives only in this app's own
index -- never tied to a track, never written into a DJ software's files.
"""

from __future__ import annotations

import time as _time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .db import LibraryDB


@dataclass(frozen=True)
class GigJournalEntry:
    id: int
    created_at: float  # unix seconds, UTC
    note: str

    @property
    def title(self) -> str:
        """The entry's first line, for a one-line list row."""
        first = self.note.splitlines()[0] if self.note else ""
        return first

    def local_time(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=UTC).astimezone()


def format_entry_line(entry: GigJournalEntry) -> str:
    """``"2026-11-04 23:12 — first line of the note"``, for the list row."""
    stamp = entry.local_time().strftime("%Y-%m-%d %H:%M")
    return f"{stamp} — {entry.title}" if entry.title else stamp


def add_entry(db: LibraryDB, note: str, clock: Callable[[], float] = _time.time) -> GigJournalEntry | None:
    """Adds a journal entry; `None` (nothing written) for a blank note."""
    text = note.strip()
    if not text:
        return None
    created_at = clock()
    entry_id = db.add_journal_entry(text, created_at)
    return GigJournalEntry(entry_id, created_at, text)


def update_entry(db: LibraryDB, entry_id: int, note: str) -> bool:
    """Replaces an entry's note; `False` (nothing written) for a blank one."""
    text = note.strip()
    if not text:
        return False
    db.update_journal_entry(entry_id, text)
    return True


def delete_entry(db: LibraryDB, entry_id: int) -> None:
    db.delete_journal_entry(entry_id)


def list_entries(db: LibraryDB) -> list[GigJournalEntry]:
    """Every entry, newest first."""
    return [GigJournalEntry(*row) for row in db.list_journal_entries()]


__all__ = [
    "GigJournalEntry",
    "add_entry",
    "delete_entry",
    "format_entry_line",
    "list_entries",
    "update_entry",
]
