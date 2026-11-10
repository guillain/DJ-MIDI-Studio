"""Editable Serato modifier / SHIFT layers (issue #434)."""

import pytest
from PySide6.QtGui import QUndoStack
from test_serato_cases import SAMPLE

from djmidi import case_edit
from djmidi.case_edit import ConditionSpec, LayerError
from djmidi.exporter import to_xml_string
from djmidi.model import condition_of, iter_bindings
from djmidi.parser import parse_string


def _config():
    return parse_string(SAMPLE)


def _layered(config):
    return config.controls[1]  # the control with two <case>s


def test_known_modifiers_and_operators_come_from_the_file():
    config = _config()
    assert case_edit.known_modifiers(config) == ["modifier_1", "modifier_2", "modifier_3"]
    assert case_edit.known_operators(config) == ["equal"]
    assert case_edit.known_modifiers(None) == [] and case_edit.known_operators(None) == ["equal"]


def test_set_conditions_keeps_other_attributes_and_leaves_the_model_alone():
    config = _config()
    control = _layered(config)
    case = control.cases[1]
    edit = case_edit.set_conditions(
        control, case, [ConditionSpec("modifier_1", "equal", "off"), ConditionSpec("modifier_4", "equal", "on")]
    )
    new = edit.cases[1]
    assert new.conditions[0].attrs == {"deck_set": "Default", "operator": "equal", "cmp_value": "off"}
    assert new.conditions[1].attrs == {"operator": "equal", "cmp_value": "on"}
    assert new.userios is case.userios and new.position == case.position
    assert control.cases[1].conditions[0].attrs["cmp_value"] == "on"  # untouched until applied


@pytest.mark.parametrize(
    "specs",
    [[], [ConditionSpec("bad tag", "equal", "on")], [ConditionSpec("modifier_1", "", "on")], [ConditionSpec("modifier_1", "equal", " ")]],
)
def test_invalid_conditions_are_refused(specs):
    config = _config()
    control = _layered(config)
    with pytest.raises(LayerError):
        case_edit.set_conditions(control, control.cases[0], specs)


def test_move_into_layer_and_remove_layer_round_trip():
    config = _config()
    control = config.controls[0]  # the modifier_3 definition, a direct binding
    userio = control.userios[0]
    edit = case_edit.move_into_layer(control, userio, [ConditionSpec("modifier_1", "equal", "on")])
    assert edit.userios == [] and edit.cases[-1].userios == [userio]
    control.userios, control.cases = edit.userios, edit.cases
    xml = to_xml_string(config)
    assert '<modifier_1 operator="equal" cmp_value="on"/>' in xml
    reparsed = parse_string(xml)
    assert condition_of(reparsed.controls[0].cases[0]) == condition_of(edit.cases[-1])
    back = case_edit.remove_layer(control, control.cases[0])
    assert back.userios == [userio] and back.cases == []


def test_find_control_of_any_node():
    config = _config()
    control = _layered(config)
    assert case_edit.find_control_of(config, control.cases[0]) is control
    assert case_edit.find_control_of(config, control.cases[0].userios[0]) is control
    assert case_edit.find_control_of(config, config.controls[0].userios[0]) is config.controls[0]
    assert case_edit.find_control_of(None, control.cases[0]) is None


def test_unedited_file_still_round_trips():
    assert to_xml_string(_config()) == SAMPLE


# --- the edit panel -------------------------------------------------------------


def _panel(config):
    from djmidi.gui.edit_panel import EditPanel

    changed = []
    stack = QUndoStack()
    panel = EditPanel(stack, lambda _node: None, config_provider=lambda: config, on_layers_changed=changed.append)
    return panel, stack, changed


def test_panel_edits_conditions_as_one_undo_step():
    config = _config()
    control = _layered(config)
    panel, stack, changed = _panel(config)
    case = control.cases[0]
    panel.set_node(case)
    assert [(t.currentText(), o.currentText(), v.currentText()) for t, o, v in panel.condition_rows] == [
        ("modifier_3", "equal", "off")
    ]
    panel.condition_rows[0][2].setCurrentText("on")
    assert panel.apply_conditions(case)
    assert stack.count() == 1 and changed == [control]
    assert control.cases[0].describe() == "modifier_3 = on"
    assert "modifier_3" in to_xml_string(config)
    stack.undo()
    assert control.cases[0] is case and case.describe() == "modifier_3 = off"
    assert to_xml_string(config) == SAMPLE


