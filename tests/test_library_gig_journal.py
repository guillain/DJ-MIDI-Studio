"""The gig journal: free-text notes per session, browsable alongside play
history (issue #405)."""

from __future__ import annotations

from djmidi.library import gig_journal
from djmidi.library.db import LibraryDB


def _clock():
    value = {"t": 1000.0}

    def tick() -> float:
        value["t"] += 1.0
        return value["t"]

    return tick


def test_add_entry_rejects_a_blank_note():
    db = LibraryDB()
    assert gig_journal.add_entry(db, "   ") is None
    assert gig_journal.list_entries(db) == []


def test_add_entry_strips_whitespace_and_records_the_time():
    db = LibraryDB()
    clock = _clock()
    entry = gig_journal.add_entry(db, "  Great crowd at the warehouse set  ", clock=clock)
    assert entry is not None
    assert entry.note == "Great crowd at the warehouse set"
    assert entry.created_at == 1001.0


def test_list_entries_is_newest_first():
    db = LibraryDB()
    clock = _clock()
    first = gig_journal.add_entry(db, "First gig", clock=clock)
    second = gig_journal.add_entry(db, "Second gig", clock=clock)
    assert [entry.id for entry in gig_journal.list_entries(db)] == [second.id, first.id]


def test_update_entry_replaces_the_note_and_rejects_blank():
    db = LibraryDB()
    entry = gig_journal.add_entry(db, "Draft note", clock=_clock())
    assert gig_journal.update_entry(db, entry.id, "Final note")
    assert gig_journal.list_entries(db)[0].note == "Final note"
    assert not gig_journal.update_entry(db, entry.id, "   ")
    assert gig_journal.list_entries(db)[0].note == "Final note"  # unchanged


def test_delete_entry_removes_it():
    db = LibraryDB()
    entry = gig_journal.add_entry(db, "To be deleted", clock=_clock())
    gig_journal.delete_entry(db, entry.id)
    assert gig_journal.list_entries(db) == []


def test_title_is_the_first_line():
    db = LibraryDB()
    entry = gig_journal.add_entry(db, "Short title\nLonger body text here.", clock=_clock())
    assert entry.title == "Short title"


def test_format_entry_line_includes_the_local_timestamp_and_title():
    entry = gig_journal.GigJournalEntry(id=1, created_at=0.0, note="Opening set went long")
    line = gig_journal.format_entry_line(entry)
    assert "Opening set went long" in line
    assert line.split(" — ")[0] == entry.local_time().strftime("%Y-%m-%d %H:%M")


def test_format_entry_line_without_a_note_is_just_the_timestamp():
    entry = gig_journal.GigJournalEntry(id=1, created_at=0.0, note="")
    assert gig_journal.format_entry_line(entry) == entry.local_time().strftime("%Y-%m-%d %H:%M")
