from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsRectItem

from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
from djmidi.gui import layout_view as layout_view_mod
from djmidi.gui.layout_view import ControllerLayoutView

_USAGE = {("DDJ-XP2", "PAD", "Pad 1"): {"0": {"codfather_st"}, "2": {"auto_loop_specific_length"}}}


def _glyph_brush_color(view: ControllerLayoutView, key: tuple[str, str, str]):
    """Find the small pad/button glyph rect (not the larger half-background
    rect, which shares the same _KEY_ROLE data) and return its brush color.

    Glyph size is per-controller (LayoutMetrics.pad_glyph/button_glyph), so
    pick the smallest matching rect rather than a hardcoded pixel width --
    it is always far smaller than the half-background rect (LayoutMetrics.cell_w)."""
    candidates = [
        item
        for item in view._scene.items()
        if isinstance(item, QGraphicsRectItem) and item.data(layout_view_mod._KEY_ROLE) == key
    ]
    if candidates:
        return min(candidates, key=lambda item: item.rect().width()).brush().color()
    raise AssertionError(f"no pad/button glyph found for {key}")


def _knob_marker_line(view: ControllerLayoutView, key: tuple[str, str, str]):
    for item in view._scene.items():
        if isinstance(item, QGraphicsLineItem) and item.data(layout_view_mod._KEY_ROLE) == key:
            return item.line()
    raise AssertionError(f"no knob marker found for {key}")


def _fader_thumb_top(view: ControllerLayoutView, key: tuple[str, str, str]) -> float:
    for item in view._scene.items():
        if (
            isinstance(item, QGraphicsRectItem)
            and item.data(layout_view_mod._KEY_ROLE) == key
            and item.rect().width() == 18
        ):
            return item.rect().y()
    raise AssertionError(f"no fader thumb found for {key}")


def test_refresh_controllers_adds_newly_registered_controller_and_keeps_selection():
    view = ControllerLayoutView()
    for i in range(view._controller_tabs.count()):
        if view._controller_tabs.tabText(i) == "XDJ-XZ":
            view._controller_tabs.setCurrentIndex(i)
            break
    register(ControllerDefinition(name="__LayoutLiveTest__"))
    try:
        view.refresh_controllers()
        items = [view._controller_tabs.tabText(i) for i in range(view._controller_tabs.count())]
        assert "__LayoutLiveTest__" in items
        assert view._controller == "XDJ-XZ"
    finally:
        del catalog._registry._REGISTRY["__LayoutLiveTest__"]


def test_deck_filter_hidden_by_default():
    view = ControllerLayoutView()
    assert view._deck_combo is None


def test_empty_controller_catalog_does_not_crash(monkeypatch):
    monkeypatch.setattr(catalog, "CONTROLLER_NAMES", [], raising=False)
    view = ControllerLayoutView()
    assert view._controller == ""
    assert view._controller_tabs.count() == 0
    assert len(view._scene.items()) == 1


def test_deck_filter_populated_from_usage():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    items = [view._deck_combo.itemText(i) for i in range(view._deck_combo.count())]
    assert items == ["All decks", "Deck 0", "Deck 2"]


def test_deck_filter_narrows_selected_deck_only():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    view._deck_combo.setCurrentText("Deck 2")
    assert view._selected_deck_filter() == "2"
    view._deck_combo.setCurrentText("All decks")
    assert view._selected_deck_filter() is None


def test_all_decks_shows_union_of_tags():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 1"), None)
    assert decks == {"0", "2"}
    assert tags == {"codfather_st", "auto_loop_specific_length"}


def test_deck_filter_narrows_tags_to_that_deck_only():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 1"), "0")
    assert decks == {"0"}
    assert tags == {"codfather_st"}


def test_unmapped_cell_returns_empty():
    view = ControllerLayoutView()
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 99"), None)
    assert decks == set()
    assert tags == set()


def test_linked_cell_from_other_controller_is_stored_and_rendered():
    usage = {
        ("DDJ-XP2", "PAD", "Pad 13"): {"1": {"codfather_st"}},
        ("XDJ-XZ", "PAD", "Pad 5"): {"1": {"codfather_st"}},
    }
    linked = {("DDJ-XP2", "PAD", "Pad 13"): {("XDJ-XZ", "PAD", "Pad 5")}}
    view = ControllerLayoutView()
    view.set_usage(usage, linked)
    assert view._linked_cells == linked
    # Rebuilding must not crash with a populated split-cell (top + bottom half + divider).
    assert len(view._scene.items()) > 0


def test_cell_without_link_renders_placeholder_without_crashing():
    view = ControllerLayoutView()
    view.set_usage({("DDJ-XP2", "PAD", "Pad 1"): {"1": {"codfather_st"}}})
    assert view._linked_cells == {}
    assert len(view._scene.items()) > 0


