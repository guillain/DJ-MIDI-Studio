from PySide6.QtGui import QColor, QPainter, QTransform

from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
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
    assert _resolve_image_path("ddj-xp2.png") == ASSETS_DIR / "ddj-xp2.png"
    abs_path = "/tmp/custom/minipad.png"
    assert _resolve_image_path(abs_path) == Path(abs_path)


def test_geometry_checkbox_disabled_for_controller_without_geometry():
    view = ControllerImageView()
    assert view.set_controller("DDJ-1000") is True  # has a reference image but no modeled geometry
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
    view.set_controller("DDJ-1000")
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
