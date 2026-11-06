"""Serato <case>/<condition> blocks (modifier layers in hand-edited mappings).

The sample follows the shape published by DJ TechTools ("Even More Serato DJ
Pro MIDI Hacking", 2018): a modifier_3 definition, then one control whose
Play becomes Reverse while the modifier is on. Before this was modelled, the
parser dropped every <case>, so saving such a mapping erased those bindings.
"""

from djmidi.exporter import to_xml_string
from djmidi.parser import parse_string
from djmidi.validator import validate

SAMPLE = """<midi app="2.0.4.4588">
    <control channel="4" event_type="Note On" control="20">
        <userio event="click">
            <modifier_3>
                <translation action_on="any" behaviour="explicit"/>
            </modifier_3>
        </userio>
    </control>
    <control channel="3" event_type="Note On" control="36">
        <case>
            <condition>
                <modifier_3 operator="equal" cmp_value="off"/>
            </condition>
            <userio event="click">
                <play deck_set="Default" deck_id="0" slot_id="0">
                    <translation action_on="press" behaviour="toggle"/>
                </play>
            </userio>
            <userio event="output">
                <play deck_set="Default" deck_id="0" slot_id="0">
                    <translation action_on="any">
                        <alias name="on" value="61"/>
                        <alias name="off" value="67"/>
                    </translation>
                </play>
            </userio>
        </case>
        <case>
            <condition>
                <modifier_1 deck_set="Default" operator="equal" cmp_value="on"/>
                <modifier_2 operator="equal" cmp_value="off"/>
            </condition>
            <userio event="click">
                <reverse deck_set="Default" deck_id="0" slot_id="0">
                    <translation action_on="press" behaviour="toggle"/>
                </reverse>
            </userio>
        </case>
    </control>
</midi>
"""


def test_cases_survive_a_round_trip_byte_for_byte():
    assert to_xml_string(parse_string(SAMPLE)) == SAMPLE


def test_cases_are_modelled():
    control = parse_string(SAMPLE).controls[1]
    assert control.userios == []
    first, second = control.cases
    assert [(c.tag, c.attrs) for c in first.conditions] == [
        ("modifier_3", {"operator": "equal", "cmp_value": "off"})
    ]
    assert [u.event for u in first.userios] == ["click", "output"]
    assert first.userios[0].mappings[0].tag == "play"
    assert [c.tag for c in second.conditions] == ["modifier_1", "modifier_2"]
    assert second.conditions[0].attrs == {"deck_set": "Default", "operator": "equal", "cmp_value": "on"}
    assert second.userios[0].mappings[0].tag == "reverse"


def test_a_case_without_condition_gets_none_added():
    text = """<midi app="1">
    <control channel="1" event_type="Note On" control="1">
        <case>
            <userio event="click">
                <play deck_set="Default" deck_id="0" slot_id="0"/>
            </userio>
        </case>
    </control>
</midi>
"""
    assert to_xml_string(parse_string(text)) == text


MIXED = """<midi app="1">
    <control channel="1" event_type="Note On" control="5">
        <userio event="click">
            <play deck_set="Default" deck_id="0" slot_id="0"/>
        </userio>
        <case>
            <condition>
                <modifier_1 operator="equal" cmp_value="on"/>
            </condition>
            <userio event="click">
                <reverse deck_set="Default" deck_id="0" slot_id="0"/>
            </userio>
        </case>
        <userio event="output">
            <play deck_set="Default" deck_id="0" slot_id="0"/>
        </userio>
    </control>
</midi>
"""


def test_mixed_userio_and_case_order_is_kept():
    assert to_xml_string(parse_string(MIXED)) == MIXED


def test_iter_bindings_walks_direct_and_case_userios_with_their_condition():
    from djmidi.model import NO_CONDITION, condition_of, iter_bindings

    control = parse_string(MIXED).controls[0]
    seen = [(userio.event, userio.mappings[0].tag, condition_of(case)) for userio, case in iter_bindings(control)]
    on = (("modifier_1", (("cmp_value", "on"), ("operator", "equal"))),)
    assert seen == [("click", "play", NO_CONDITION), ("output", "play", NO_CONDITION), ("click", "reverse", on)]
    assert control.cases[0].describe() == "modifier_1 = on"


def test_validation_says_case_conditions_are_not_editable_yet():
    issues = [issue for issue in validate(parse_string(SAMPLE)) if "conditional" in issue.message]
    assert len(issues) == 1
    assert issues[0].severity == "info"
    assert "play, reverse" in issues[0].message
    assert "control=36" in issues[0].location


def test_a_modifier_definition_needs_no_deck_or_slot():
    errors = [issue for issue in validate(parse_string(SAMPLE)) if issue.severity == "error"]
    assert errors == []


