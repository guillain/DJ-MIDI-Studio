import pytest

from djmidi import catalog
from djmidi.catalog import make_sequential_pad_lookup
from djmidi.catalog._registry import ControllerDefinition, register


def test_builtin_controllers_are_registered_at_import():
    assert "DDJ-XP2" in catalog.CONTROLLER_NAMES
    assert "XDJ-XZ" in catalog.CONTROLLER_NAMES
    assert "DDJ-1000" in catalog.CONTROLLER_NAMES
    assert catalog.PAD_COUNTS == {"DDJ-XP2": 16, "XDJ-XZ": 8, "DDJ-1000": 16}


def test_registering_twice_raises():
    definition = ControllerDefinition(name="__DuplicateTest__")
    register(definition)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register(definition)
    finally:
        # Registry is process-global; don't leak this test's controller into others.
        del catalog._registry._REGISTRY["__DuplicateTest__"]


def test_register_replace_true_overwrites_existing():
    first = ControllerDefinition(name="__ReplaceTest__", static_entries=[catalog.ControlInfo("__ReplaceTest__", "DECK", "PLAY", "NOTE", ("1",), "0")])
    second = ControllerDefinition(name="__ReplaceTest__", static_entries=[catalog.ControlInfo("__ReplaceTest__", "DECK", "CUE", "NOTE", ("1",), "1")])
    register(first)
    try:
        register(second, replace=True)
        assert catalog.get_definition("__ReplaceTest__") is second
        hits = catalog.lookup("1", "Note On", "1")
        assert any(h.name == "CUE" for h in hits)
    finally:
        del catalog._registry._REGISTRY["__ReplaceTest__"]


def test_unknown_controller_raises():
    with pytest.raises(ValueError, match="Unknown controller"):
        catalog.get_definition("__NoSuchController__")


def test_registering_a_new_controller_is_picked_up_everywhere_without_touching_gui_code():
    """The whole point of the registry: adding a controller is `register(...)`
    plus (normally) one import line in catalog/__init__.py — nothing else."""
    static = [catalog.ControlInfo("__TestPad__", "DECK", "PLAY", "NOTE", ("1",), "10")]
    pad_lookup = make_sequential_pad_lookup("__TestPad__", {"2": 1}, pad_count=4, mode_names=["DEFAULT"])
    definition = ControllerDefinition(
        name="__TestPad__",
        static_entries=static,
        pad_lookup=pad_lookup,
        pad_count=4,
        pad_columns=2,
        section_order=("DECK",),
    )
    register(definition)
    try:
        assert "__TestPad__" in catalog.CONTROLLER_NAMES
        assert catalog.PAD_COUNTS["__TestPad__"] == 4

        hits = catalog.lookup("1", "Note On", "10")
        assert any(h.controller == "__TestPad__" and h.name == "PLAY" for h in hits)

        pad_hits = catalog.lookup("2", "Note On", "1")
        assert any(h.controller == "__TestPad__" and "Pad 2" in h.name for h in pad_hits)

        from djmidi.gui import layout as layout_mod

        cells = layout_mod.build_layout("__TestPad__")
        pad_cells = [c for c in cells if c.section == "PAD"]
        assert len(pad_cells) == 4
        assert {c.col for c in pad_cells} == {0, 1}  # pad_columns=2
    finally:
        del catalog._registry._REGISTRY["__TestPad__"]


def test_make_sequential_pad_lookup_out_of_range_returns_none():
    pad_lookup = make_sequential_pad_lookup("X", {"1": 1}, pad_count=4, mode_names=["A", "B"])
    assert pad_lookup("1", "NOTE", "3") is not None  # pad 4, mode A
    assert pad_lookup("1", "NOTE", "4") is None  # pad index 4 >= pad_count
    assert pad_lookup("1", "NOTE", "32") is None  # mode_index 2 >= len(modes)
    assert pad_lookup("9", "NOTE", "0") is None  # unknown channel
    assert pad_lookup("1", "CC", "0") is None  # wrong kind
