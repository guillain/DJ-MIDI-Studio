from __future__ import annotations

import copy
from pathlib import Path

import pytest

from djmidi.mapping_diff import KINDS, diff_configs, function_label
from djmidi.model import Alias, Control, MappingElement, MidiConfig, Translation, UserIO
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


@pytest.fixture(scope="module")
def real_config() -> MidiConfig:
    return parse_file(FIXTURE)


def _copy(config: MidiConfig) -> MidiConfig:
    return copy.deepcopy(config)


def _controls(config: MidiConfig, channel: str, control: str) -> list[Control]:
    return [c for c in config.controls if c.channel == channel and c.control == control]


def _elements(config: MidiConfig, channel: str, control: str, event: str):
    for item in _controls(config, channel, control):
        for userio in item.userios:
            if userio.event == event:
                yield from userio.mappings


def test_identical_real_files_have_no_difference(real_config):
    diff = diff_configs(real_config, parse_file(FIXTURE))
    assert diff.is_empty
    assert diff.counts() == dict.fromkeys(KINDS, 0)


def test_reordered_controls_mean_the_same_thing(real_config):
    shuffled = _copy(real_config)
    shuffled.controls.reverse()
    assert diff_configs(real_config, shuffled).is_empty


def test_retagging_every_copy_is_one_reassignment_not_ten(real_config):
    new = _copy(real_config)
    for element in _elements(new, "14", "65", "click"):
        assert element.tag == "codfather_st"
        element.tag = "play"
    diff = diff_configs(real_config, new)
    assert [entry.kind for entry in diff.entries] == ["reassigned"]
    entry = diff.entries[0]
    assert entry.trigger == ("14", "Note On", "65")
    assert entry.event == "click"
    assert entry.old_functions == ("Codfather ST (deck 3, slot 1)",)
    assert entry.new_functions == ("play (deck 3, slot 1)",)
    assert entry.summary() == "Codfather ST (deck 3, slot 1) -> play (deck 3, slot 1)"
    # The raw tag stays available for the dialog's tooltip.
    assert entry.old_raw == ("codfather_st (deck 3, slot 1)",)
    assert entry.raw_summary() == "codfather_st (deck 3, slot 1) -> play (deck 3, slot 1)"


def test_dropping_one_duplicate_copy_is_a_count_change(real_config):
    new = _copy(real_config)
    victim = _controls(new, "14", "65")[0]
    new.controls.remove(victim)
    diff = diff_configs(real_config, new)
    assert {entry.kind for entry in diff.entries} == {"duplicates"}
    assert all("x10 -> x9" in entry.details[0] for entry in diff.entries)
    assert not diff.by_kind("removed")


def test_removed_trigger_is_reported_once(real_config):
    new = _copy(real_config)
    new.controls = [c for c in new.controls if not (c.channel == "14" and c.control == "65")]
    diff = diff_configs(real_config, new)
    removed = diff.by_kind("removed")
    assert {entry.event for entry in removed} == {e.event for c in _controls(real_config, "14", "65") for e in c.userios}
    assert len(diff.entries) == len(removed)
    assert all(entry.trigger == ("14", "Note On", "65") for entry in removed)


def test_added_trigger_and_added_function(real_config):
    new = _copy(real_config)
    new.controls.append(
        Control("16", "Note On", "1", [UserIO("click", [MappingElement("play", "Default", "1", "0")])])
    )
    first = _controls(new, "14", "65")[0]
    next(u for u in first.userios if u.event == "click").mappings.append(MappingElement("cue", "Default", "3"))
    diff = diff_configs(real_config, new)
    added = diff.by_kind("added")
    assert [(entry.trigger, entry.new_functions) for entry in added] == [
        (("14", "Note On", "65"), ("cue (deck 3)",)),
        (("16", "Note On", "1"), ("play (deck 1, slot 0)",)),
    ]
    assert not diff.by_kind("reassigned")


def test_alias_value_change_on_every_copy_is_described(real_config):
    new = _copy(real_config)
    for element in _elements(new, "14", "72", "output"):
        for translation in element.translations:
            for alias in translation.aliases:
                if alias.name == "on":
                    alias.value = "100"
    diff = diff_configs(real_config, new)
    assert [entry.kind for entry in diff.entries] == ["changed"]
    assert diff.entries[0].details == ("alias on: 127 -> 100",)


def test_editing_one_copy_out_of_ten_says_so(real_config):
    new = _copy(real_config)
    next(_elements(new, "14", "74", "click")).translations[0].behaviour = "toggle"
    diff = diff_configs(real_config, new)
    assert [entry.kind for entry in diff.entries] == ["changed"]
    assert diff.entries[0].details == ("behaviour: explicit -> toggle", "on 1 of 10 copies")


def test_entries_are_grouped_by_kind_then_trigger():
    def config(*controls):
        return MidiConfig(controls=list(controls))

    def control(number, tag, behaviour="explicit"):
        translation = Translation("press", behaviour, [Alias("on", "127")])
        return Control("1", "Note On", number, [UserIO("click", [MappingElement(tag, translations=[translation])])])

    old = config(control("10", "a"), control("2", "b"), control("3", "c"))
    new = config(control("10", "a", "toggle"), control("2", "x"), control("4", "d"))
    diff = diff_configs(old, new)
    assert [(entry.kind, entry.control) for entry in diff.entries] == [
        ("reassigned", "2"),
        ("added", "4"),
        ("removed", "3"),
        ("changed", "10"),
    ]


def test_traktor_binding_position_is_not_a_difference():
    def config(binding):
        element = MappingElement("Play", deck_id="1", extra_attrs={"device": "XDJ"})
        return MidiConfig(controls=[Control("1", "Note On", "0", [UserIO("click", [element])], {"tsi_binding": binding})])

    assert diff_configs(config("1"), config("7")).is_empty


def test_function_label_names_non_default_deck_sets():
    assert function_label(("play", "Default", "1", None)) == "play (deck 1)"
    assert function_label(("play", "Alt", None, "2")) == "play (set Alt, slot 2)"
    assert function_label(("master", None, None, None)) == "master"


def test_function_label_uses_readable_names_and_keeps_the_raw_form():
    key = ("auto_loop_roll_specific_length", "Default", "2", "3")
    assert function_label(key) == "Loop roll (deck 2, slot 3)"
    assert function_label(key, raw=True) == "auto_loop_roll_specific_length (deck 2, slot 3)"


def test_changed_entry_carries_raw_tags_too(real_config):
    new = _copy(real_config)
    next(_elements(new, "14", "74", "click")).translations[0].behaviour = "toggle"
    (entry,) = diff_configs(real_config, new).entries
    assert entry.old_raw == entry.new_raw
    assert entry.raw_summary().startswith(entry.old_raw[0])
