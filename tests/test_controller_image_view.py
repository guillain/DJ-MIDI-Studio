from PySide6.QtGui import QPainter, QTransform

from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
from djmidi.gui.controller_image_view import (
    ASSETS_DIR,
    IMAGES,
    ControllerImageView,
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


def test_ddj_1000_is_last_and_has_reference_image():
    assert catalog.CONTROLLER_NAMES[-1] == "DDJ-1000"
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