def test_functions_under_different_conditions_are_not_a_conflict():
    from djmidi.validator import find_deck_conflicts

    # Play (modifier_3 off) and Reverse (modifier_1 on) on one button, deck 0.
    assert find_deck_conflicts(parse_string(SAMPLE)) == {}


def test_two_functions_under_the_same_condition_are_a_conflict():
    from djmidi.validator import find_deck_conflicts

    text = SAMPLE.replace(
        """                <reverse deck_set="Default" deck_id="0" slot_id="0">""",
        """                <eject deck_set="Default" deck_id="0" slot_id="0"/>
                <reverse deck_set="Default" deck_id="0" slot_id="0">""",
    )
    conflicts = find_deck_conflicts(parse_string(text))
    [conflict] = conflicts[("3", "Note On", "36")]
    assert conflict.functions == (("eject", "0"), ("reverse", "0"))
    assert conflict.describe().endswith("[modifier_1 = on, modifier_2 = off]")


def test_a_case_binding_is_checked_like_any_other():
    text = SAMPLE.replace('<translation action_on="press" behaviour="toggle"/>\n                </reverse>', (
        '<translation behaviour="toggle"/>\n                </reverse>'
    ))
    [issue] = [issue for issue in validate(parse_string(text)) if "missing action_on" in issue.message]
    assert "/case[modifier_1 = on, modifier_2 = off]/" in issue.location


# --- every tool sees <case> bindings, with their condition ------------------


def test_by_channel_tree_shows_cases_in_file_order_and_indexes_their_nodes():
    from djmidi.gui.tree_model import NODE_ROLE, build_channel_columns

    config = parse_string(MIXED)
    [(_channel, model, node_to_item)] = build_channel_columns(config)
    control_item = model.invisibleRootItem().child(0).child(0)
    labels = [control_item.child(row).text() for row in range(control_item.rowCount())]
    assert labels[1] == "Case: modifier_1 = on"
    case = config.controls[0].cases[0]
    assert control_item.child(1).data(NODE_ROLE) is case
    reverse = case.userios[0].mappings[0]
    assert node_to_item[id(reverse)].data(NODE_ROLE) is reverse


def test_mapping_groups_keep_conditions_apart():
    from djmidi.gui.mapping_group import build_mapping_groups

    groups = build_mapping_groups(parse_string(SAMPLE))
    by_tag = {group.tag: group for group in groups}
    assert by_tag["play"].condition_text == "modifier_3 = off"
    assert by_tag["reverse"].condition_text == "modifier_1 = on, modifier_2 = off"
    assert by_tag["modifier_3"].condition_text == ""


def test_function_search_finds_a_case_binding_with_its_condition():
    from djmidi.function_search import search_functions

    [result] = search_functions(parse_string(SAMPLE), "reverse")
    assert result.location() == "Deck 0 · Slot 0 · [modifier_1 = on, modifier_2 = off]"
    assert [(t.channel, t.control) for t in result.triggers] == [("3", "36")]


def test_mapping_diff_sees_a_change_inside_a_case():
    from djmidi.mapping_diff import diff_configs

    edited = SAMPLE.replace('<reverse deck_set="Default" deck_id="0"', '<reverse deck_set="Default" deck_id="1"')
    diff = diff_configs(parse_string(SAMPLE), parse_string(edited))
    assert not diff.is_empty
    texts = " ".join(" ".join((*entry.old_functions, *entry.new_functions)) for entry in diff.entries)
    assert "[modifier_1 = on, modifier_2 = off]" in texts


def test_deck_copy_copies_case_bindings_with_their_condition():
    from djmidi.deck_copy import plan_deck_copy

    plan = plan_deck_copy(parse_string(SAMPLE), "0", "1", {"3": "4"})
    [copy] = [control for control in plan.controls if control.channel == "4" and control.control == "36"]
    assert [case.describe() for case in copy.cases] == ["modifier_3 = off", "modifier_1 = on, modifier_2 = off"]
    assert {m.deck_id for case in copy.cases for u in case.userios for m in u.mappings} == {"1"}


def test_midi_learn_finds_the_control_of_a_case_binding():
    from djmidi.midi_learn import find_parent_control

    config = parse_string(SAMPLE)
    reverse = config.controls[1].cases[1].userios[0].mappings[0]
    assert find_parent_control(config, reverse) is config.controls[1]


def test_edit_panel_shows_a_read_only_case_card():
    from PySide6.QtGui import QUndoStack
    from PySide6.QtWidgets import QLabel

    from djmidi.gui.edit_panel import EditPanel

    panel = EditPanel(QUndoStack(), lambda _node: None)
    panel.set_node(parse_string(SAMPLE).controls[1].cases[0])
    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert "Applies while: modifier_3 = off" in texts
