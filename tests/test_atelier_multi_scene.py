"""Atelier scenes across several controllers (issue #427)."""

import pytest
from PySide6.QtCore import Qt

from djmidi import catalog
from djmidi.atelier.features import features_for
from djmidi.atelier.scene import SceneCoverage, scene_coverage
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui.atelier_view import AtelierView

SYNC = "deck.beat-sync@1"
CLUB = ControllerSyncSet("DDJ-XP2", "DDJ-XP2", (SyncMessage("Note On", 1, 88, 127),), scene="Club")


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _xdj_feature():
    return next(feature for feature in features_for("XDJ-XZ") if feature.led is not None)


def _view(sets):
    view = AtelierView(
        sync_set_provider=lambda controller, scene: sets.get((controller, scene)),
        scene_names_provider=lambda: ["Default", "Club"],
        active_scene_provider=lambda: "Club",
    )
    view.controller_combo.setCurrentText("DDJ-XP2")
    return view


def _light(view, controller, feature_id):
    view.controller_combo.setCurrentText(controller)
    assert view.select_feature(feature_id)
    view.set_led_choice(2)  # on


def test_scene_coverage_lists_saved_and_unsaved_controllers_in_order():
    sets = {("DDJ-XP2", "Club"): CLUB}
    coverage = scene_coverage(
        ["XDJ-XZ", "DDJ-XP2", "DDJ-1000"], "Club", lambda c, s: sets.get((c, s)), unsaved=["XDJ-XZ"]
    )
    assert coverage == [SceneCoverage("XDJ-XZ", False, True), SceneCoverage("DDJ-XP2", True, False)]
    assert scene_coverage(["DDJ-XP2"], "Default", lambda c, s: sets.get((c, s))) == []


def test_switching_controller_keeps_unsaved_edits():
    view = _view({("DDJ-XP2", "Club"): CLUB})
    _light(view, "DDJ-XP2", SYNC)
    view.set_led_choice(1)
    assert view.is_dirty
    view.controller_combo.setCurrentText("XDJ-XZ")
    assert not view.is_dirty
    view.controller_combo.setCurrentText("DDJ-XP2")
    assert view.is_dirty
    assert view.scene.led_value(SYNC) == 0
    assert "Unsaved changes kept" in view.status_label.text()
    assert "DDJ-XP2 (unsaved)" in view.coverage_label.text()


def test_reload_saved_drops_only_this_controllers_draft():
    view = _view({("DDJ-XP2", "Club"): CLUB})
    xdj = _xdj_feature()
    _light(view, "XDJ-XZ", xdj.id)
    _light(view, "DDJ-XP2", SYNC)
    view.set_led_choice(1)
    view.reload_saved()
    assert not view.is_dirty and view.scene.led_value(SYNC) == 127
    assert view.unsaved_controllers() == ["XDJ-XZ"]


def test_coverage_label_and_bold_controllers():
    view = _view({("DDJ-XP2", "Club"): CLUB})
    assert view.coverage_label.text() == "This scene covers: DDJ-XP2"
    index = view.controller_combo.findText("DDJ-XP2")
    assert view.controller_combo.itemData(index, Qt.ItemDataRole.FontRole).bold()
    view.scene_combo.setCurrentText("Default")
    assert view.coverage_label.text() == "No controller has a set for this scene yet."
    assert not view.send_all_button.isEnabled() and not view.save_all_button.isEnabled()


def test_save_all_saves_every_unsaved_controller_of_the_scene():
    sets = {("DDJ-XP2", "Club"): CLUB}
    view = _view(sets)
    saved = []
    view.saveRequested.connect(lambda sync_set: (saved.append(sync_set), sets.__setitem__(sync_set.key, sync_set)))
    xdj = _xdj_feature()
    _light(view, "XDJ-XZ", xdj.id)
    _light(view, "DDJ-XP2", SYNC)
    view.set_led_choice(1)
    assert view.save_all_button.isEnabled()
    result = view.save_all()
    assert {s.controller for s in result} == {"XDJ-XZ", "DDJ-XP2"}
    assert all(s.scene == "Club" for s in result) and len(saved) == 2
    assert view.unsaved_controllers() == [] and not view.save_all_button.isEnabled()
    assert sets[("DDJ-XP2", "Club")].messages[0].data2 == 0
    assert sets[("DDJ-XP2", "Club")].output_port == "DDJ-XP2"  # the stored port is kept
    assert "XDJ-XZ" in view.coverage_label.text() and "unsaved" not in view.coverage_label.text()


def test_save_keeps_the_saved_scene_when_saving_reloads_the_view():
    sets = {("DDJ-XP2", "Club"): CLUB}
    view = _view(sets)

    def store(sync_set):
        sets[sync_set.key] = sync_set
        view.refresh_scenes()  # what MainWindow's save does

    view.saveRequested.connect(store)
    _light(view, "DDJ-XP2", SYNC)
    view.set_led_choice(1)
    view.save()
    assert not view.is_dirty
    assert view.scene.led_value(SYNC) == 0


def test_send_all_sends_drafts_and_stored_sets_of_the_scene():
    view = _view({("DDJ-XP2", "Club"): CLUB, ("DDJ-1000", "Default"): ControllerSyncSet("DDJ-1000")})
    sent = []
    view.sendAllRequested.connect(sent.append)
    xdj = _xdj_feature()
    _light(view, "XDJ-XZ", xdj.id)
    sets = view.send_all()
    assert [s.controller for s in sets] == [s.controller for s in view.coverage()]
    assert {s.controller for s in sets} == {"DDJ-XP2", "XDJ-XZ"}
    assert sent == [sets]
    xdj_set = next(s for s in sets if s.controller == "XDJ-XZ")
    assert xdj_set.scene == "Club" and xdj_set.messages


def test_main_window_sends_every_set(monkeypatch):
    from djmidi.gui import main_window as mw

    window = mw.MainWindow()
    calls = []
    monkeypatch.setattr(mw, "list_output_ports", lambda: ["DDJ-XP2", "XDJ-XZ"])
    monkeypatch.setattr(mw, "run_sync", lambda sets, ports: calls.append((list(sets), ports)) or [])
    window.atelier_view.sendAllRequested.emit([CLUB, None])
    assert calls and [s.controller for s in calls[0][0]] == ["DDJ-XP2"]
