from PySide6.QtGui import QColor, QPainter, QTransform

from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
from djmidi.gui import layout_view as layout_view_mod
from djmidi.gui.controller_image_view import (
    ASSETS_DIR,
    DOCUMENTS,
    DOCUMENTS_DIR,
    IMAGES,
    ControllerImageView,
    documentation_for_controller,
)


def test_refresh_controllers_adds_newly_registered_controller():
    view = ControllerImageView()
    register(ControllerDefinition(name="__ImageLiveTest__"))
    try:
        view.refresh_controllers()
        items = [view._combo.itemText(i) for i in range(view._combo.count())]
        assert "__ImageLiveTest__" in items
    finally:
        del catalog._registry._REGISTRY["__ImageLiveTest__"]


def test_asset_files_exist():
    for filename in IMAGES.values():
        assert (ASSETS_DIR / filename).exists()


def test_bundled_controller_documents_exist():
    assert set(DOCUMENTS) == {
        "DDJ-XP2",
        "XDJ-XZ",
        "DDJ-1000",
        "DDJ-REV1",
        "DDJ-FLX10",
        "Numark Mixtrack Pro FX",
        "Hercules DJControl Inpulse 500",
    }
    for filename in DOCUMENTS.values():
        assert (DOCUMENTS_DIR / filename).exists()


def test_documentation_for_controller_returns_none_when_not_bundled():
    assert documentation_for_controller("DDJ-FLX4") is None
    assert documentation_for_controller("DDJ-XP2") == DOCUMENTS_DIR / DOCUMENTS["DDJ-XP2"]


def test_ddj_1000_order_and_reference_image():
    assert catalog.CONTROLLER_NAMES.index("DDJ-FLX4") < catalog.CONTROLLER_NAMES.index("DDJ-1000")
    assert catalog.CONTROLLER_NAMES.index("DDJ-REV1") < catalog.CONTROLLER_NAMES.index("DDJ-1000")
    assert IMAGES["DDJ-1000"] == "ddj-1000.png"


def test_loads_pixmap_for_default_controller():
    view = ControllerImageView()
    assert view._pixmap_item is not None
    assert not view._scene.sceneRect().isEmpty()


def test_switching_controller_reloads_image():
    view = ControllerImageView()
    first_rect = view._scene.sceneRect()
    other = next(name for name in IMAGES if name != view._combo.currentText())
    view._combo.setCurrentText(other)
    assert view._scene.sceneRect() != first_rect


def test_set_controller_selects_known_name():
    view = ControllerImageView()
    assert view.set_controller("XDJ-XZ") is True
    assert view._combo.currentText() == "XDJ-XZ"
    assert view.set_controller("__missing__") is False


def test_zoomable_view_enables_antialiasing_and_smooth_pixmap_transform():
    """setRenderHint(self.renderHints()) is a self-referential no-op (it sets
    the hint bits already present in the *current* hints back onto themselves)
    — the viewer must actually request Antialiasing/SmoothPixmapTransform for
    a zoomed Pioneer diagram to render smoothly rather than pixelated."""
    view = ControllerImageView()
    hints = view._view.renderHints()
    assert hints & QPainter.RenderHint.Antialiasing
    assert hints & QPainter.RenderHint.SmoothPixmapTransform


def test_switching_to_controller_without_image_resets_leftover_zoom():
    """Reachable in practice via Controller Setup's "Apply now", which adds a
    freshly-applied controller (no reference image yet) to this combo mid-
    session: if the user had zoomed into the previously-shown image, the
    "Image not found" placeholder must not inherit that pan/zoom transform."""
    register(ControllerDefinition(name="__NoImageCtrl__"))
    try:
        view = ControllerImageView()
        view.refresh_controllers()  # settles _load() on the still-selected default controller
        view._view.scale(5.0, 5.0)
        zoomed = view._view.transform()
        assert zoomed != QTransform()

        assert view.set_controller("__NoImageCtrl__") is True
        assert view._view.transform() == QTransform()
    finally:
        catalog._registry._REGISTRY.pop("__NoImageCtrl__", None)


def test_resolve_image_path_handles_absolute_and_bundled():
    from pathlib import Path

    from djmidi.gui.controller_image_view import ASSETS_DIR, _resolve_image_path

    assert _resolve_image_path(None) is None
    assert _resolve_image_path("") is None
    assert _resolve_image_path("ddj-xp2-midi.png") == ASSETS_DIR / "ddj-xp2-midi.png"
    abs_path = "/tmp/custom/minipad.png"
    assert _resolve_image_path(abs_path) == Path(abs_path)


