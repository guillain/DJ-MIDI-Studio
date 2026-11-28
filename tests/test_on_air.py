"""Studio-style ● REC lamps: every recording shows, on every tab and in Stage Mode."""

from djmidi.gui.main_window import MainWindow
from djmidi.gui.on_air import Lamp, OnAirLamps, elapsed_text


def test_elapsed_text():
    assert elapsed_text(0) == "00:00"
    assert elapsed_text(754) == "12:34"
    assert elapsed_text(3 * 3600 + 5) == "3:00:05"


def test_lamps_light_count_blink_and_go_out():
    now = [100.0]
    lamps = OnAirLamps(clock=lambda: now[0])
    assert lamps.isHidden()
    lamps.update_lamps([Lamp("live_set", "REC set", "tip", started=40.0)])
    assert not lamps.isHidden() and lamps.keys == ["live_set"]
    assert lamps.text_of("live_set") == "● REC set  01:00"
    lamps._on_blink()
    assert lamps.text_of("live_set").startswith("○ REC set")
    now[0] = 130.0
    lamps.update_lamps([Lamp("live_set", "REC set", "tip", started=40.0), Lamp("setup", "REC setup", "tip")])
    assert lamps.text_of("setup").endswith("00:00")  # counted from when it lit
    clicked = []
    lamps.lampClicked.connect(clicked.append)
    lamps._buttons["setup"].click()
    assert clicked == ["setup"]
    lamps.update_lamps([])
    assert lamps.isHidden() and lamps.keys == []


def test_main_window_lights_a_lamp_per_recording(monkeypatch):
    window = MainWindow()
    assert window.on_air_lamps() == []
    window._record_button.blockSignals(True)  # the lamp only reads the button; no real ● Rec
    window._record_button.setChecked(True)
    window.live_monitor_view._recorder = type(
        "R", (), {"is_recording": True, "manifest": {"started": 1.0}}
    )()
    window.refresh_on_air()
    assert window.on_air.keys == ["live_set", "setup"]
    assert "REC set" in window.on_air.text_of("live_set")
    shown = []
    monkeypatch.setattr(window, "_show_tool_dock", shown.append)
    window._on_air_lamp_clicked("live_set")
    assert shown == ["monitor"]
    window.live_monitor_view._recorder = None
    window._record_button.setChecked(False)
    window.refresh_on_air()
    assert window.on_air.isHidden()


def test_auto_recording_waits_for_a_controller_and_starts_once(monkeypatch):
    from djmidi.plugins.preferences import PluginPreferences

    preferences = PluginPreferences()
    assert preferences.record_live_sets is False
    preferences.record_live_sets = True
    assert PluginPreferences.from_json(preferences.to_json()).record_live_sets is True
    window = MainWindow()
    results = [None, "path"]
    monkeypatch.setattr(window.live_monitor_view, "start_recording", lambda: results.pop(0))
    retries = []
    monkeypatch.setattr("djmidi.gui.main_window.QTimer.singleShot", lambda ms, fn: retries.append(ms))
    assert window.start_auto_recording() is False and retries == [3000]  # no controller yet
    assert window.start_auto_recording() is True
    assert window.start_auto_recording() is True and retries == [3000]  # once per launch
