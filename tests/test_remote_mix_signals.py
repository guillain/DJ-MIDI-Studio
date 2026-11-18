"""Signals between DJs (remote mix, phase 10)."""

import queue

from djmidi.gui.remote_mix_signals import SignalsPanel
from djmidi.midi_io import MidiEvent
from djmidi.remote_mix import signals


def _note(channel="7", note="5", velocity="127", event_type="Note On"):
    return MidiEvent("in", channel, event_type, note, velocity, 0.0, "DDJ-XP2")


def test_a_signal_is_shown_once_and_never_to_its_sender():
    mine, theirs = signals.SignalBoard(0), signals.SignalBoard(1)
    message = mine.send("next")
    assert theirs.receive(message) == signals.Signal("next", 0)
    assert theirs.receive(message) is None  # the two repeats
    assert mine.receive(message) is None
    assert theirs.receive({"k": "sig", "s": "unknown", "from": 0, "n": 9}) is None
    assert theirs.receive({"k": "mix", "c": {}}) is None


def test_only_a_pad_press_binds_and_pads_survive_a_restart(tmp_path):
    assert signals.pad_from_event(_note(event_type="Control Change")) is None
    assert signals.pad_from_event(_note(velocity="0")) is None  # a release
    pads = signals.SignalPads()
    pads.bind("drop", signals.pad_from_event(_note()))
    pads.bind("love", signals.pad_from_event(_note()))  # one pad, one signal
    assert pads.bindings == {"love": signals.PadTrigger("7", "5")}
    pads.save(tmp_path / "s.json")
    again = signals.SignalPads.load(tmp_path / "s.json")
    assert again.fired(_note()) == "love" and again.fired(_note(note="6")) is None


def test_the_panel_sends_by_button_or_pad_and_shows_what_arrives(tmp_path):
    now = [100.0]
    sent = []
    panel = SignalsPanel(
        pads_path=tmp_path / "s.json", name_of=lambda dj: ["Host", "Alex"][dj], beats_to_phrase=lambda: 7,
        clock=lambda: now[0],
    )
    try:
        assert not panel.buttons["next"].isEnabled()  # not connected yet
        panel.attach(0, sent.append)
        panel.buttons["next"].click()
        assert len(sent) == signals.REPEATS and sent[0]["s"] == "next"

        panel.learn_buttons["drop"].click()
        assert not panel.feed_midi_event(_note(event_type="Control Change"))
        assert panel.feed_midi_event(_note())
        assert panel.learn_buttons["drop"].text() == "ch7 note 5"
        sent.clear()
        assert panel.feed_midi_event(_note()) and sent[0]["s"] == "drop"
        assert signals.SignalPads.load(tmp_path / "s.json").bindings["drop"] == signals.PadTrigger("7", "5")

        alex = signals.SignalBoard(1)
        panel.receive(alex.send("drop"))
        assert not panel.banner.isHidden()
        assert panel.banner.text() == "Alex: Drop on the next phrase! (in 7 beats)"
        now[0] += signals.SHOW_S + 1
        panel._tick()
        assert panel.banner.isHidden()
    finally:
        panel.close()


def test_the_dialog_routes_signals_and_the_hub_relays_them(tmp_path):
    from datetime import datetime

    from djmidi.gui.remote_mix_dialog import RemoteMixDialog
    from djmidi.remote_mix import probe

    sessions = []

    class Session:
        def __init__(self, **kwargs):
            self.port, self.peer, self.leading, self.remote_leading = kwargs["port"], None, True, None
            self.follow_error = self.error = None
            self.my_id, self.roster, self.inbox = 0, {0: "Host", 1: "Alex"}, queue.Queue()
            sessions.append(self)

        def start(self):
            pass

        def stop(self):
            pass

        def send(self, message):
            pass

        def stats(self):
            return probe.summarise([], 0)

    dialog = RemoteMixDialog(
        session_factory=Session, link_factory=lambda: None, addresses=list, report_dir=lambda: tmp_path,
        now=lambda: datetime(2026, 11, 21, 21, 0),  # noqa: DTZ001
        controls_path=tmp_path / "c.json",
    )
    try:
        dialog.start_button.click()
        session = sessions[0]
        dialog.refresh()
        assert dialog.signals_panel.board is not None
        session.inbox.put(signals.SignalBoard(1).send("your_turn"))
        dialog.refresh()
        assert dialog.signals_panel.shown == signals.Signal("your_turn", 1)
        assert "Alex: Your turn" == dialog.signals_panel.banner.text()
    finally:
        dialog.close()
