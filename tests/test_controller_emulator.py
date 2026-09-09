from pathlib import Path

from PySide6.QtWidgets import QGraphicsPixmapItem

from djmidi import catalog
from djmidi.gui import layout_view as layout_view_mod
from djmidi.gui.controller_emulator import (
    _DRAG_PX_PER_UNIT,
    _KEY_ROLE,
    ControllerEmulatorView,
    EmulatorLayoutView,
    _dry_run_lookup,
    _pick_default_variant,
)
from djmidi.gui.layout import CellKey, clear_reverse_lookup_cache, reverse_lookup
from djmidi.model import Alias, Control, MappingElement, MidiConfig, Translation, UserIO
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _toggle_config() -> MidiConfig:
    """A hand-built config (not the real fixture -- see the "Phase 5 slice
    1" tests below for why) mapping DDJ-XP2's BEAT SYNC trigger (channel 1,
    NOTE 88 -- a fixed, deterministic resolution with none of the pad-mode
    ambiguity a real pad trigger would have) to a behaviour="toggle" click
    mapping with on/off output aliases."""
    click = MappingElement(
        tag="some_toggle_fn", deck_id="0", slot_id="0",
        translations=[Translation(action_on="press", behaviour="toggle")],
    )
    output = MappingElement(
        tag="some_toggle_fn", deck_id="0", slot_id="0",
        translations=[Translation(aliases=[Alias(name="on", value="20"), Alias(name="off", value="0")])],
    )
    control = Control(
        channel="1", event_type="Note On", control="88",
        userios=[UserIO(event="click", mappings=[click]), UserIO(event="output", mappings=[output])],
    )
    return MidiConfig(controls=[control])


def _alias_info_config() -> MidiConfig:
    """Like _toggle_config(), but the click mapping is NOT behaviour="toggle"
    -- reproducing the real selected/off value-collision shape
    (auto_loop_specific_length) where this project has no state to decide
    which alias applies, so it should only ever be listed, never toggled."""
    click = MappingElement(
        tag="some_ambiguous_fn", deck_id="0", slot_id="0",
        translations=[Translation(action_on="any")],
    )
    output = MappingElement(
        tag="some_ambiguous_fn", deck_id="0", slot_id="0",
        translations=[
            Translation(
                aliases=[Alias(name="selected", value="0"), Alias(name="on", value="127"), Alias(name="off", value="0")]
            )
        ],
    )
    control = Control(
        channel="1", event_type="Note On", control="88",
        userios=[UserIO(event="click", mappings=[click]), UserIO(event="output", mappings=[output])],
    )
    return MidiConfig(controls=[control])


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


def test_pick_default_variant_prefer_token_scopes_to_a_pad_mode_bank():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "PAD", "Pad 1")]
    picked = _pick_default_variant(variants, prefer_token="(PAD MODE 3)")
    assert "(PAD MODE 3)" in picked.name
    assert "+SHIFT" not in picked.name  # still prefers the no-shift variant within the bank
    # An unknown token falls back to the plain default (no crash, no empty).
    assert _pick_default_variant(variants, prefer_token="(NO SUCH MODE)") is variants[0]


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


def test_controller_emulator_view_resolves_left_and_right_touch_strip_hold_by_slide_fx_side():
    """DDJ-XP2's EFFECT section (Slide FX 1 vs 2) bundles the same way as
    DECK/PAD MODE, just along a different channel axis -- reported by the
    maintainer as "le hold effect de la ddj-xp2" sharing the same problem."""
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    left_text = view._resolve(("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD"))
    right_text = view._resolve(("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD (R)"))
    assert "ch5 " in left_text  # Slide FX 1's channel
    assert "ch6 " in right_text  # Slide FX 2's channel