def test_geometry_checkbox_disabled_for_controller_without_geometry():
    view = ControllerImageView()
    assert view.set_controller("Hercules DJControl Inpulse 500") is True  # has a reference image but no modeled geometry
    assert view._geometry_checkbox.isEnabled() is False
    assert view._overlay_items == []


def test_geometry_checkbox_enabled_and_draws_markers_for_xdj_xz_and_ddj_xp2():
    from djmidi.gui.geometry import CONTROL_GEOMETRY

    for name in ("XDJ-XZ", "DDJ-XP2"):
        view = ControllerImageView()
        assert view.set_controller(name) is True
        assert view._geometry_checkbox.isEnabled() is True
        assert view._overlay_items == []  # unchecked by default

        view._geometry_checkbox.setChecked(True)
        assert len(view._overlay_items) == len(CONTROL_GEOMETRY[name])
        for item in view._overlay_items:
            assert item.toolTip() != ""


def test_unchecking_geometry_layer_clears_markers():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    assert view._overlay_items
    view._geometry_checkbox.setChecked(False)
    assert view._overlay_items == []


def test_switching_away_from_modeled_controller_clears_markers():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    assert view._overlay_items
    view.set_controller("Hercules DJControl Inpulse 500")
    assert view._overlay_items == []
    assert view._geometry_checkbox.isEnabled() is False


def test_geometry_overlay_markers_stay_within_the_image_bounds():
    """Sanity check for gui/geometry.py's hand-measured fractions: every
    marker must land inside the actual pixmap, not off the edge of it."""
    for name in ("XDJ-XZ", "DDJ-XP2"):
        view = ControllerImageView()
        view.set_controller(name)
        view._geometry_checkbox.setChecked(True)
        pixmap = view._pixmap_item.pixmap()
        for item in view._overlay_items:
            rect = item.rect()
            assert 0 <= rect.x() and rect.x() + rect.width() <= pixmap.width()
            assert 0 <= rect.y() and rect.y() + rect.height() <= pixmap.height()


def test_flash_key_brightens_marker_then_reverts_to_its_color():
    from djmidi.gui.geometry import CONTROL_GEOMETRY

    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    original_color = QColor(CONTROL_GEOMETRY["XDJ-XZ"]["PLAY/PAUSE"].color)
    original_color.setAlpha(110)

    view.flash_key("PLAY/PAUSE")
    item = view._overlay_items_by_label["PLAY/PAUSE"]
    assert item.brush().color() == QColor(255, 255, 255, 200)

    view._clear_flash("XDJ-XZ", "PLAY/PAUSE")
    assert item.brush().color() == original_color


def test_flash_key_on_unmodeled_label_does_not_crash():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    view.flash_key("Not A Real Control")  # must not raise


def test_flash_key_is_a_noop_when_overlay_is_unchecked():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view.flash_key("PLAY/PAUSE")  # overlay off, no items drawn -- must not raise
    assert view._overlay_items_by_label == {}


def test_clear_flash_ignores_a_stale_callback_after_switching_controller():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    view.flash_key("PLAY/PAUSE")
    view.set_controller("DDJ-1000")  # switches away before the flash timer fires
    view._clear_flash("XDJ-XZ", "PLAY/PAUSE")  # must not raise despite the stale label/controller


# ─── Live send (gui/live_send.py) ─────────────────────────────────────────


