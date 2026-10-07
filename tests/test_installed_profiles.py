"""Installing a controller profile built in Controller Setup (issue #175
phase 2): a JSON file in the user's Controllers folder, loaded at launch."""

import json

from PySide6.QtGui import QPixmap

from djmidi import catalog, user_paths
from djmidi.catalog._registry import ControlInfo
from djmidi.catalog.codegen import build_definition
from djmidi.catalog.profile import load_user_profiles, save_controller_profile

NAME = "__InstalledProfileTest__"


def _cleanup():
    catalog._registry._REGISTRY.pop(NAME, None)


def test_saved_profile_loads_back_with_its_entries(tmp_path):
    rows = [
        ControlInfo(NAME, "DECK", "PLAY", "NOTE", ("1",), "11"),
        ControlInfo(NAME, "DECK", "PLAY", "NOTE", ("2",), "11"),
        ControlInfo(NAME, "PADS", "Pad 1", "NOTE", ("1",), "36"),
    ]
    try:
        save_controller_profile(build_definition(NAME, rows), tmp_path / "p.json")
        loaded, errors = load_user_profiles(tmp_path)
        assert loaded == [NAME] and errors == {}
        definition = catalog.get_definition(NAME)
        assert definition.plugin_id.startswith("user.")
        assert {(e.name, e.channels) for e in definition.static_entries} == {("PLAY", ("1", "2")), ("Pad 1", ("1",))}
    finally:
        _cleanup()


def test_a_profile_never_replaces_a_built_in_controller(tmp_path):
    definition = build_definition("DDJ-XP2", [ControlInfo("DDJ-XP2", "X", "Y", "NOTE", ("1",), "1")])
    save_controller_profile(definition, tmp_path / "fake.json")
    entries_before = len(catalog.static_entries("DDJ-XP2"))
    loaded, errors = load_user_profiles(tmp_path)
    assert loaded == [] and "built-in" in next(iter(errors.values()))
    assert len(catalog.static_entries("DDJ-XP2")) == entries_before


def test_install_saves_the_profile_and_a_copy_of_its_picture(tmp_path):
    from djmidi.gui.controller_setup import ControllerSetupView

    picture = tmp_path / "photo.png"
    QPixmap(40, 20).save(str(picture), "PNG")
    view = ControllerSetupView()
    view._name_edit.setText(NAME)
    view._rows = [ControlInfo(NAME, "DECK", "PLAY", "NOTE", ("1",), "11")]
    view._sources = ["manual"]
    view._devices = [""]
    view._reference_image = str(picture)
    try:
        path = view._apply()
        assert path.parent == user_paths.controllers_dir()
        document = json.loads(path.read_text())
        image = document["controller"]["reference_image"]
        assert image.startswith(str(user_paths.controllers_dir())) and image.endswith(".png")
        assert NAME in catalog.CONTROLLER_NAMES
    finally:
        _cleanup()


def test_main_window_loads_installed_profiles_at_launch():
    from djmidi.gui.main_window import MainWindow

    save_controller_profile(
        build_definition(NAME, [ControlInfo(NAME, "DECK", "PLAY", "NOTE", ("1",), "11")]),
        user_paths.controllers_dir() / "installed.json",
    )
    try:
        window = MainWindow()
        assert NAME in catalog.CONTROLLER_NAMES
        window.close()
    finally:
        _cleanup()