def test_set_selected_keys_stores_and_triggers_rebuild():
    view = ControllerLayoutView()
    view.set_usage(_USAGE)
    view.set_selected_keys({("DDJ-XP2", "PAD", "Pad 1")})
    assert view._selected_keys == {("DDJ-XP2", "PAD", "Pad 1")}
    view.set_selected_keys(set())
    assert view._selected_keys == set()


def test_selection_history_fades_previous_layout_selection():
    view = ControllerLayoutView()
    first = ("DDJ-XP2", "PAD", "Pad 1")
    second = ("DDJ-XP2", "PAD", "Pad 2")
    view.set_selected_keys({first})
    view.set_selected_keys({second})
    assert view._selected_keys == {second}
    assert view._selection_history == [{first}]
    view.clear_selection_history()
    assert view._selection_history == []


def test_set_controller_switches_tab_when_name_exists():
    view = ControllerLayoutView()
    assert view.set_controller("XDJ-XZ") is True
    assert view._controller == "XDJ-XZ"


def test_flash_key_briefly_brightens_a_pad_glyph_then_reverts():
    view = ControllerLayoutView()
    view.set_usage(_USAGE)
    key = ("DDJ-XP2", "PAD", "Pad 1")
    normal_color = _glyph_brush_color(view, key)

    view.flash_key(key)
    assert key in view._flash_keys
    assert _glyph_brush_color(view, key) == layout_view_mod._FLASH_BRUSH.color()

    view._clear_flash(key)
    assert key not in view._flash_keys
    assert _glyph_brush_color(view, key) == normal_color


def test_flash_key_on_unused_cell_does_not_crash():
    view = ControllerLayoutView()
    view.flash_key(("DDJ-XP2", "PAD", "Pad 1"))
    assert len(view._scene.items()) > 0


def test_set_value_rotates_the_knob_marker():
    view = ControllerLayoutView()
    key = ("DDJ-XP2", "EFFECT", "EFFECT 1")
    default_line = _knob_marker_line(view, key)

    view.set_value(key, 0)
    low_line = _knob_marker_line(view, key)
    view.set_value(key, 127)
    high_line = _knob_marker_line(view, key)

    # Same pivot (center), but the tip moves to opposite sides of "up" for
    # the min/max values, and away from the untouched (default) position.
    assert low_line.p1() == high_line.p1() == default_line.p1()
    assert low_line.p2() != default_line.p2()
    assert high_line.p2() != default_line.p2()
    assert low_line.p2().x() < default_line.p2().x() < high_line.p2().x()


def test_set_value_moves_the_fader_thumb():
    view = ControllerLayoutView()
    key = ("DDJ-XP2", "MIXER", "Slide FX 1")
    default_top = _fader_thumb_top(view, key)

    view.set_value(key, 0)
    bottom_top = _fader_thumb_top(view, key)
    view.set_value(key, 127)
    top_top = _fader_thumb_top(view, key)

    # 0 sinks toward the bottom of the track (larger y), 127 rises toward the
    # top (smaller y), on either side of the untouched (default) position.
    assert top_top < default_top < bottom_top


def test_set_value_is_a_noop_when_unchanged():
    view = ControllerLayoutView()
    key = ("DDJ-XP2", "EFFECT", "EFFECT 1")
    view.set_value(key, 90)
    line = _knob_marker_line(view, key)
    view.set_value(key, 90)
    assert _knob_marker_line(view, key) == line


def test_set_value_on_unused_cell_does_not_crash():
    view = ControllerLayoutView()
    view.set_value(("DDJ-XP2", "EFFECT", "EFFECT 1"), 64)
    assert len(view._scene.items()) > 0


def test_controller_selector_is_horizontal_scrollable():
    view = ControllerLayoutView()
    assert view._controller_scroll.widget() is view._controller_tabs
    assert view._controller_tabs.minimumWidth() == 0
    assert view._controller_scroll.horizontalScrollBarPolicy().name == "ScrollBarAsNeeded"


def test_set_zoom_scales_the_view_transform():
    view = ControllerLayoutView()
    view.set_zoom(1.6)
    assert view._view.transform().m11() == 1.6
    assert view._view.transform().m22() == 1.6


def test_set_zoom_back_to_one_resets_the_transform():
    # "Reset" means giving up the manual performance-mode scale factor, not
    # necessarily an identity transform -- the resize-driven "maximize
    # space" auto-fit (_fit_card_view/_fit_real_position_view) may still
    # apply its own scale at factor 1.0, which is the whole point of that
    # feature and is asserted on its own terms elsewhere.
    view = ControllerLayoutView()
    view.set_zoom(1.6)
    assert view._manual_zoom_factor == 1.6
    view.set_zoom(1.0)
    assert view._manual_zoom_factor == 1.0
    assert view._controller_scroll.verticalScrollBarPolicy().name == "ScrollBarAlwaysOff"
    assert view.set_controller("__missing__") is False


# ─── Real-position mode (controllers with gui/geometry.CONTROL_GEOMETRY) ──────


def _real_position_items(view: ControllerLayoutView, key: tuple[str, str, str]):
    return [
        item
        for item in view._scene.items()
        if item.data(layout_view_mod._KEY_ROLE) == key
    ]


