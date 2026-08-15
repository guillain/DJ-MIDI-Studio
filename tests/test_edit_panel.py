"""Tests for EditPanel – exercising set_node for each supported model type."""
from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QLabel

from djmidi.gui.edit_panel import EditPanel
from djmidi.gui.mapping_group import MappingGroup
from djmidi.model import Alias, Control, MappingElement, Translation, UserIO

# ─── helpers ──────────────────────────────────────────────────────────────────

def _panel() -> tuple[EditPanel, list[object]]:
    applied: list[object] = []
    panel = EditPanel(QUndoStack(), applied.append)
    return panel, applied


def _control() -> Control:
    return Control(channel="8", event_type="Note On", control="64")


def _userio() -> UserIO:
    return UserIO(event="click")


def _mapping(with_translation: bool = True) -> MappingElement:
    m = MappingElement(tag="codfather_st", deck_id="1", slot_id="0")
    if with_translation:
        alias = Alias(name="on", value="127")
        m.translations.append(Translation(action_on="press", behaviour="toggle", aliases=[alias]))
    return m


def _group_with_member() -> MappingGroup:
    control = _control()
    userio = _userio()
    mapping = _mapping()
    group = MappingGroup(
        deck_id="1",
        slot_id="0",
        tag="codfather_st",
        event="click",
        channel="8",
        control_no="64",
        event_type="Note On",
        members=[(control, userio, mapping)],
    )
    return group


# ─── set_node ─────────────────────────────────────────────────────────────────

def test_set_node_none_clears_body():
    panel, _ = _panel()
    panel.set_node(_control())
    panel.set_node(None)
    assert panel.current_node is None


def test_set_node_control_shows_body():
    panel, _ = _panel()
    panel.set_node(_control())
    assert panel.current_node is not None
    assert panel._body is not None


def test_set_node_userio_shows_body():
    panel, _ = _panel()
    panel.set_node(_userio())
    assert panel._body is not None


def test_set_node_mapping_element_shows_body():
    panel, _ = _panel()
    panel.set_node(_mapping())
    assert panel._body is not None


def test_set_node_mapping_without_translation_shows_body():
    panel, _ = _panel()
    panel.set_node(_mapping(with_translation=False))
    assert panel._body is not None


def test_set_node_group_shows_body():
    panel, _ = _panel()
    panel.set_node(_group_with_member())
    assert panel._body is not None


def test_set_node_unknown_type_skips_body():
    panel, _ = _panel()
    panel.set_node(42)
    assert panel._body is None


def test_set_node_replaces_previous_body():
    panel, _ = _panel()
    panel.set_node(_control())
    first_body = panel._body
    panel.set_node(_userio())
    assert panel._body is not first_body


# ─── _push (via redo/undo through undo_stack) ────────────────────────────────

def test_push_same_value_does_not_push_command():
    panel, applied = _panel()
    target = _control()
    panel._push(target, "channel", "8", "8", target)
    assert not applied  # no-op


def test_push_different_value_applies_change():
    panel, applied = _panel()
    target = _control()
    panel._push(target, "channel", "8", "9", target)
    assert target.channel == "9"
    assert applied


# ─── physical control box ─────────────────────────────────────────────────────

def test_physical_control_box_known_trigger_shows_name():
    panel, _ = _panel()
    # ch8 Note On note 64 is a known DDJ-XP2 trigger
    box = panel._build_physical_control_box("8", "Note On", "64")
    assert box is not None
    label = box.findChild(QLabel)
    assert label is not None
    assert label.minimumHeight() >= label.fontMetrics().lineSpacing() * 8


def test_physical_control_box_unknown_trigger_shows_placeholder():
    panel, _ = _panel()
    box = panel._build_physical_control_box("99", "Note On", "99")
    assert box is not None


# ─── group form round-trip ────────────────────────────────────────────────────

def test_build_group_form_does_not_crash():
    panel, _ = _panel()
    group = _group_with_member()
    panel.set_node(group)
    assert panel.current_node is group