def test_marker_click_is_a_noop_when_live_send_off(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    view = ControllerImageView()
    view.set_controller("DDJ-XP2")
    view._geometry_checkbox.setChecked(True)
    view._on_marker_clicked("SHIFT")
    assert sent == []


def test_marker_click_sends_when_live_send_active(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    view = ControllerImageView()
    view.set_controller("DDJ-XP2")
    view._geometry_checkbox.setChecked(True)
    view._live_send._toggle_button.setChecked(True)
    view._on_marker_clicked("SHIFT")
    assert len(sent) == 1
    assert "LIVE SENT" in view._live_send_status.text()


def test_marker_click_with_no_raw_trigger_reports_status_without_sending(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    view._live_send._toggle_button.setChecked(True)
    view._on_marker_clicked("Jog wheel")  # a display-only marker, no catalog trigger
    assert sent == []
    assert "no raw MIDI trigger" in view._live_send_status.text()


def test_marker_click_on_right_pad_grid_sends_the_right_decks_trigger(monkeypatch):
    """Before this fix, a right-pad-grid marker resolved via the merged
    CellKey cell_key_for_geometry_label() collapses "Pad 3 (R)" into, so
    clicking it always sent the *left* grid's deck (1) trigger -- the same
    underlying bug reported for the Controller Emulator ("pressing a button
    on one deck also activates the second deck")."""
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append(a))
    view = ControllerImageView()
    view.set_controller("DDJ-XP2")
    view._geometry_checkbox.setChecked(True)
    view._live_send._toggle_button.setChecked(True)
    view._on_marker_clicked("Pad 3 (R)")
    assert len(sent) == 1
    entry = sent[0][1]
    assert entry.name.startswith("Deck 2 Pad 3")


def test_marker_click_on_left_pad_grid_still_sends_the_left_decks_trigger(monkeypatch):
    from djmidi.gui import live_send as live_send_mod

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append(a))
    view = ControllerImageView()
    view.set_controller("DDJ-XP2")
    view._geometry_checkbox.setChecked(True)
    view._live_send._toggle_button.setChecked(True)
    view._on_marker_clicked("Pad 3")
    assert len(sent) == 1
    entry = sent[0][1]
    assert entry.name.startswith("Deck 1 Pad 3")


def test_zoomable_view_emits_marker_clicked_only_for_a_real_click_not_a_pan():
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtCore import Qt as QtCore
    from PySide6.QtGui import QMouseEvent

    view = ControllerImageView()
    view.set_controller("DDJ-XP2")
    view._geometry_checkbox.setChecked(True)
    item = view._overlay_items_by_label.get("SHIFT")
    assert item is not None
    scene_pos = item.sceneBoundingRect().center()
    view_pos = view._view.mapFromScene(scene_pos)

    received = []
    view._view.markerClicked.connect(received.append)

    def press_release(end_pos):
        local = QPointF(view_pos)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, local, local, QtCore.MouseButton.LeftButton,
            QtCore.MouseButton.LeftButton, QtCore.KeyboardModifier.NoModifier,
        )
        view._view.mousePressEvent(press)
        end_local = QPointF(end_pos)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease, end_local, end_local, QtCore.MouseButton.LeftButton,
            QtCore.MouseButton.NoButton, QtCore.KeyboardModifier.NoModifier,
        )
        view._view.mouseReleaseEvent(release)

    # A drag of more than the click tolerance must not emit a click.
    from PySide6.QtCore import QPoint

    press_release(view_pos + QPoint(50, 50))
    assert received == []

    # Press and release at (near enough) the same spot is a genuine click.
    press_release(view_pos)
    assert received == ["SHIFT"]


def test_load_renders_an_absolute_path_reference_image(tmp_path):
    from PySide6.QtGui import QPixmap

    from djmidi.catalog._registry import ControllerDefinition, register
    from djmidi.gui.controller_image_view import ControllerImageView

    image_path = tmp_path / "abs-ref.png"
    QPixmap(64, 32).save(str(image_path), "PNG")
    register(ControllerDefinition(name="__AbsImageCtrl__", reference_image=str(image_path)))
    try:
        view = ControllerImageView()
        assert view.set_controller("__AbsImageCtrl__") is True
        assert view._pixmap_item is not None
        assert not view._pixmap_item.pixmap().isNull()
    finally:
        import djmidi.catalog as catalog_mod

        catalog_mod._registry._REGISTRY.pop("__AbsImageCtrl__", None)


# ─── "MIDI info" variant toggle ─────────────────────────────────────────────


def test_image_variants_resolves_clean_and_annotated_siblings():
    from djmidi.gui.controller_image_view import image_variants

    clean, annotated = image_variants("ddj-xp2.png")
    assert clean == ASSETS_DIR / "ddj-xp2.png"
    assert annotated == ASSETS_DIR / "ddj-xp2-midi.png"
    # Passing the annotated name resolves the same pair.
    assert image_variants("ddj-xp2-midi.png") == (clean, annotated)


def test_image_variants_none_and_absolute():
    from pathlib import Path

    from djmidi.gui.controller_image_view import image_variants

    assert image_variants(None) == (None, None)
    assert image_variants("") == (None, None)
    # An absolute path (Controller Setup attachment) has no annotated sibling.
    missing_abs = "/tmp/definitely/not/here.png"
    assert image_variants(missing_abs) == (None, None)
    assert image_variants(str(Path(missing_abs))) == (None, None)