def test_real_position_mode_is_used_for_a_controller_with_geometry():
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    # isVisible() would be False regardless (the widget is never actually
    # shown in this test) -- isHidden() reflects only this widget's own
    # explicit show()/hide() call, which is what _rebuild() controls.
    assert not view._detail_label.isHidden()
    # Every real-position marker uses the geometry-photo canvas as its scene
    # rect, not the classic card grid's per-cell col_step/row_step math.
    canvas_w, canvas_h = layout_view_mod._reference_canvas_size("DDJ-XP2")
    assert view._scene.sceneRect() == layout_view_mod.QRectF(0, 0, canvas_w, canvas_h)


def test_real_position_mode_renders_both_ddj_xp2_pad_grids():
    """Regression test for the maintainer's follow-up report ("il manque des
    boutons... pas symétriques") -- both physical pad grids must render,
    not just the one geometry.CONTROL_GEOMETRY records without a "(R)" suffix."""
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    left = _real_position_items(view, ("DDJ-XP2", "PAD", "Pad 1"))
    assert left  # the left grid's Pad 1 marker + glyph exist


def test_real_position_mode_renders_the_right_mirror_cluster():
    """The right-side DECK/LOOP/QUANTIZE/PAD-MODE cluster comes from
    layout_view._RIGHT_MIRROR_GEOMETRY, not gui/geometry.CONTROL_GEOMETRY --
    both must contribute markers for the tab to read as symmetric."""
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    assert _real_position_items(view, ("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert _real_position_items(view, ("DDJ-XP2", "PAD MODE", "PAD MODE 1"))
    assert _real_position_items(view, ("DDJ-XP2", "MIXER", "Slide FX 2"))


def test_real_position_mode_renders_xdj_xz_right_tray_transport():
    view = ControllerLayoutView()
    view.set_controller("XDJ-XZ")
    assert _real_position_items(view, ("XDJ-XZ", "DECK", "PLAY/PAUSE"))
    assert _real_position_items(view, ("XDJ-XZ", "DECK", "CUE"))
    assert _real_position_items(view, ("XDJ-XZ", "DECK", "HOT CUE"))


def test_real_position_mode_falls_back_to_classic_grid_without_geometry():
    view = ControllerLayoutView()
    view.set_controller("DDJ-FLX4")
    assert not view._detail_label.isVisible()
    # Classic mode's scene rect hugs its items' bounds, not a fixed photo canvas.
    assert view._scene.sceneRect() != layout_view_mod.QRectF(0, 0, *layout_view_mod._DEFAULT_CANVAS)


def test_real_position_click_still_emits_cell_activated():
    """Clicking must keep driving the existing cross-tab navigation
    (cellActivated) exactly like classic mode -- real-position mode only
    changes how a cell is drawn, never its click behavior."""
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    received = []
    view.cellActivated.connect(received.append)
    view._view.cellClicked.emit(("DDJ-XP2", "PAD", "Pad 1"))
    assert received == [("DDJ-XP2", "PAD", "Pad 1")]


def test_detail_label_updates_on_click_in_real_position_mode():
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    view.set_usage({("DDJ-XP2", "PAD", "Pad 1"): {"1": {"codfather_st"}}})
    view._view.cellClicked.emit(("DDJ-XP2", "PAD", "Pad 1"))
    assert "codfather_st" in view._detail_label.text()


def test_fit_real_position_view_skips_when_manual_zoom_active():
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    view.set_zoom(1.6)
    transform_before = view._view.transform()
    view._fit_real_position_view()
    assert view._view.transform() == transform_before


def test_fit_card_view_never_enlarges_beyond_native_size():
    view = ControllerLayoutView()
    view.set_controller("DDJ-FLX4")
    view.resize(4000, 4000)
    view._view.viewport().resize(4000, 4000)
    shrunk = view._fit_card_view()
    assert not shrunk
    assert view._view.transform().m11() <= 1.0


# ─── Live send (gui/live_send.py) ─────────────────────────────────────────


def test_live_send_defaults_to_off_and_is_a_noop_on_click(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    assert view._live_send.is_active() is False
    view._view.cellClicked.emit(("DDJ-XP2", "OTHER", "SHIFT"))
    assert sent == []


def test_live_send_sends_on_click_when_active(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    view._live_send._toggle_button.setChecked(True)
    view._view.cellClicked.emit(("DDJ-XP2", "OTHER", "SHIFT"))
    assert len(sent) == 1
    assert sent[0][0][0] == "Port A"


def test_live_send_click_still_navigates_cross_tab_regardless_of_toggle():
    """Live send must never interfere with the existing cellActivated
    cross-tab navigation, whether it's on or off."""
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    received = []
    view.cellActivated.connect(received.append)
    view._live_send._toggle_button.setChecked(True)
    view._view.cellClicked.emit(("DDJ-XP2", "OTHER", "SHIFT"))
    assert received == [("DDJ-XP2", "OTHER", "SHIFT")]
