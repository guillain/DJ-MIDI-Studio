"""A scene played to the DJ software: its lit buttons tapped through a
virtual port, so the software changes state (not only the controller's LEDs)."""

import pytest

from djmidi import catalog
from djmidi.atelier.scene import Scene
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui.atelier_view import AtelierView

SYNC_ON = SyncMessage("Note On", 1, 88, 127)
SYNC_OFF_DECK2 = SyncMessage("Note On", 2, 88, 0)
STRANGER = SyncMessage("Control Change", 16, 120, 5)
CLUB = ControllerSyncSet("DDJ-XP2", "DDJ-XP2", (SYNC_ON, SYNC_OFF_DECK2, STRANGER), scene="Club")


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_only_lit_buttons_become_taps():
    scene = Scene.from_sync_set(CLUB, "DDJ-XP2")
    assert scene.software_taps() == (
        SyncMessage("Note On", 1, 88, 127),
        SyncMessage("Note Off", 1, 88, 0),
    )


def test_the_software_set_is_aimed_at_the_chosen_port():
    sync_set = Scene.from_sync_set(CLUB, "DDJ-XP2").software_sync_set("IAC Driver Bus 1", "Club")
    assert sync_set.output_port == "IAC Driver Bus 1" and sync_set.scene == "Club"
    assert len(sync_set.messages) == 2


def _view() -> AtelierView:
    view = AtelierView(
        sync_set_provider=lambda controller, scene: CLUB if (controller, scene) == ("DDJ-XP2", "Club") else None,
        scene_names_provider=lambda: ["Default", "Club"],
        active_scene_provider=lambda: "Club",
    )
    view.ports_provider = lambda: ["PIONEER DDJ-XP2", "IAC Driver Bus 1"]
    view.refresh_software_ports()
    view.controller_combo.setCurrentText("DDJ-XP2")
    return view


def test_controllers_are_not_offered_as_the_software_port():
    view = _view()
    ports = [view.software_port_combo.itemText(i) for i in range(view.software_port_combo.count())]
    assert ports == ["IAC Driver Bus 1"] and view.software_send_button.isEnabled()


def test_sending_emits_the_taps_for_the_software_port():
    view = _view()
    sent = []
    view.softwareSendRequested.connect(sent.append)
    view.send_to_software()
    assert [s.output_port for s in sent] == ["IAC Driver Bus 1"]
    assert sent[0].messages[0] == SyncMessage("Note On", 1, 88, 127)


def test_no_port_disables_the_button():
    view = _view()
    view.ports_provider = lambda: ["PIONEER DDJ-XP2"]
    view.refresh_software_ports()
    assert not view.software_send_button.isEnabled()
    assert view.send_to_software() is None


def test_main_window_sends_only_to_that_port(monkeypatch):
    from djmidi.gui import main_window as mw

    window = mw.MainWindow()
    calls = []
    monkeypatch.setattr(mw, "list_output_ports", lambda: ["DDJ-XP2", "IAC Driver Bus 1"])
    monkeypatch.setattr(mw, "run_sync", lambda sets, ports: calls.append((list(sets), ports)) or [])
    taps = Scene.from_sync_set(CLUB, "DDJ-XP2").software_sync_set("IAC Driver Bus 1", "Club")
    window.atelier_view.softwareSendRequested.emit(taps)
    assert calls == [([taps], ["IAC Driver Bus 1"])]


def test_a_vanished_port_never_falls_back_to_the_controller(monkeypatch):
    from djmidi.gui import main_window as mw

    window = mw.MainWindow()
    calls = []
    monkeypatch.setattr(mw, "list_output_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(mw, "run_sync", lambda sets, ports: calls.append(sets) or [])
    taps = Scene.from_sync_set(CLUB, "DDJ-XP2").software_sync_set("IAC Driver Bus 1", "Club")
    window.atelier_view.softwareSendRequested.emit(taps)
    assert calls == []
