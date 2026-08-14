from seratomidiconf import catalog
from seratomidiconf.catalog._registry import ControllerDefinition, register
from seratomidiconf.gui.controller_image_view import (
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

