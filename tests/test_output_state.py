from pathlib import Path

from djmidi.gui.mapping_group import MappingGroup, build_mapping_groups
from djmidi.gui.output_state import (
    describe_output_aliases,
    find_output_group,
    is_toggle_group,
    resolve_toggle_alias,
)
from djmidi.model import Alias, MappingElement, Translation
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _group(tag: str, deck_id: str, slot_id: str, translations: list[Translation]) -> MappingGroup:
    element = MappingElement(tag=tag, deck_id=deck_id, slot_id=slot_id, translations=translations)
    group = MappingGroup(
        deck_id=deck_id, slot_id=slot_id, tag=tag, event="click", channel="1", control_no="0", event_type="Note On"
    )
    group.members.append((None, None, element))  # type: ignore[arg-type]
    return group


# ─── is_toggle_group ───────────────────────────────────────────────────────


def test_is_toggle_group_true_for_a_real_toggle_mapping():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    codfather = next(g for g in groups if g.tag == "codfather_st" and g.event == "click")
    assert is_toggle_group(codfather) is True


def test_is_toggle_group_false_for_an_explicit_mapping():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    auto_loop = next(g for g in groups if g.tag == "auto_loop_specific_length" and g.event == "click")
    assert is_toggle_group(auto_loop) is False


def test_is_toggle_group_false_with_no_translations():
    group = _group("some_tag", "0", "0", [])
    assert is_toggle_group(group) is False


# ─── find_output_group ─────────────────────────────────────────────────────


def test_find_output_group_locates_the_paired_output_mapping():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    click = next(g for g in groups if g.tag == "codfather_st" and g.event == "click" and g.deck_id == "0" and g.slot_id == "0")
    output = find_output_group(groups, click)
    assert output is not None
    assert output.event == "output"
    assert output.tag == "codfather_st"
    assert output.deck_id == "0"
    assert output.slot_id == "0"


def test_find_output_group_returns_none_when_absent():
    click = _group("nonexistent_tag", "5", "5", [Translation(behaviour="toggle")])
    assert find_output_group([click], click) is None


# ─── resolve_toggle_alias ───────────────────────────────────────────────────


def test_resolve_toggle_alias_returns_the_on_alias_for_a_real_mapping():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    click = next(g for g in groups if g.tag == "codfather_st" and g.event == "click" and g.deck_id == "0" and g.slot_id == "0")
    output = find_output_group(groups, click)
    alias = resolve_toggle_alias(output, active=True)
    assert alias is not None
    assert alias.name == "on"
    assert alias.value == "20"


def test_resolve_toggle_alias_returns_the_off_alias():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    click = next(g for g in groups if g.tag == "codfather_st" and g.event == "click" and g.deck_id == "0" and g.slot_id == "0")
    output = find_output_group(groups, click)
    alias = resolve_toggle_alias(output, active=False)
    assert alias is not None
    assert alias.name == "off"
    assert alias.value == "0"


def test_resolve_toggle_alias_returns_none_for_no_output_group():
    assert resolve_toggle_alias(None, active=True) is None


def test_resolve_toggle_alias_returns_none_with_no_translations():
    output = _group("some_tag", "0", "0", [])
    output.event = "output"
    assert resolve_toggle_alias(output, active=True) is None


def test_resolve_toggle_alias_returns_none_when_the_wanted_alias_is_absent():
    output = _group("some_tag", "0", "0", [Translation(aliases=[Alias(name="selected", value="0")])])
    output.event = "output"
    assert resolve_toggle_alias(output, active=True) is None


# ─── describe_output_aliases ────────────────────────────────────────────────


def test_describe_output_aliases_lists_the_real_ambiguous_case():
    """auto_loop_specific_length's real output aliases -- selected/off both
    0, on 127 -- surfaced read-only rather than guessed at."""
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    output = next(
        g
        for g in groups
        if g.tag == "auto_loop_specific_length" and g.event == "output" and g.deck_id == "0" and g.slot_id == "6"
    )
    assert describe_output_aliases(output) == "selected=0, on=127, off=0"


def test_describe_output_aliases_returns_empty_for_no_output_group():
    assert describe_output_aliases(None) == ""


def test_describe_output_aliases_returns_empty_with_no_aliases():
    output = _group("some_tag", "0", "0", [Translation()])
    output.event = "output"
    assert describe_output_aliases(output) == ""


def test_describe_output_aliases_returns_empty_with_no_translations():
    output = _group("some_tag", "0", "0", [])
    output.event = "output"
    assert describe_output_aliases(output) == ""