def _register_midi_canonical(name: str) -> None:
    """A throwaway controller whose reference_image names the annotated
    '-midi' variant -- every *real* geometry controller was re-measured
    against its clean render (v0.47.54..58), so this scenario now only
    exists for a hand-registered definition."""
    register(ControllerDefinition(name=name, reference_image="ddj-xp2-midi.png"))


def test_midi_checkbox_enabled_when_both_variants_bundled_and_swaps_image():
    _register_midi_canonical("__MidiCanonicalCtl__")
    try:
        view = ControllerImageView()
        assert view.set_controller("__MidiCanonicalCtl__") is True
        assert view._midi_checkbox.isEnabled() is True
        # reference_image names the annotated variant -> box defaults on.
        assert view._midi_checkbox.isChecked() is True

        view._midi_checkbox.setChecked(False)
        clean_size = (view._pixmap_item.pixmap().width(), view._pixmap_item.pixmap().height())
        view._midi_checkbox.setChecked(True)
        annotated_size = (view._pixmap_item.pixmap().width(), view._pixmap_item.pixmap().height())
        assert annotated_size != clean_size  # a different image is now on screen
    finally:
        catalog._registry._REGISTRY.pop("__MidiCanonicalCtl__", None)


def test_geometry_overlay_only_offered_on_the_canonical_variant():
    """Every real geometry controller now names its clean render (v0.47.54..58),
    so 'Show real layout' is available by default and disabled once 'MIDI info'
    swaps the annotated crop in."""
    view = ControllerImageView()
    assert view.set_controller("DDJ-XP2") is True

    assert view._midi_checkbox.isChecked() is False  # canonical == clean
    assert view._geometry_checkbox.isEnabled() is True
    view._geometry_checkbox.setChecked(True)
    assert view._overlay_items != []

    view._midi_checkbox.setChecked(True)  # annotated == non-canonical
    assert view._geometry_checkbox.isEnabled() is False
    assert view._overlay_items == []  # checked but disabled -> not drawn


def test_midi_override_pins_the_user_choice_across_controller_switches():
    _register_midi_canonical("__MidiCanonicalA__")
    _register_midi_canonical("__MidiCanonicalB__")
    try:
        view = ControllerImageView()
        view.set_controller("__MidiCanonicalA__")  # canonical annotated -> box on
        assert view._midi_checkbox.isChecked() is True
        view._midi_checkbox.setChecked(False)  # user opts out of MIDI callouts
        view.set_controller("__MidiCanonicalB__")
        assert view._midi_checkbox.isChecked() is False
        view.set_controller("__MidiCanonicalA__")
        assert view._midi_checkbox.isChecked() is False
    finally:
        catalog._registry._REGISTRY.pop("__MidiCanonicalA__", None)
        catalog._registry._REGISTRY.pop("__MidiCanonicalB__", None)


def test_midi_checkbox_disabled_when_only_one_variant_bundled():
    """A Controller Setup attachment (absolute path) has no '-midi' sibling."""
    from pathlib import Path

    image_path = Path("/tmp/djmidi-test-onevariant.png")
    from PySide6.QtGui import QPixmap

    QPixmap(48, 24).save(str(image_path), "PNG")
    register(ControllerDefinition(name="__OneVariantCtrl__", reference_image=str(image_path)))
    try:
        view = ControllerImageView()
        assert view.set_controller("__OneVariantCtrl__") is True
        assert view._midi_checkbox.isEnabled() is False
    finally:
        catalog._registry._REGISTRY.pop("__OneVariantCtrl__", None)
        image_path.unlink(missing_ok=True)


# ─── Persistent "held down" overlay state (set_active) ──────────────────────


def _overlay_geometry_controller(view) -> str:
    """Pick a controller whose reference_image is the geometry-canonical one
    and turn the overlay on."""
    view.set_controller("DDJ-XP2")  # clean render == canonical since v0.47.54
    view._geometry_checkbox.setChecked(True)
    assert view._overlay_items_by_label
    return "DDJ-XP2"


def test_set_active_tints_and_restores_an_overlay_marker():
    from PySide6.QtGui import QColor

    from djmidi.gui.controller_image_view import _ACTIVE_COLOR

    view = ControllerImageView()
    _overlay_geometry_controller(view)
    item = view._overlay_items_by_label["Pad 1"]
    resting = QColor(item.brush().color())

    view.set_active("Pad 1", True)
    assert "Pad 1" in view._active_labels
    lit = view._overlay_items_by_label["Pad 1"].brush().color()
    assert (lit.red(), lit.green(), lit.blue()) == (
        QColor(_ACTIVE_COLOR).red(),
        QColor(_ACTIVE_COLOR).green(),
        QColor(_ACTIVE_COLOR).blue(),
    )
    assert view._overlay_items_by_label["Pad 1"].pen().color() == QColor(_ACTIVE_COLOR)

    view.set_active("Pad 1", False)
    assert "Pad 1" not in view._active_labels
    assert view._overlay_items_by_label["Pad 1"].brush().color() == resting


