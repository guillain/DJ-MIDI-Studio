"""Tests for all QUndoCommand subclasses in gui/commands.py."""
from __future__ import annotations

from PySide6.QtGui import QUndoStack

from seratomidiconf.gui.commands import (
    AddAliasCommand,
    AddGroupAliasCommand,
    RemoveAliasCommand,
    RemoveGroupAliasCommand,
    SetAttrCommand,
    SetGroupAttrCommand,
)
from seratomidiconf.model import Alias, MappingElement, Translation

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

