import ast
import importlib.util

from djmidi import catalog
from djmidi.catalog._registry import ControlInfo, register
from djmidi.catalog.codegen import (
    build_definition,
    find_trigger_conflicts,
    generate_module_source,
    infer_section_order,
    merge_by_channel,
)


def test_infer_section_order_reflects_first_seen():
    entries = [
        ControlInfo("MiniPad", "PAD", "PAD 1", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "1"),
        ControlInfo("MiniPad", "PAD", "PAD 2", "NOTE", ("1",), "2"),
    ]
    assert infer_section_order(entries) == ("PAD", "DECK")


def test_build_definition_merges_and_registers_cleanly():
    entries = [
        ControlInfo("__BuildDefTest__", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("__BuildDefTest__", "DECK", "PLAY", "NOTE", ("2",), "0"),
    ]
    definition = build_definition("__BuildDefTest__", entries)
    assert definition.name == "__BuildDefTest__"
    assert definition.pad_lookup is None
    assert definition.pad_count == 0
    assert definition.section_order == ("DECK",)
    assert len(definition.static_entries) == 1
    assert definition.static_entries[0].channels == ("1", "2")

    register(definition)
    try:
        hits = catalog.lookup("1", "Note On", "0")
        assert any(h.controller == "__BuildDefTest__" and h.name == "PLAY" for h in hits)
    finally:
        catalog._registry._REGISTRY.pop("__BuildDefTest__", None)


def test_find_trigger_conflicts_flags_same_trigger_different_labels():
    entries = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("1",), "0"),
    ]
    conflicts = find_trigger_conflicts(entries)
    assert len(conflicts) == 1
    assert "channel=1" in conflicts[0]
    assert "'DECK'/'PLAY'" in conflicts[0]
    assert "'DECK'/'CUE'" in conflicts[0]


def test_find_trigger_conflicts_ignores_same_label_different_channel():
    entries = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("2",), "0"),
    ]
    assert find_trigger_conflicts(entries) == []


def test_find_trigger_conflicts_ignores_distinct_triggers():
    entries = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("1",), "1"),
    ]
    assert find_trigger_conflicts(entries) == []


def test_merge_by_channel_folds_same_control_across_channels():
    entries = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("2",), "0"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("3",), "0"),
    ]
    merged = merge_by_channel(entries)
    assert len(merged) == 1
    assert merged[0].channels == ("1", "2", "3")


def test_merge_by_channel_leaves_distinct_rows_alone():
    entries = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("1",), "1"),
    ]
    merged = merge_by_channel(entries)
    assert len(merged) == 2
    assert [e.name for e in merged] == ["PLAY", "CUE"]


def test_merge_by_channel_preserves_first_seen_order():
    entries = [
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("2",), "1"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("1",), "1"),
    ]
    merged = merge_by_channel(entries)
    assert [e.name for e in merged] == ["CUE", "PLAY"]
    assert merged[0].channels == ("2", "1")


def test_generate_module_source_produces_valid_python():
    entries = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    source = generate_module_source("MiniPad", entries)
    ast.parse(source)


def test_generate_module_source_escapes_quotes_in_controller_name():
    """controller_name is free-form, user-typed text (via the Controller Setup
    tab's name field) — unlike the other fields, which are embedded via !r as
    complete standalone literals, it lands in the middle of the generated
    module's already-open triple-double-quoted docstring, so a literal '\"\"\"'
    in the name must not be able to prematurely close it."""
    entries = [ControlInfo('Weird"""Name', "DECK", "PLAY", "NOTE", ("1",), "0")]
    source = generate_module_source('Weird"""Name', entries)
    ast.parse(source)  # must not raise SyntaxError
    assert 'name=\'Weird"""Name\',' in source


def test_generate_module_source_smoke_content():
    entries = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    source = generate_module_source("MiniPad", entries)
    assert "_STATIC: list[ControlInfo] = [" in source
    assert "register(" in source
    assert "ControlInfo('MiniPad', 'DECK', 'PLAY', 'NOTE', ('1',), '0')," in source


def test_generate_module_source_infers_section_order_from_first_seen():
    entries = [
        ControlInfo("MiniPad", "PAD", "PAD 1", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "1"),
        ControlInfo("MiniPad", "PAD", "PAD 2", "NOTE", ("1",), "2"),
    ]
    source = generate_module_source("MiniPad", entries)
    assert "section_order=('PAD', 'DECK')" in source


def test_generate_module_source_round_trips_through_registry(tmp_path):
    entries = merge_by_channel(
        [
            ControlInfo("__CodegenTest__", "DECK", "PLAY", "NOTE", ("1",), "0"),
            ControlInfo("__CodegenTest__", "DECK", "PLAY", "NOTE", ("2",), "0"),
        ]
    )
    source = generate_module_source("__CodegenTest__", entries)
    module_path = tmp_path / "codegen_test_module.py"
    module_path.write_text(source)

    spec = importlib.util.spec_from_file_location("codegen_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        assert "__CodegenTest__" in catalog.CONTROLLER_NAMES
        hits = catalog.lookup("1", "Note On", "0")
        assert any(h.controller == "__CodegenTest__" and h.name == "PLAY" for h in hits)
        hits2 = catalog.lookup("2", "Note On", "0")
        assert any(h.controller == "__CodegenTest__" and h.name == "PLAY" for h in hits2)
    finally:
        catalog._registry._REGISTRY.pop("__CodegenTest__", None)
