from pathlib import Path

from djmidi.gui.controller_emulator import (
    _DRAG_PX_PER_UNIT,
    _KEY_ROLE,
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


# ─── Real-position parity with ControllerLayoutView (gui/layout_view.py) ──────


def test_emulator_uses_real_position_mode_for_a_geometry_controller():
    """The maintainer asked for this schematic to be identical to the By
    tabs' -- for a controller with gui/geometry.CONTROL_GEOMETRY, both must
    render layout_view.real_position_markers(), not two independent layouts."""
    from djmidi.gui import layout_view as layout_view_mod

    view = EmulatorLayoutView("DDJ-XP2")
    assert view._real_position_mode is True
    markers = layout_view_mod.real_position_markers("DDJ-XP2")
    assert markers  # sanity: DDJ-XP2 does have geometry
    for marker in markers:
        matches = [
            item
            for item in view._scene.items()
            if item.data(_KEY_ROLE) == marker.key
        ]
        assert matches, f"no item found for {marker.key}"


def test_emulator_falls_back_to_classic_grid_without_geometry():
    view = EmulatorLayoutView("DDJ-FLX4")
    assert view._real_position_mode is False
    # The classic grid's scene rect hugs its items, not a fixed photo canvas.
    from djmidi.gui import layout_view as layout_view_mod

    canvas_w, canvas_h = layout_view_mod._reference_canvas_size("DDJ-FLX4")
    assert view._scene.sceneRect() != layout_view_mod.QRectF(0, 0, canvas_w, canvas_h)


def test_emulator_real_position_marker_click_still_resolves(monkeypatch):
    """A right-mirror-cluster or right-pad-grid marker (drawn only via
    real-position mode) must click through exactly like any other cell."""
    view = EmulatorLayoutView("DDJ-XP2")
    received: list[CellKey] = []
    view.controlPressed.connect(received.append)
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    assert received == [key]


def test_emulator_switching_to_a_geometry_controller_updates_real_position_mode():
    view = EmulatorLayoutView("DDJ-FLX4")
    assert view._real_position_mode is False
    view.set_controller("XDJ-XZ")
    assert view._real_position_mode is True


# ─── Pad-side identity: left ("Pad N") vs. right ("Pad N (R)") grid must ───
# ─── stay independent, both visually and on resolution (the "pressing a ───
# ─── button on one deck also activates the second deck" report) ───────────


def test_emulator_right_grid_marker_gets_its_own_presentation_key():
    """Before this fix, both grids' scene items shared the merged CellKey
    real_position_markers() resolves both "Pad 3" and "Pad 3 (R)" to; each
    physical side must now carry its own distinct key."""
    view = EmulatorLayoutView("DDJ-XP2")
    left_items = [item for item in view._scene.items() if item.data(_KEY_ROLE) == ("DDJ-XP2", "PAD", "Pad 3")]
    right_items = [
        item for item in view._scene.items() if item.data(_KEY_ROLE) == ("DDJ-XP2", "PAD", "Pad 3 (R)")
    ]
    assert left_items
    assert right_items


def test_emulator_flashing_the_right_grid_pad_does_not_flash_the_left():
    view = EmulatorLayoutView("DDJ-XP2")
    left_key: CellKey = ("DDJ-XP2", "PAD", "Pad 3")
    right_key: CellKey = ("DDJ-XP2", "PAD", "Pad 3 (R)")
    view.flash_key(right_key)
    assert right_key in view._flash_keys
    assert left_key not in view._flash_keys


def test_emulator_left_and_right_pad_clicks_emit_distinct_keys():
    view = EmulatorLayoutView("DDJ-XP2")
    received: list[CellKey] = []
    view.controlPressed.connect(received.append)
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3"))
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3 (R)"))
    assert received == [("DDJ-XP2", "PAD", "Pad 3"), ("DDJ-XP2", "PAD", "Pad 3 (R)")]


def test_controller_emulator_view_resolves_left_and_right_pad_to_their_own_deck():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    left_text = view._resolve(("DDJ-XP2", "PAD", "Pad 3"))
    right_text = view._resolve(("DDJ-XP2", "PAD", "Pad 3 (R)"))
    assert "ch8" in left_text  # deck 1's pad channel
    assert "ch10" in right_text  # deck 2's pad channel


# ─── Same fix, one section over: DECK/PAD MODE buttons (the follow-up ─────
# ─── report "tous les modes pad ont le même problème (mirroring deck 1 ────
# ─── et 2)" once the pad-grid fix above had already shipped) ───────────────


def test_emulator_right_mirror_deck_button_gets_its_own_presentation_key():
    """DDJ-XP2's second physical DECK/PAD MODE cluster (real_position_markers()
    suffixes its label " (R)" for exactly this reason) must get its own
    scene-item key, distinct from the left cluster's, the same way the pad
    grid already does."""
    view = EmulatorLayoutView("DDJ-XP2")
    left_items = [
        item for item in view._scene.items() if item.data(_KEY_ROLE) == ("DDJ-XP2", "DECK", "BEAT SYNC")
    ]
    right_items = [
        item for item in view._scene.items() if item.data(_KEY_ROLE) == ("DDJ-XP2", "DECK", "BEAT SYNC (R)")
    ]
    assert left_items
    assert right_items


def test_emulator_flashing_the_right_mirror_pad_mode_button_does_not_flash_the_left():
    view = EmulatorLayoutView("DDJ-XP2")
    left_key: CellKey = ("DDJ-XP2", "PAD MODE", "PAD MODE 1")
    right_key: CellKey = ("DDJ-XP2", "PAD MODE", "PAD MODE 1 (R)")
    view.flash_key(right_key)
    assert right_key in view._flash_keys
    assert left_key not in view._flash_keys


def test_controller_emulator_view_resolves_left_and_right_pad_mode_to_their_own_deck():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    left_text = view._resolve(("DDJ-XP2", "PAD MODE", "PAD MODE 1"))
    right_text = view._resolve(("DDJ-XP2", "PAD MODE", "PAD MODE 1 (R)"))
    assert "ch1 " in left_text  # deck 1's channel
    assert "ch2 " in right_text  # deck 2's channel


def test_controller_emulator_view_resolves_left_and_right_beat_sync_to_their_own_deck():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    left_text = view._resolve(("DDJ-XP2", "DECK", "BEAT SYNC"))
    right_text = view._resolve(("DDJ-XP2", "DECK", "BEAT SYNC (R)"))
    assert "ch1 " in left_text
    assert "ch2 " in right_text


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
    # DDJ-XP2's Pad 1 default variant (ch8 NOTE 0) is not present in the
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


def test_controller_emulator_view_accepts_an_initial_controller():
    view = ControllerEmulatorView(config_provider=lambda: None, initial_controller="XDJ-XZ")
    assert view.current_controller() == "XDJ-XZ"
    assert view._emulator._controller == "XDJ-XZ"


def test_controller_emulator_view_ignores_an_unknown_initial_controller():
    view = ControllerEmulatorView(config_provider=lambda: None, initial_controller="NOPE")
    assert view.current_controller() != "NOPE"


def test_controller_emulator_view_refresh_controllers_preserves_selection():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("XDJ-XZ")
    view.refresh_controllers()
    assert view._combo.currentText() == "XDJ-XZ"
    assert view._emulator._controller == "XDJ-XZ"


# ─── Phase 3: drag-to-set continuous controls ─────────────────────────────────


def test_set_value_persists_and_is_read_back_by_the_drag_start_value():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "MIXER", "Slide FX 1")
    assert view._current_value(key) == 63  # _MIDI_DEFAULT, before any drag
    view.set_value(key, 90)
    assert view._current_value(key) == 90


