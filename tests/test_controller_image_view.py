from PySide6.QtGui import QPainter, QTransform

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
