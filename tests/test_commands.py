"""Tests for all QUndoCommand subclasses in gui/commands.py."""
from __future__ import annotations

from PySide6.QtGui import QUndoStack

from djmidi.gui.commands import (
    AddAliasCommand,
    AddGroupAliasCommand,
    RemoveAliasCommand,
    RemoveGroupAliasCommand,
    SetAttrCommand,
    SetGroupAttrCommand,
)
from djmidi.model import Alias, MappingElement, Translation

# ─── helpers ──────────────────────────────────────────────────────────────────

def _stack() -> QUndoStack:
    return QUndoStack()


def _translation(action_on: str = "press", behaviour: str = "toggle") -> Translation:
    return Translation(action_on=action_on, behaviour=behaviour)


def _mapping(tag: str = "codfather_st") -> MappingElement:
    return MappingElement(tag=tag, deck_id="1", slot_id="0")


# ─── SetAttrCommand ───────────────────────────────────────────────────────────

def test_set_attr_command_redo_applies_new_value():
    applied: list[object] = []
    target = _mapping()
    stack = _stack()
    cmd = SetAttrCommand(target, "deck_id", "1", "2", target, applied.append)
    stack.push(cmd)
    assert target.deck_id == "2"
    assert len(applied) == 1


def test_set_attr_command_undo_restores_old_value():
    applied: list[object] = []
    target = _mapping()
    stack = _stack()
    cmd = SetAttrCommand(target, "deck_id", "1", "2", target, applied.append)
    stack.push(cmd)
    stack.undo()
    assert target.deck_id == "1"
    assert len(applied) == 2


def test_set_attr_command_custom_label():
    cmd = SetAttrCommand(object(), "x", "a", "b", object(), lambda _: None, label="My label")
    assert cmd.text() == "My label"


def test_set_attr_command_default_label_contains_attr_name():
    cmd = SetAttrCommand(object(), "deck_id", "1", "2", object(), lambda _: None)
    assert "deck_id" in cmd.text()


# ─── AddAliasCommand ──────────────────────────────────────────────────────────

def test_add_alias_command_redo_appends_alias():
    applied: list[object] = []
    translation = _translation()
    alias = Alias(name="on", value="127")
    stack = _stack()
    mapping = _mapping()
    stack.push(AddAliasCommand(translation, alias, mapping, applied.append))
    assert alias in translation.aliases


def test_add_alias_command_undo_removes_alias():
    applied: list[object] = []
    translation = _translation()
    alias = Alias(name="on", value="127")
    stack = _stack()
    mapping = _mapping()
    stack.push(AddAliasCommand(translation, alias, mapping, applied.append))
    stack.undo()
    assert alias not in translation.aliases


# ─── RemoveAliasCommand ───────────────────────────────────────────────────────

def test_remove_alias_command_redo_removes_by_index():
    applied: list[object] = []
    alias = Alias(name="on", value="127")
    translation = Translation(aliases=[alias])
    stack = _stack()
    mapping = _mapping()
    stack.push(RemoveAliasCommand(translation, 0, mapping, applied.append))
    assert alias not in translation.aliases


def test_remove_alias_command_undo_reinserts_at_index():
    applied: list[object] = []
    alias = Alias(name="on", value="127")
    translation = Translation(aliases=[alias])
    stack = _stack()
    mapping = _mapping()
    stack.push(RemoveAliasCommand(translation, 0, mapping, applied.append))
    stack.undo()
    assert translation.aliases[0] is alias


# ─── SetGroupAttrCommand ──────────────────────────────────────────────────────

def test_set_group_attr_command_redo_applies_to_all():
    called: list[None] = []
    m1 = _mapping()
    m2 = _mapping()
    stack = _stack()
    stack.push(SetGroupAttrCommand([m1, m2], "deck_id", ["1", "1"], "3", lambda: called.append(None)))
    assert m1.deck_id == "3"
    assert m2.deck_id == "3"
    assert len(called) == 1


def test_set_group_attr_command_undo_restores_individual_old_values():
    called: list[None] = []
    m1 = _mapping()
    m2 = _mapping()
    m1.deck_id = "1"
    m2.deck_id = "2"
    stack = _stack()
    stack.push(SetGroupAttrCommand([m1, m2], "deck_id", ["1", "2"], "5", lambda: called.append(None)))
    stack.undo()
    assert m1.deck_id == "1"
    assert m2.deck_id == "2"


# ─── AddGroupAliasCommand ─────────────────────────────────────────────────────