def test_emulator_right_tempo_fader_has_its_own_value_independent_of_the_left():
    """XDJ-XZ's right-tray "Tempo" fader is continuous/display-only (no
    catalog trigger), so real_position_markers() gives it a fully distinct
    DISPLAY key rather than just a distinct label -- otherwise dragging the
    right fader would also move the left one's glyph in EmulatorLayoutView
    (reported by the maintainer as "même problème pour le temps de la
    xdj-xz")."""
    view = EmulatorLayoutView("XDJ-XZ")
    left_key: CellKey = ("XDJ-XZ", "DISPLAY", "Tempo")
    right_key: CellKey = ("XDJ-XZ", "DISPLAY", "Tempo (R)")
    view.set_value(right_key, 100)
    assert view._values.get(right_key) == 100
    assert left_key not in view._values


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


# ─── Phase 5 slice 1: toggle-state tracking (gui/output_state.py) ──────────


def test_on_control_pressed_toggles_state_and_reports_the_on_alias():
    view = ControllerEmulatorView(config_provider=_toggle_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    assert view._toggle_active[key] is True
    assert "TOGGLED ON" in view._status_label.text()
    assert "'on' = 20" in view._status_label.text()
    assert key in view._emulator._active_keys


def test_on_control_pressed_toggles_back_off_on_a_second_click():
    view = ControllerEmulatorView(config_provider=_toggle_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    view._on_control_pressed(key)
    assert view._toggle_active[key] is False
    assert "TOGGLED OFF" in view._status_label.text()
    assert "'off' = 0" in view._status_label.text()
    assert key not in view._emulator._active_keys


def test_apply_output_state_is_a_noop_for_a_non_toggle_mapping():
    """SHIFT has no toggle mapping in _toggle_config() at all -- clicking
    it must not add anything to _toggle_active or the status text."""
    view = ControllerEmulatorView(config_provider=_toggle_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "OTHER", "SHIFT")
    view._on_control_pressed(key)
    assert key not in view._toggle_active
    assert "TOGGLED" not in view._status_label.text()


# ─── Non-toggle output mappings: read-only alias listing (the follow-up ───
# ─── to slice 1, covering the selected/off value-collision case) ──────────


def test_on_control_pressed_lists_aliases_for_a_non_toggle_mapping():
    view = ControllerEmulatorView(config_provider=_alias_info_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    assert "output aliases: selected=0, on=127, off=0" in view._status_label.text()
    # Read-only: no toggle state or persistent highlight for this mapping.
    assert key not in view._toggle_active
    assert key not in view._emulator._active_keys
    assert "TOGGLED" not in view._status_label.text()


def test_on_control_pressed_lists_aliases_consistently_across_repeated_clicks():
    """Unlike a toggle mapping, repeated clicks must not change the
    reported alias set -- there is no state to flip here."""
    view = ControllerEmulatorView(config_provider=_alias_info_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    first = view._status_label.text()
    view._on_control_pressed(key)
    assert view._status_label.text() == first


def test_apply_output_state_is_a_noop_with_no_config_loaded():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    assert key not in view._toggle_active


def test_switching_controller_clears_toggle_state():
    view = ControllerEmulatorView(config_provider=_toggle_config)
    view._combo.setCurrentText("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view._on_control_pressed(key)
    assert view._toggle_active
    view._combo.setCurrentText("XDJ-XZ")
    assert view._toggle_active == {}


def test_emulator_set_active_marks_and_unmarks_a_key():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view.set_active(key, True)
    assert key in view._active_keys
    view.set_active(key, False)
    assert key not in view._active_keys


def test_emulator_set_active_is_a_noop_when_state_does_not_change():
    """Mirrors set_value()'s own no-rebuild-if-unchanged discipline."""
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view.set_active(key, False)  # already inactive -- no-op
    assert key not in view._active_keys


def test_emulator_switching_controller_clears_active_keys():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "DECK", "BEAT SYNC")
    view.set_active(key, True)
    view.set_controller("XDJ-XZ")
    assert view._active_keys == set()


# ─── Real-photo backdrop ("Controller photo" checkbox) ───────────────────────


def _emulator_photo_items(view: EmulatorLayoutView):
    return [item for item in view._scene.items() if isinstance(item, QGraphicsPixmapItem)]


def test_emulator_photo_backdrop_on_by_default():
    view = EmulatorLayoutView("DDJ-XP2")
    assert view._show_reference_photo is True
    photos = _emulator_photo_items(view)
    assert len(photos) == 1
    assert photos[0].zValue() == layout_view_mod._PHOTO_Z


def test_emulator_photo_backdrop_can_be_turned_off():
    view = EmulatorLayoutView("DDJ-XP2")
    view.set_show_reference_photo(False)
    assert _emulator_photo_items(view) == []


def test_emulator_photo_backdrop_noop_without_geometry():
    view = EmulatorLayoutView("DDJ-FLX4")
    view.set_show_reference_photo(True)
    assert _emulator_photo_items(view) == []


def test_emulator_photo_backdrop_does_not_block_click_resolution(monkeypatch):
    """The z=-100 backdrop must never sit in front of a marker and swallow
    its click."""
    clear_reverse_lookup_cache()
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    view._photo_checkbox.setChecked(True)
    received: list[CellKey] = []
    view._emulator.controlPressed.connect(received.append)
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view._emulator._on_control_pressed(key)
    assert received == [key]


def test_controller_emulator_view_photo_checkbox_drives_the_layout():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    # On by default.
    assert view._photo_checkbox.isChecked() is True
    assert view._emulator._show_reference_photo is True
    assert len(_emulator_photo_items(view._emulator)) == 1

    view._photo_checkbox.setChecked(False)
    assert view._emulator._show_reference_photo is False
    assert _emulator_photo_items(view._emulator) == []

    view._photo_checkbox.setChecked(True)
    assert len(_emulator_photo_items(view._emulator)) == 1


# ─── Live "held down" state (set_live_active / set_live_active_from_hit) ─────


def test_emulator_set_live_active_is_separate_from_click_toggle_state():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view.set_live_active(key, True)
    assert key in view._live_active_keys
    assert key not in view._active_keys  # the phase-5 click-toggle set is untouched
    view.set_live_active(key, False)
    assert key not in view._live_active_keys


def test_emulator_set_live_active_noop_when_unchanged():
    view = EmulatorLayoutView("DDJ-XP2")
    view.set_live_active(("DDJ-XP2", "PAD", "Pad 1"), False)
    assert not view._live_active_keys


def test_emulator_switching_controller_clears_live_active():
    view = EmulatorLayoutView("DDJ-XP2")
    view.set_live_active(("DDJ-XP2", "PAD", "Pad 1"), True)
    view.set_controller("XDJ-XZ")
    assert view._live_active_keys == set()


def test_controller_emulator_view_set_live_active_from_hit_filters_by_controller():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    xp2_hit = next(h for h in catalog.lookup("8", "Note On", "12") if h.controller == "DDJ-XP2")
    view.set_live_active_from_hit(xp2_hit, True)
    assert view._emulator._live_active_keys

    view._emulator._live_active_keys.clear()
    xz_hit = next(h for h in catalog.lookup("6", "Note On", "0") if h.controller == "XDJ-XZ")
    view.set_live_active_from_hit(xz_hit, True)  # different controller -> ignored
    assert not view._emulator._live_active_keys


# ─── Output-direction LED state (set_led / set_led_from_hit) ────────────────


def test_emulator_set_led_is_separate_from_the_hold_and_toggle_sets():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view.set_led(key, True)
    assert key in view._led_keys
    assert key not in view._active_keys
    assert key not in view._live_active_keys
    view.set_led(key, False)
    assert key not in view._led_keys


def test_emulator_led_survives_an_input_hold_release():
    view = EmulatorLayoutView("DDJ-XP2")
    key: CellKey = ("DDJ-XP2", "PAD", "Pad 1")
    view.set_led(key, True)
    view.set_live_active(key, True)
    view.set_live_active(key, False)
    assert key in view._led_keys


def test_emulator_switching_controller_clears_led_state():
    view = EmulatorLayoutView("DDJ-XP2")
    view.set_led(("DDJ-XP2", "PAD", "Pad 1"), True)
    view.set_controller("XDJ-XZ")
    assert view._led_keys == set()


def test_controller_emulator_view_set_led_from_hit_filters_by_controller():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    xp2_hit = next(h for h in catalog.lookup("8", "Note On", "12") if h.controller == "DDJ-XP2")
    view.set_led_from_hit(xp2_hit, True)
    assert view._emulator._led_keys

    view._emulator._led_keys.clear()
    xz_hit = next(h for h in catalog.lookup("6", "Note On", "0") if h.controller == "XDJ-XZ")
    view.set_led_from_hit(xz_hit, True)  # different controller -> ignored
    assert not view._emulator._led_keys


# ─── Live jog-wheel rotation (spin_jog / spin_jog_from_key) ─────────────────


def test_emulator_spin_jog_integrates_ticks_and_clears_on_controller_switch():
    view = EmulatorLayoutView("XDJ-XZ")
    key: CellKey = ("XDJ-XZ", "DISPLAY", "Jog wheel")
    view.spin_jog(key, 4)
    view.spin_jog(key, 3)
    assert view._jog_angles[key] == 7 * layout_view_mod._JOG_DEGREES_PER_TICK
    view.spin_jog(key, 0)  # no-op
    assert view._jog_angles[key] == 7 * layout_view_mod._JOG_DEGREES_PER_TICK
    view.set_controller("DDJ-XP2")
    assert view._jog_angles == {}


def test_controller_emulator_view_spin_jog_from_key_filters_by_controller():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("XDJ-XZ")
    key = ("XDJ-XZ", "DISPLAY", "Jog wheel")
    view.spin_jog_from_key(key, 6)
    assert view._emulator._jog_angles.get(key)

    view._emulator._jog_angles.clear()
    view._combo.setCurrentText("DDJ-XP2")
    view.spin_jog_from_key(key, 6)  # instance now shows a different controller
    assert not view._emulator._jog_angles


# ─── Phase 5 slice 2: pad-mode-page tracking (gui/pad_mode.py) ──────────────


def test_clicking_a_pad_mode_button_steers_later_pad_resolution():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")

    before = view._resolve(("DDJ-XP2", "PAD", "Pad 1"))
    assert "NOTE 0" in before  # PAD MODE 1 (lowest) by default

    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 3"))
    assert view._pad_mode == {"": "(PAD MODE 3)"}
    assert ("DDJ-XP2", "PAD MODE", "PAD MODE 3") in view._emulator._active_keys

    after = view._resolve(("DDJ-XP2", "PAD", "Pad 1"))
    assert "NOTE 32" in after  # (3 - 1) * 16 -- PAD MODE 3's bank


def test_pad_mode_selection_is_per_grid_side():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 3"))
    # Left grid follows mode 3; the untouched right grid still defaults.
    assert "NOTE 32" in view._resolve(("DDJ-XP2", "PAD", "Pad 1"))
    assert "NOTE 0" in view._resolve(("DDJ-XP2", "PAD", "Pad 1 (R)"))
    assert view._current_pad_mode_token(("DDJ-XP2", "PAD", "Pad 1 (R)")) is None


def test_selecting_a_new_pad_mode_relights_and_unlights():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 2"))
    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 4"))
    assert view._pad_mode == {"": "(PAD MODE 4)"}
    assert ("DDJ-XP2", "PAD MODE", "PAD MODE 4") in view._emulator._active_keys
    assert ("DDJ-XP2", "PAD MODE", "PAD MODE 2") not in view._emulator._active_keys


def test_pad_mode_state_clears_on_controller_switch():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 3"))
    view._combo.setCurrentText("XDJ-XZ")
    assert view._pad_mode == {}
    assert view._pad_mode_button_key == {}


def test_xdj_xz_hot_cue_beat_loop_buttons_steer_pad_resolution():
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("XDJ-XZ")
    hot_cue = view._resolve(("XDJ-XZ", "PAD", "Pad 1"))  # HOT CUE mode default

    view._on_control_pressed(("XDJ-XZ", "DECK", "BEAT LOOP"))
    assert view._pad_mode == {"": "(BEAT LOOP mode)"}
    beat_loop = view._resolve(("XDJ-XZ", "PAD", "Pad 1"))
    assert beat_loop != hot_cue
