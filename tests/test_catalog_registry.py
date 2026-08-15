import pytest

from djmidi import catalog
from djmidi.catalog import make_sequential_pad_lookup
from djmidi.catalog._registry import ControllerDefinition, register


def test_builtin_controllers_are_registered_at_import():
    assert "DDJ-XP2" in catalog.CONTROLLER_NAMES
    assert "XDJ-XZ" in catalog.CONTROLLER_NAMES
    assert "DDJ-1000" in catalog.CONTROLLER_NAMES
    assert "DDJ-FLX4" in catalog.CONTROLLER_NAMES
    assert "DDJ-FLX10" in catalog.CONTROLLER_NAMES
    assert "Numark Mixtrack Pro FX" in catalog.CONTROLLER_NAMES
    assert "Hercules DJControl Inpulse 500" in catalog.CONTROLLER_NAMES
    assert catalog.PAD_COUNTS == {
        "DDJ-XP2": 16,
        "XDJ-XZ": 8,
        "DDJ-1000": 16,
        "DDJ-FLX4": 8,
        "DDJ-FLX10": 16,
        "Numark Mixtrack Pro FX": 8,
        "Hercules DJControl Inpulse 500": 8,
    }


def test_builtin_controller_plugins_expose_metadata():
    definitions = {definition.name: definition for definition in catalog.all_controller_definitions()}
    assert definitions["DDJ-XP2"].plugin_id == "pioneer.ddj-xp2"
    assert definitions["DDJ-XP2"].manufacturer == "Pioneer DJ"
    assert definitions["DDJ-XP2"].supported_software == ("serato",)
    assert definitions["DDJ-XP2"].reference_image == "ddj-xp2.png"
    assert definitions["DDJ-FLX10"].reference_image == "ddj-flx10.png"
    assert definitions["DDJ-FLX4"].reference_image == "ddj-flx4.png"
    assert definitions["Numark Mixtrack Pro FX"].reference_image == "numark-mixtrack-pro-fx.png"
    assert definitions["Hercules DJControl Inpulse 500"].reference_image == "hercules-djcontrol-inpulse-500.png"
    assert definitions["Numark Mixtrack Pro FX"].manufacturer == "Numark"
    assert definitions["Hercules DJControl Inpulse 500"].manufacturer == "Hercules"
    assert definitions["DDJ-FLX10"].plugin_id == "pioneer.ddj-flx10"
    assert definitions["DDJ-FLX10"].supported_software == ("rekordbox", "serato")


def test_ddj_flx10_resolves_transport_and_pad_controls():
    transport_hits = catalog.lookup("3", "Note On", "0")
    assert any(hit.controller == "DDJ-FLX10" and hit.name == "PLAY/PAUSE" for hit in transport_hits)

    pad_hits = catalog.lookup("9", "Note On", "31")
    assert any(hit.controller == "DDJ-FLX10" and hit.name == "Deck 4 Pad 16 (PAD MODE 2)" for hit in pad_hits)


def test_ddj_flx4_resolves_two_deck_transport_and_pad_controls():
    transport_hits = catalog.lookup("2", "Note On", "0")
    assert any(hit.controller == "DDJ-FLX4" and hit.name == "PLAY/PAUSE" for hit in transport_hits)

    pad_hits = catalog.lookup("7", "Note On", "23")
    assert any(hit.controller == "DDJ-FLX4" and hit.name == "Deck 2 Pad 8 (PAD MODE 2)" for hit in pad_hits)


def test_non_pioneer_controller_plugins_resolve_pad_controls():
    numark_hits = catalog.lookup("1", "Note On", "36")
    assert any(hit.controller == "Numark Mixtrack Pro FX" and hit.name == "Deck 1 Pad 1" for hit in numark_hits)

    hercules_hits = catalog.lookup("2", "Note On", "47")
    assert any(hit.controller == "Hercules DJControl Inpulse 500" and hit.name == "Deck 2 Pad 8" for hit in hercules_hits)


def test_controller_detection_ranks_matching_port_name():
    matches = catalog.detect_controller("USB DDJ-XP2 MIDI 1")
    assert matches
    assert matches[0].controller.name == "DDJ-XP2"
    assert matches[0].score == 100


def test_disabled_controller_is_removed_from_active_lookup_and_detection():
    catalog.set_enabled_plugin_ids({"pioneer.ddj-xp2"})
    try:
        assert catalog.CONTROLLER_NAMES == ["DDJ-XP2"]
        assert catalog.lookup("1", "Note On", "36") == []
        assert catalog.detect_controller("Numark Mixtrack Pro FX") == []
    finally:
        catalog.set_enabled_plugin_ids(None)


def test_builtin_controller_plugins_are_discovered_without_central_import_list():
    catalog.discover_plugins()
    assert set(catalog.CONTROLLER_NAMES) >= {"DDJ-XP2", "XDJ-XZ", "DDJ-1000"}


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