def test_panel_shows_errors_instead_of_applying():
    config = _config()
    control = _layered(config)
    panel, stack, _changed = _panel(config)
    panel.set_node(control.cases[0])
    panel.condition_rows[0][0].setCurrentText("not valid")
    assert not panel.apply_conditions(control.cases[0])
    assert stack.count() == 0 and "isn't a valid modifier name" in panel.layer_status.text()


def test_panel_moves_a_direct_binding_into_a_layer_and_removes_it():
    config = _config()
    control = config.controls[0]
    userio = control.userios[0]
    panel, stack, _changed = _panel(config)
    panel.set_node(userio)
    assert panel.layer_tag.currentText() == "modifier_1"
    panel.layer_value.setCurrentText("off")
    assert panel.move_into_layer(userio, panel.layer_tag.currentText(), panel.layer_value.currentText())
    assert next(condition_of(case) for _u, case in iter_bindings(control)) != ()
    assert panel.remove_layer(control.cases[0])
    assert control.userios == [userio] and control.cases == []
    stack.undo()
    stack.undo()
    assert to_xml_string(config) == SAMPLE


def test_a_binding_inside_a_layer_offers_no_move():
    config = _config()
    panel, _stack, _changed = _panel(config)
    panel.set_node(_layered(config).cases[0].userios[0])
    assert not hasattr(panel, "layer_tag") or panel.layer_tag.parent() is None


def test_main_window_rebuilds_and_keeps_the_control_selected(tmp_path):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    window.config = _config()
    window.current_path = tmp_path / "m.xml"
    window._load_tree()
    control = window.config.controls[1]
    window.edit_panel.set_node(control.cases[0])
    window.edit_panel.condition_rows[0][2].setCurrentText("on")
    assert window.edit_panel.apply_conditions(control.cases[0])
    assert window.edit_panel.current_node is control
    window.undo_stack.undo()
    assert to_xml_string(window.config) == SAMPLE
    window.close()


# --- every identical copy (issue #440) --------------------------------------------

_LAYERED = SAMPLE[SAMPLE.index('    <control channel="3"') : SAMPLE.index("</midi>")]
# Three identical copies of the layered control, then one with a different
# binding on the same trigger, which isn't a copy and must stay as it is.
_DIFFERENT = _LAYERED.replace('cmp_value="off"', 'cmp_value="on"', 1)
COPIES = SAMPLE.replace("</midi>", _LAYERED + _LAYERED + _DIFFERENT + "</midi>")


def test_identical_copies_are_the_controls_written_the_same():
    config = parse_string(COPIES)
    first = config.controls[1]
    copies = case_edit.identical_copies(config, first)
    assert len(copies) == 3 and copies[0] is first
    assert config.controls[4] not in copies  # same trigger, different binding
    assert case_edit.identical_copies(None, first) == [first]


def test_the_real_mapping_has_ten_copies_per_trigger():
    from pathlib import Path

    from djmidi.parser import parse_file

    config = parse_file(Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml")
    assert len(case_edit.identical_copies(config, config.controls[0])) == 10


def test_panel_edits_every_copy_in_one_undo_step():
    config = parse_string(COPIES)
    panel, stack, _changed = _panel(config)
    first = config.controls[1]
    panel.set_node(first.cases[0])
    from PySide6.QtWidgets import QLabel

    assert any("3 identical copies" in label.text() for label in panel.findChildren(QLabel))
    panel.condition_rows[0][2].setCurrentText("on")
    assert panel.apply_conditions(first.cases[0])
    assert stack.count() == 1
    assert [c.cases[0].describe() for c in config.controls[1:4]] == ["modifier_3 = on"] * 3
    assert config.controls[4].cases[0].describe() == "modifier_3 = on"  # was already on, untouched
    assert config.controls[4].cases[1].describe() == "modifier_1 = on, modifier_2 = off"
    # The copies are still identical to each other after the edit.
    assert len(case_edit.identical_copies(config, config.controls[1])) == 4  # now equals the 4th too
    stack.undo()
    assert to_xml_string(config) == COPIES


def test_remove_layer_and_move_into_layer_reach_every_copy():
    config = parse_string(COPIES)
    panel, stack, _changed = _panel(config)
    assert panel.remove_layer(config.controls[2].cases[1])
    assert [len(c.cases) for c in config.controls[1:5]] == [1, 1, 1, 2]
    stack.undo()
    assert to_xml_string(config) == COPIES