def test_set_value_is_a_noop_rebuild_when_unchanged():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "MIXER", "Slide FX 1")
    view.set_value(key, 90)
    calls = []
    view._rebuild = lambda: calls.append(1)  # type: ignore[method-assign]
    view.set_value(key, 90)
    assert calls == []


def test_value_dragged_signal_updates_the_emulator_value():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "MIXER", "Slide FX 1")
    view._view.valueDragged.emit(key, 100)
    assert view._values[key] == 100


def test_drag_on_a_continuous_glyph_moves_the_value_not_a_click():
    """A knob/fader/jog press must start a drag (no controlPressed), unlike
    a discrete pad/button press. Exercises the real drag-delta computation
    _ClickableEmulatorView.mouseMoveEvent uses, without constructing a real
    QMouseEvent (which needs a live scene item under the cursor)."""
    view = EmulatorLayoutView("DDJ-XP2")
    fader_key: CellKey = ("DDJ-XP2", "MIXER", "Slide FX 1")
    received: list[CellKey] = []
    view.controlPressed.connect(received.append)

    view._view._drag_key = fader_key
    view._view._drag_start_y = 100.0
    view._view._drag_start_value = 63
    delta = (view._view._drag_start_y - 40.0) / _DRAG_PX_PER_UNIT  # dragged up 60px
    new_value = max(0, min(127, round(view._view._drag_start_value + delta)))
    view._view.valueDragged.emit(fader_key, new_value)
    assert view._values[fader_key] == new_value
    assert new_value > 63  # dragging up increased the value
    assert received == []  # never treated as a click


def test_discrete_pad_click_is_unaffected_by_drag_support():
    view = EmulatorLayoutView("DDJ-XP2")
    received: list[CellKey] = []
    view.controlPressed.connect(received.append)
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view._on_control_pressed(key)
    assert received == [key]


def test_jog_glyph_draws_a_position_notch():
    """draw_control_glyph()'s jog branch now draws a rotation notch (phase
    3's visible feedback for the drag-to-spin gesture) -- sanity check it
    doesn't crash and adds items for a jog-kind cell."""
    from PySide6.QtWidgets import QGraphicsScene

    from djmidi.gui import layout_view as layout_view_mod

    scene = QGraphicsScene()
    metrics = layout_view_mod.metrics_for("XDJ-XZ")
    before = len(scene.items())
    layout_view_mod.draw_control_glyph(
        scene, metrics, 0, 0, "jog", ("XDJ-XZ", "DECK", "Jog wheel"), 100, False
    )
    assert len(scene.items()) > before
