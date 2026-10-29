"""Placing a profile's controls on a picture (issue #363)."""

import json

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from djmidi import catalog
from djmidi.catalog._registry import ControlInfo, ControllerDefinition
from djmidi.catalog.profile import (
    find_user_profile_file,
    load_controller_profile,
    save_controller_profile,
    save_profile_layout,
    uninstall_user_profile,
)
from djmidi.gui import geometry
from djmidi.gui.geometry_editor import (
    DEFAULT_MARKER_FRACTION,
    GeometryEditorDialog,
    marker_from_drag,
)

NAME = "Test Profile"


def _install(tmp_path) -> object:
    entries = [
        ControlInfo(NAME, "Deck", "Sync", "NOTE", ("1",), "88"),
        ControlInfo(NAME, "Deck", "Sync +SHIFT", "NOTE", ("1",), "92"),
        ControlInfo(NAME, "PAD", "Pad 1 (HotCue)", "NOTE", ("8",), "0"),
        ControlInfo(NAME, "PAD", "Pad 1 (Sampler)", "NOTE", ("8",), "48"),
        ControlInfo(NAME, "PAD", "Pad 2 (HotCue)", "NOTE", ("8",), "1"),
    ]
    definition = ControllerDefinition(name=NAME, static_entries=entries, section_order=("Deck", "PAD"))
    path = save_controller_profile(definition, tmp_path / "Controllers" / "test-profile.json")
    load_controller_profile(path, replace=True)
    return path


def _picture(tmp_path, name="picture.png"):
    image = QImage(1000, 500, QImage.Format.Format_RGB32)
    image.fill(QColor("#303030"))
    path = tmp_path / name
    image.save(str(path))
    return path


def test_marker_from_a_drag_or_a_click():
    drag = marker_from_drag("A", QPointF(300, 200), QPointF(100, 100), 1000, 500, "rect", "#fff")
    assert drag == ("A", 0.1, 0.2, 0.2, 0.2, "rect", "#fff")
    click = marker_from_drag("B", QPointF(500, 250), QPointF(502, 251), 1000, 500, "circle", "#fff")
    assert click[3] == pytest.approx(DEFAULT_MARKER_FRACTION) and click[1] == pytest.approx(0.48)
    clamped = marker_from_drag("C", QPointF(900, 400), QPointF(1200, 700), 1000, 500, "rect", "#fff")
    assert clamped[1:5] == pytest.approx((0.9, 0.8, 0.1, 0.2))


def test_profile_geometry_round_trips_and_is_validated(tmp_path):
    path = _install(tmp_path)
    definition = save_profile_layout(path, "/pics/p.png", [("Sync", 0.1, 0.2, 0.05, 0.05, "circle", "#4a90d9")])
    assert definition.marker_geometry == (("Sync", 0.1, 0.2, 0.05, 0.05, "circle", "#4a90d9"),)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["controller"]["geometry"]["Sync"]["shape"] == "circle"
    assert raw["controller"]["reference_image"] == "/pics/p.png"
    raw["controller"]["geometry"]["Sync"]["x"] = 1.5
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="fractions"):
        load_controller_profile(path, replace=True)
    assert find_user_profile_file(NAME, tmp_path / "Controllers") == path


def test_profile_geometry_feeds_the_views_but_never_a_built_in(tmp_path):
    path = _install(tmp_path)
    markers = [("Sync", 0.1, 0.2, 0.05, 0.05, "rect", "#fff"), ("Pad 1", 0.3, 0.6, 0.1, 0.1, "rect", "#fff")]
    save_profile_layout(path, None, markers)
    geometry.sync_profile_geometry()
    assert set(geometry.CONTROL_GEOMETRY[NAME]) == {"Sync", "Pad 1"}
    assert geometry.resolve_geometry_label(NAME, "Sync +SHIFT") == "Sync"
    assert geometry.resolve_geometry_label(NAME, "Pad 1 (Sampler)") == "Pad 1"
    built_in = dict(geometry.CONTROL_GEOMETRY["DDJ-XP2"])
    xp2 = catalog.get_definition("DDJ-XP2")
    fake = (("X", 0, 0, 0.1, 0.1, "rect", "#fff"),)
    catalog._registry._REGISTRY["DDJ-XP2"] = type(xp2)(**{**xp2.__dict__, "marker_geometry": fake})
    geometry.sync_profile_geometry()
    assert geometry.CONTROL_GEOMETRY["DDJ-XP2"] == built_in
    uninstall_user_profile(NAME, tmp_path / "Controllers")
    geometry.sync_profile_geometry()
    assert NAME not in geometry.CONTROL_GEOMETRY


def test_editor_places_controls_in_order_and_saves_with_a_copied_picture(tmp_path):
    path = _install(tmp_path)
    dialog = GeometryEditorDialog(NAME, path)
    assert [cell.label for cell in dialog._cells] == ["Sync", "Pad 1", "Pad 2"]  # one per physical control
    assert not dialog.save_button.isEnabled()  # no picture yet
    dialog.set_picture(_picture(tmp_path))
    assert dialog.save_button.isEnabled()
    first = dialog._current_label()
    dialog._on_dragged(QPointF(100, 100), QPointF(200, 200))
    assert first in {marker[0] for marker in dialog.markers}
    assert dialog._current_label() != first  # moved on to the next unplaced control
    assert dialog.status.text() == "1 of 3 controls placed."
    dialog._remove_current()  # nothing placed on the new one: no-op
    dialog.control_list.setCurrentRow(0)
    dialog.shape_combo.setCurrentIndex(dialog.shape_combo.findData("circle"))
    assert dialog.markers[0][5] == "circle"
    saved = []
    dialog.saved.connect(saved.append)
    assert dialog.save() and saved == [NAME]
    copied = tmp_path / "Controllers" / "test-profile-picture.png"
    assert copied.is_file()
    assert catalog.get_definition(NAME).reference_image == str(copied)
    assert NAME in geometry.CONTROL_GEOMETRY

    reopened = GeometryEditorDialog(NAME, path)
    assert len(reopened.markers) == 1 and reopened._picture == copied


def test_main_window_places_controls_of_an_installed_profile(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from djmidi import user_paths
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        infos = []
        monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args[2]))
        window.controller_image_view.set_controller("DDJ-XP2")
        assert window.open_geometry_editor() is None and "installed profile" in infos[0]
        assert not window.controller_image_view._place_button.isEnabled()

        profile = _install(user_paths.controllers_dir().parent / "x")
        target = user_paths.controllers_dir() / profile.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(profile.read_text(encoding="utf-8"), encoding="utf-8")
        window._on_controller_applied(NAME)
        window.controller_image_view.set_controller(NAME)
        assert window.controller_image_view._place_button.isEnabled()
        dialog = window.open_geometry_editor()
        dialog.set_picture(_picture(tmp_path))
        dialog._on_dragged(QPointF(10, 10), QPointF(80, 80))
        dialog.save()
        assert window.statusBar().currentMessage() == f"Layout of '{NAME}' saved."
        assert window.controller_image_view._geometry_checkbox.isEnabled()
    finally:
        window.close()