def test_flash_clear_falls_back_to_the_held_tint_not_the_resting_colour():
    from PySide6.QtGui import QColor

    from djmidi.gui.controller_image_view import _ACTIVE_COLOR

    view = ControllerImageView()
    _overlay_geometry_controller(view)
    view.set_active("Pad 1", True)
    view.flash_key("Pad 1")  # white pulse on top of the held state
    assert view._overlay_items_by_label["Pad 1"].brush().color() == QColor(255, 255, 255, 200)
    view._clear_flash("DDJ-XP2", "Pad 1")
    # still held -> amber, not the marker's resting colour
    got = view._overlay_items_by_label["Pad 1"].brush().color()
    assert (got.red(), got.green(), got.blue()) == (
        QColor(_ACTIVE_COLOR).red(),
        QColor(_ACTIVE_COLOR).green(),
        QColor(_ACTIVE_COLOR).blue(),
    )


def test_active_labels_cleared_on_controller_switch():
    view = ControllerImageView()
    _overlay_geometry_controller(view)
    view.set_active("Pad 1", True)
    view.set_controller("XDJ-XZ")
    assert view._active_labels == set()


def test_set_led_tints_a_marker_and_survives_an_input_release():
    from PySide6.QtGui import QColor

    from djmidi.gui.controller_image_view import _ACTIVE_COLOR

    view = ControllerImageView()
    _overlay_geometry_controller(view)
    item = view._overlay_items_by_label["Pad 1"]
    resting = QColor(item.brush().color())

    view.set_led("Pad 1", True)
    assert "Pad 1" in view._led_labels
    lit = view._overlay_items_by_label["Pad 1"].brush().color()
    assert (lit.red(), lit.green(), lit.blue()) == (
        QColor(_ACTIVE_COLOR).red(),
        QColor(_ACTIVE_COLOR).green(),
        QColor(_ACTIVE_COLOR).blue(),
    )

    # A phantom input hold + release must not clear the software-driven LED.
    view.set_active("Pad 1", True)
    view.set_active("Pad 1", False)
    assert "Pad 1" in view._led_labels
    still_lit = view._overlay_items_by_label["Pad 1"].brush().color()
    assert (still_lit.red(), still_lit.green(), still_lit.blue()) == (
        QColor(_ACTIVE_COLOR).red(),
        QColor(_ACTIVE_COLOR).green(),
        QColor(_ACTIVE_COLOR).blue(),
    )

    view.set_led("Pad 1", False)
    assert "Pad 1" not in view._led_labels
    assert view._overlay_items_by_label["Pad 1"].brush().color() == resting


def test_led_labels_cleared_on_controller_switch():
    view = ControllerImageView()
    _overlay_geometry_controller(view)
    view.set_led("Pad 1", True)
    view.set_controller("XDJ-XZ")
    assert view._led_labels == set()


def test_overlay_draws_a_jog_notch_that_spin_jog_turns_in_place():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")  # has a "Jog wheel" geometry entry
    view._geometry_checkbox.setChecked(True)
    assert "Jog wheel" in view._overlay_jog_notches
    notch = view._overlay_jog_notches["Jog wheel"]
    before = (notch.line().x2(), notch.line().y2())

    view.spin_jog("Jog wheel", 15)
    assert view._jog_angles["Jog wheel"] == 15 * layout_view_mod._JOG_DEGREES_PER_TICK
    assert view._overlay_jog_notches["Jog wheel"] is notch  # same item, turned in place
    assert (notch.line().x2(), notch.line().y2()) != before


def test_spin_jog_zero_delta_and_unknown_label_are_safe_noops():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    view.spin_jog("Jog wheel", 0)
    assert "Jog wheel" not in view._jog_angles
    view.spin_jog("No Such Control", 5)  # accumulates but draws nothing, no raise
    assert view._geometry_rect("No Such Control") is None


def test_jog_angles_cleared_on_controller_switch():
    view = ControllerImageView()
    view.set_controller("XDJ-XZ")
    view._geometry_checkbox.setChecked(True)
    view.spin_jog("Jog wheel", 10)
    view.set_controller("DDJ-XP2")
    assert view._jog_angles == {}
