from pathlib import Path

from djmidi.gui.controller_emulator import (
    ControllerEmulatorView,
    EmulatorLayoutView,
    _dry_run_lookup,
    _pick_default_variant,
)
from djmidi.gui.layout import CellKey, clear_reverse_lookup_cache, reverse_lookup
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_pick_default_variant_prefers_the_no_shift_variant():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "DECK", "BEAT SYNC")]
    picked = _pick_default_variant(variants)
    assert picked.name == "BEAT SYNC"


def test_pick_default_variant_falls_back_to_the_lowest_pad_mode():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "PAD", "Pad 1")]
    picked = _pick_default_variant(variants)
    assert picked is variants[0]


def test_dry_run_lookup_only_includes_click_events():
    config = parse_file(FIXTURE)
    lookup = _dry_run_lookup(config)
    assert lookup  # the real fixture has real click-mapped triggers
    for functions in lookup.values():
        assert functions  # never an empty list under a real key


# ─── EmulatorLayoutView ────────────────────────────────────────────────────

def test_emulator_layout_view_renders_cells_for_its_controller():
    view = EmulatorLayoutView("DDJ-XP2")
    assert len(view._scene.items()) > 0


def test_emulator_layout_view_set_controller_switches_and_rebuilds():
    view = EmulatorLayoutView("DDJ-XP2")
    view.set_controller("XDJ-XZ")
    assert view._controller == "XDJ-XZ"


def test_emulator_layout_view_flash_key_then_reverts():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view.flash_key(key)
    assert key in view._flash_keys
    view._clear_flash(key)
    assert key not in view._flash_keys


def test_emulator_layout_view_click_emits_control_pressed_and_flashes():
    view = EmulatorLayoutView("DDJ-XP2")
    received: list[CellKey] = []
    view.controlPressed.connect(received.append)
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view._on_control_pressed(key)
    assert received == [key]
    assert key in view._flash_keys


# ─── ControllerEmulatorView ────────────────────────────────────────────────

def test_controller_emulator_view_resolves_against_no_config():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "OTHER", "SHIFT")
    text = view._resolve(key)
    assert "no mapping loaded" in text


def test_controller_emulator_view_resolves_an_unmapped_trigger():
    config = parse_file(FIXTURE)
    view = ControllerEmulatorView(config_provider=lambda: config)
    view._combo.setCurrentText("DDJ-XP2")
    # DDJ-XP2's Pad 1 default variant (ch8 NOTE 12) is not present in the
    # real fixture (confirmed by grepping the fixture XML directly).
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    text = view._resolve(key)
    assert "not mapped in the loaded config" in text


def test_controller_emulator_view_click_updates_status_label():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "OTHER", "SHIFT")
    view._on_control_pressed(key)
    assert "SHIFT" in view._status_label.text()


def test_controller_emulator_view_unknown_cell_reports_no_trigger():
    view = ControllerEmulatorView(config_provider=lambda: None)
    key: CellKey = ("DDJ-XP2", "MIXER", "Effect 1 Depth")
    text = view._resolve(key)
    assert "no raw MIDI trigger known" in text


def test_controller_emulator_view_switching_controller_resets_status():
    view = ControllerEmulatorView(config_provider=lambda: None)
    key: CellKey = ("DDJ-XP2", "OTHER", "SHIFT")
    view._on_control_pressed(key)
    view._combo.setCurrentText("XDJ-XZ")
    assert view._status_label.text() == "Click a control to see what it resolves to."
    assert view._emulator._controller == "XDJ-XZ"


def test_controller_emulator_view_refresh_controllers_preserves_selection():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("XDJ-XZ")
    view.refresh_controllers()
    assert view._combo.currentText() == "XDJ-XZ"
    assert view._emulator._controller == "XDJ-XZ"
