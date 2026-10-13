"""Tests for the edit panel's MIDI Learn (issue #220)."""
from __future__ import annotations

from PySide6.QtGui import QUndoStack

from djmidi.gui.edit_panel import EditPanel
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.midi_io import MidiEvent
from djmidi.model import Control, MappingElement, MidiConfig, UserIO


def _press(channel: str = "5", data1: str = "40", event_type: str = "Note On", data2: str = "127") -> MidiEvent:
    return MidiEvent(direction="in", channel=channel, event_type=event_type, data1=data1, data2=data2, timestamp=0.0)


def _control(channel: str = "1", control: str = "10", tag: str = "play") -> Control:
    return Control(channel, "Note On", control, [UserIO("click", [MappingElement(tag=tag, deck_id="1", slot_id="0")])])


def _panel(config: MidiConfig, listening: bool = True) -> tuple[EditPanel, QUndoStack, list[object]]:
    stack = QUndoStack()
    applied: list[object] = []
    panel = EditPanel(
        stack,
        applied.append,
        lambda: applied.append("group"),
        config_provider=lambda: config,
        ensure_listening=lambda: listening,
    )
    return panel, stack, applied


def _trigger(control: Control) -> tuple[str, str, str]:
    return control.channel, control.event_type, control.control


def test_learn_reassigns_a_control_as_one_undo_step():
    control = _control()
    panel, stack, applied = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    assert panel.start_learn()
    assert panel.is_learning
    assert panel.feed_learn_event(_press())
    assert not panel.is_learning
    assert _trigger(control) == ("5", "Note On", "40")
    assert stack.count() == 1
    assert control in applied
    stack.undo()
    assert _trigger(control) == ("1", "Note On", "10")
    stack.redo()
    assert _trigger(control) == ("5", "Note On", "40")


def test_release_does_not_end_learning():
    control = _control()
    panel, stack, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    panel.start_learn()
    assert not panel.feed_learn_event(_press(event_type="Note Off", data2="0"))
    assert panel.is_learning
    assert stack.count() == 0


def test_events_are_ignored_when_not_learning():
    control = _control()
    panel, stack, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    assert not panel.feed_learn_event(_press())
    assert stack.count() == 0


def test_no_input_open_does_not_start():
    control = _control()
    panel, _, _ = _panel(MidiConfig(controls=[control]), listening=False)
    panel.set_node(control)
    assert not panel.start_learn()
    assert not panel.is_learning
    assert "No MIDI input" in panel._learn_status.text()


def test_cancel_and_timeout_stop_learning():
    control = _control()
    panel, stack, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    panel.start_learn()
    panel._on_learn_clicked()  # the button doubles as Cancel
    assert not panel.is_learning
    assert panel._learn_button.text() == "Learn"
    panel.start_learn()
    panel._learn_timer.timeout.emit()
    assert not panel.is_learning
    assert "timed out" in panel._learn_status.text()
    assert not panel.feed_learn_event(_press())
    assert stack.count() == 0


def test_selecting_another_node_cancels_learning():
    control, other = _control(), _control("2", "11")
    panel, _, _ = _panel(MidiConfig(controls=[control, other]))
    panel.set_node(control)
    panel.start_learn()
    panel.set_node(other)
    assert not panel.is_learning


def test_conflict_asks_and_refusal_keeps_the_trigger():
    control, clash = _control(), _control("5", "40", "cue")
    panel, stack, _ = _panel(MidiConfig(controls=[control, clash]))
    asked: list[list[str]] = []
    panel.confirm_conflict = lambda trigger, lines: asked.append(lines) or False
    panel.set_node(control)
    panel.start_learn()
    assert panel.feed_learn_event(_press())
    assert asked == [["cue deck 1 [click]"]]
    assert _trigger(control) == ("1", "Note On", "10")
    assert stack.count() == 0
    assert "already used" in panel._learn_status.text()


def test_conflict_accepted_reassigns():
    control, clash = _control(), _control("5", "40", "cue")
    panel, stack, _ = _panel(MidiConfig(controls=[control, clash]))
    panel.confirm_conflict = lambda trigger, lines: True
    panel.set_node(control)
    panel.start_learn()
    panel.feed_learn_event(_press())
    assert _trigger(control) == ("5", "Note On", "40")
    assert stack.count() == 1


def test_same_trigger_is_a_no_op():
    control = _control("5", "40")
    panel, stack, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    panel.start_learn()
    assert panel.feed_learn_event(_press())
    assert stack.count() == 0
    assert "Already on" in panel._learn_status.text()


def test_group_learn_moves_every_duplicate_and_the_group():
    duplicates = [_control() for _ in range(10)]
    config = MidiConfig(controls=duplicates)
    (group,) = build_mapping_groups(config)
    panel, stack, applied = _panel(config)
    panel.set_node(group)
    panel.start_learn()
    panel.feed_learn_event(_press("6", "7", "Control Change", "0"))
    assert all(_trigger(c) == ("6", "Control Change", "7") for c in duplicates)
    assert (group.channel, group.event_type, group.control_no) == ("6", "Control Change", "7")
    assert "group" in applied
    assert stack.count() == 1
    stack.undo()
    assert all(_trigger(c) == ("1", "Note On", "10") for c in duplicates)
    assert (group.channel, group.event_type, group.control_no) == ("1", "Note On", "10")


def test_mapping_element_learn_moves_its_parent_control():
    control = _control()
    mapping = control.userios[0].mappings[0]
    panel, stack, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(mapping)
    panel.start_learn()
    panel.feed_learn_event(_press())
    assert _trigger(control) == ("5", "Note On", "40")
    assert stack.count() == 1


def test_mapping_without_known_parent_has_no_learn_row():
    orphan = MappingElement(tag="play")
    panel, _, _ = _panel(MidiConfig())
    panel.set_node(orphan)
    assert not panel.start_learn()


def test_learn_message_survives_the_refresh_of_the_same_node():
    control = _control()
    panel, _, _ = _panel(MidiConfig(controls=[control]))
    panel.set_node(control)
    panel.start_learn()
    panel.feed_learn_event(_press())
    panel.set_node(control)  # what MainWindow's deferred refresh does
    assert "Learned ch5 Note On #40" in panel._learn_status.text()
    panel.set_node(None)
    panel.set_node(control)
    assert panel._learn_status.text() == ""


def test_main_window_routes_live_presses_to_learn():
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from djmidi.gui.main_window import MainWindow
    from djmidi.parser import parse_file

    window = MainWindow()
    window.config = parse_file(Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml")
    window._load_tree()
    QApplication.processEvents()
    group = build_mapping_groups(window.config)[0]
    window.edit_panel.set_node(group)
    window.edit_panel._ensure_listening = lambda: True
    window.edit_panel.confirm_conflict = lambda *_: True
    assert window.edit_panel.start_learn()
    window._on_live_midi_event(_press("16", "127", "Control Change", "64"))
    QApplication.processEvents()
    assert not window.edit_panel.is_learning
    assert all(_trigger(c) == ("16", "Control Change", "127") for c, _, _ in group.members)
    window.undo_stack.undo()
    QApplication.processEvents()
    assert all(c.channel != "16" for c, _, _ in group.members)
    window.close()