def test_add_group_alias_command_redo_appends_to_all_translations():
    called: list[None] = []
    t1 = _translation()
    t2 = _translation()
    a1 = Alias(name="on", value="127")
    a2 = Alias(name="on", value="127")
    stack = _stack()
    stack.push(AddGroupAliasCommand([t1, t2], [a1, a2], lambda: called.append(None)))
    assert a1 in t1.aliases
    assert a2 in t2.aliases


def test_add_group_alias_command_undo_removes_from_all():
    called: list[None] = []
    t1 = _translation()
    t2 = _translation()
    a1 = Alias(name="on", value="127")
    a2 = Alias(name="on", value="127")
    stack = _stack()
    stack.push(AddGroupAliasCommand([t1, t2], [a1, a2], lambda: called.append(None)))
    stack.undo()
    assert a1 not in t1.aliases
    assert a2 not in t2.aliases


# ─── RemoveGroupAliasCommand ──────────────────────────────────────────────────

def test_remove_group_alias_command_redo_deletes_by_index():
    called: list[None] = []
    alias_a = Alias(name="on", value="127")
    alias_b = Alias(name="on", value="127")
    t1 = Translation(aliases=[alias_a])
    t2 = Translation(aliases=[alias_b])
    stack = _stack()
    stack.push(RemoveGroupAliasCommand([t1, t2], 0, lambda: called.append(None)))
    assert not t1.aliases
    assert not t2.aliases


def test_remove_group_alias_command_undo_reinserts_at_index():
    called: list[None] = []
    alias_a = Alias(name="on", value="127")
    alias_b = Alias(name="on", value="127")
    t1 = Translation(aliases=[alias_a])
    t2 = Translation(aliases=[alias_b])
    stack = _stack()
    stack.push(RemoveGroupAliasCommand([t1, t2], 0, lambda: called.append(None)))
    stack.undo()
    assert t1.aliases[0] is alias_a
    assert t2.aliases[0] is alias_b



def test_write_tracks_metadata_command_batches_and_skips_failures():
    from PySide6.QtGui import QUndoStack

    from djmidi.gui.commands import WriteTracksMetadataCommand

    files = {"a": {"genre": "Old"}, "b": {"genre": None}, "bad": {"genre": "X"}}
    applied = []

    def writer(path, **fields):
        if path == "bad":
            raise OSError("read-only")
        files[path].update(fields)

    changes = {path: ({"genre": files[path]["genre"]}, {"genre": "New"}) for path in files}
    stack = QUndoStack()
    command = WriteTracksMetadataCommand(changes, applied.append, writer=writer)
    stack.push(command)
    assert files["a"]["genre"] == files["b"]["genre"] == "New"
    assert command.written == ["a", "b"] and "bad" in command.failures
    assert stack.count() == 1 and applied == [["a", "b"]]
    stack.undo()
    assert files["a"]["genre"] == "Old" and files["b"]["genre"] is None
    assert applied[-1] == ["a", "b"]


def test_write_tracks_metadata_command_dropped_when_nothing_written():
    from PySide6.QtGui import QUndoStack

    from djmidi.gui.commands import WriteTracksMetadataCommand

    def writer(path, **fields):
        raise OSError("nope")

    stack = QUndoStack()
    command = WriteTracksMetadataCommand({"x": ({}, {"genre": "G"})}, lambda paths: None, writer=writer)
    stack.push(command)
    assert stack.count() == 0 and command.failures == {"x": "nope"}


def test_write_tracks_metadata_command_reports_progress_and_can_be_cancelled():
    """A bulk tag write reports each file to a fresh progress callback per
    redo/undo pass; stopping keeps what's written, and undo restores exactly that."""
    from PySide6.QtGui import QUndoStack

    from djmidi.gui.commands import WriteTracksMetadataCommand

    files = {name: {"genre": "Old"} for name in ("a", "b", "c")}
    passes = []

    def writer(path, **fields):
        files[path].update(fields)

    def factory(label, total):
        calls = []
        passes.append((label, total, calls))

        def report(done, total):
            calls.append(done)
            return done < 2  # stop before the third file

        return report

    changes = {path: ({"genre": "Old"}, {"genre": "New"}) for path in files}
    stack = QUndoStack()
    command = WriteTracksMetadataCommand(changes, lambda paths: None, writer=writer, progress_factory=factory)
    stack.push(command)
    assert command.cancelled is True and command.written == ["a", "b"]
    assert [files[p]["genre"] for p in ("a", "b", "c")] == ["New", "New", "Old"]
    assert passes[0][:2] == ("Writing tags…", 3) and passes[0][2] == [0, 1, 2, 3]
    stack.undo()
    assert passes[1][:2] == ("Restoring tags…", 2)
    assert all(f["genre"] == "Old" for f in files.values())
