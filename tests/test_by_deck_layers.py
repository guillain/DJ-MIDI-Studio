"""Modifier / SHIFT layers edited from the By Deck tab (issue #448)."""

from test_case_edit import COPIES, _panel
from test_serato_cases import SAMPLE

from djmidi.exporter import to_xml_string
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.model import NO_CONDITION
from djmidi.parser import parse_string


def _groups(config):
    return build_mapping_groups(config)


def test_a_direct_function_moves_into_a_layer_on_every_copy_in_one_step():
    config = parse_string(COPIES)
    panel, stack, _changed = _panel(config)
    group = next(group for group in _groups(config) if group.condition == NO_CONDITION)
    panel.set_node(group)
    assert panel.layer_tag.currentText() == "modifier_1"
    _control, userio, _mapping = group.members[0]
    assert panel.move_into_layer(userio, "modifier_2", "on")
    regrouped = [g for g in _groups(config) if (g.tag, g.channel, g.control_no) == (group.tag, group.channel, group.control_no)]
    assert all(g.condition != NO_CONDITION for g in regrouped)
    stack.undo()
    assert to_xml_string(config) == COPIES


def test_a_layered_function_shows_its_conditions_and_can_leave_the_layer():
    config = parse_string(COPIES)
    panel, stack, _changed = _panel(config)
    layered = next(group for group in _groups(config) if group.condition != NO_CONDITION and len(group.members) == 3)
    panel.set_node(layered)
    assert panel.condition_rows and panel.condition_rows[0][0].currentText().startswith("modifier_")
    control, userio, _mapping = layered.members[0]
    case = next(case for case in control.cases if userio in case.userios)
    assert panel.remove_layer(case)
    assert all(not copy.cases or case not in copy.cases for copy in config.controls)
    stack.undo()
    assert to_xml_string(config) == COPIES


def test_main_window_keeps_the_function_selected_in_by_deck(tmp_path):
    from djmidi.gui.main_window import MainWindow
    from djmidi.gui.mapping_group import MappingGroup

    window = MainWindow()
    try:
        window.config = parse_string(SAMPLE)
        window.current_path = tmp_path / "m.xml"
        window._load_tree()
        group = next(g for g in _groups(window.config) if g.condition == NO_CONDITION)
        assert window._select_deck_group_like(group)
        selected = window.edit_panel.current_node
        assert isinstance(selected, MappingGroup) and selected.tag == group.tag
        _control, userio, _mapping = selected.members[0]
        assert window.edit_panel.move_into_layer(userio, "modifier_3", "on")
        moved = window.edit_panel.current_node
        assert isinstance(moved, MappingGroup) and moved.tag == group.tag and moved.condition != NO_CONDITION
        window.undo_stack.undo()
        assert to_xml_string(window.config) == SAMPLE
    finally:
        window.close()
