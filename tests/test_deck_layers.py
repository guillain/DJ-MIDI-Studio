from djmidi.deck_layers import DeckLayers, controller_for_port
from djmidi.midi_io import MidiEvent

# Real switches with Serato running, 2026-11-27 (live set recording).
XZ_TO_3 = [("XDJ-XZ (1)", "Control Change", "1", "102", "0"), ("XDJ-XZ (1)", "Control Change", "3", "102", "127")]
XZ_TO_1 = [("XDJ-XZ (1)", "Control Change", "3", "102", "0"), ("XDJ-XZ (1)", "Control Change", "1", "102", "127")]
XP2_TO_3 = [("DDJ-XP2", "Note On", "3", "114", "127"), ("DDJ-XP2", "Note On", "1", "60", "0"),
            ("DDJ-XP2", "Note On", "3", "60", "127"), ("DDJ-XP2", "Note On", "3", "114", "0")]


def _feed(layers, rows):
    return [layers.feed(port, "in", kind, channel, data1, data2) for port, kind, channel, data1, data2 in rows]


def test_ports_name_their_controller():
    assert controller_for_port("XDJ-XZ (2)") == "XDJ-XZ"
    assert controller_for_port("DDJ-XP2") == "DDJ-XP2"
    assert controller_for_port("IAC Driver Bus 1") == ""


def test_the_xz_and_xp2_switches_are_read_and_a_difference_is_said():
    layers = DeckLayers()
    _feed(layers, [("DDJ-XP2", "Note On", "8", "68", "127")])  # the XP2 is here, on its first decks
    assert layers.summary() == ""
    assert any(_feed(layers, XZ_TO_3))
    assert layers.decks == {"XDJ-XZ": {"left": 3}}
    assert "is DDJ-XP2 on deck 3 too" in layers.summary()
    _feed(layers, XP2_TO_3)
    assert layers.decks["DDJ-XP2"] == {"left": 3}
    assert layers.differences() == [] and "⚠" not in layers.summary()
    _feed(layers, XZ_TO_1)
    assert layers.differences() == [("left", "DDJ-XP2", 3, "XDJ-XZ", 1)]
    assert "⚠ left side: DDJ-XP2 is on deck 3, XDJ-XZ on deck 1" in layers.summary()


def test_other_messages_and_outputs_change_nothing():
    layers = DeckLayers()
    assert not layers.feed("XDJ-XZ (1)", "out", "Control Change", "3", "102", "127")
    assert not layers.feed("XDJ-XZ (2)", "in", "Control Change", "5", "102", "127")  # FX FREQUENCY HI
    assert not layers.feed("IAC Driver Bus 1", "in", "Note On", "3", "60", "127")
    assert layers.decks == {}


def test_the_live_monitor_shows_the_decks_line():
    from djmidi.gui.live_monitor import LiveMonitorView

    view = LiveMonitorView()
    for port, kind, channel, data1, data2 in XZ_TO_3:
        view._append_event(MidiEvent("in", channel, kind, data1, data2, 0.0, port))
    assert not view.decks_label.isHidden()
    assert "XDJ-XZ 3 | ?" in view.decks_label.text()


# The right side, captured 2026-11-28 with Serato running.
XP2_RIGHT_TO_4 = [("DDJ-XP2", "Note On", "4", "114", "127"), ("DDJ-XP2", "Note On", "2", "60", "0"),
                  ("DDJ-XP2", "Note On", "4", "60", "127"), ("DDJ-XP2", "Note On", "4", "114", "0")]
XZ_RIGHT_TO_4 = [("XDJ-XZ (1)", "Control Change", "2", "102", "0"), ("XDJ-XZ (1)", "Control Change", "4", "102", "127")]


def test_the_right_side_and_the_short_alert():
    layers = DeckLayers()
    _feed(layers, [("DDJ-XP2", "Note On", "8", "68", "127")])
    _feed(layers, XZ_RIGHT_TO_4)
    assert layers.alert() == "⚠ XDJ-XZ on deck 4 · DDJ-XP2 too?"
    _feed(layers, XP2_RIGHT_TO_4)
    assert layers.decks == {"XDJ-XZ": {"right": 4}, "DDJ-XP2": {"right": 4}} and layers.alert() == ""
    _feed(layers, XZ_TO_3)
    _feed(layers, XP2_TO_3)
    _feed(layers, XZ_TO_1)
    assert layers.alert() == "⚠ DDJ-XP2 on deck 3 · XDJ-XZ on deck 1"


def test_the_alert_reaches_stage_mode_and_a_window_over_other_apps(monkeypatch):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    monitor = window.live_monitor_view
    for port, kind, channel, data1, data2 in XZ_TO_3:
        monitor._append_event(MidiEvent("in", channel, kind, data1, data2, 0.0, port))
    monitor._append_event(MidiEvent("in", "8", "Note On", "68", "127", 0.0, "DDJ-XP2"))
    for port, kind, channel, data1, data2 in XP2_TO_3[:3]:
        monitor._append_event(MidiEvent("in", channel, kind, data1, data2, 0.0, port))
    assert monitor.deck_alert == ""  # both on deck 3
    for port, kind, channel, data1, data2 in XZ_TO_1:
        monitor._append_event(MidiEvent("in", channel, kind, data1, data2, 0.0, port))
    assert monitor.deck_alert == "⚠ DDJ-XP2 on deck 3 · XDJ-XZ on deck 1"
    toast = window._deck_alert_toast
    assert toast is not None and toast.isVisible() and toast.label.text() == monitor.deck_alert
    for port, kind, channel, data1, data2 in [("DDJ-XP2", "Note On", "3", "60", "0"), ("DDJ-XP2", "Note On", "1", "60", "127")]:
        monitor._append_event(MidiEvent("in", channel, kind, data1, data2, 0.0, port))
    assert monitor.deck_alert == "" and not toast.isVisible()
