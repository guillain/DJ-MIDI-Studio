from djmidi.midi_api import MidiMessage
from djmidi.midi_clock import MidiClockMirror


def test_clock_mirror_rejects_invalid_destinations():
    for destinations in ([], ["clock-in"], ["out", "out"]):
        try:
            MidiClockMirror("clock-in", destinations)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Clock destinations must be rejected")


def test_clock_mirror_tracks_transport_and_forwards_destinations():
    mirror = MidiClockMirror("clock-in", ["a", "b"])
    sent: list[str] = []
    start = MidiMessage(data=b"\xfa", received_time=1, port_id="clock-in")
    assert mirror.forward(start, lambda destination, _: sent.append(destination)) == 2
    assert mirror.running
    assert sent == ["a", "b"]
    stop = MidiMessage(data=b"\xfc", received_time=2, port_id="clock-in")
    mirror.forward(stop, lambda *_: None)
    assert not mirror.running


def test_clock_mirror_drops_impossible_jitter_and_reports_timing():
    mirror = MidiClockMirror(
        "clock-in",
        ["out"],
        min_clock_interval_ms=2.0,
        expected_interval_ms=10.0,
    )
    sent: list[float] = []
    send = lambda _destination, message: sent.append(message.received_time)
    assert mirror.forward(MidiMessage(b"\xf8", 1.000, "clock-in"), send) == 1
    assert mirror.forward(MidiMessage(b"\xf8", 1.001, "clock-in"), send) == 0
    assert mirror.forward(MidiMessage(b"\xf8", 1.011, "clock-in"), send) == 1
    assert mirror.stats.jitter_dropped == 1
    assert mirror.stats.jitter_samples == 1
    assert mirror.stats.last_interval_ms == 10.0
    assert sent == [1.0, 1.011]


def test_clock_transport_boundaries_reset_jitter_measurement():
    mirror = MidiClockMirror("clock-in", ["out"], expected_interval_ms=10.0)
    sent: list[bytes] = []
    send = lambda _destination, message: sent.append(message.data)
    mirror.forward(MidiMessage(b"\xf8", 1.000, "clock-in"), send)
    mirror.forward(MidiMessage(b"\xf8", 1.010, "clock-in"), send)
    mirror.forward(MidiMessage(b"\xfc", 2.000, "clock-in"), send)
    mirror.forward(MidiMessage(b"\xfa", 3.000, "clock-in"), send)
    mirror.forward(MidiMessage(b"\xf8", 3.001, "clock-in"), send)
    assert mirror.stats.jitter_samples == 1
    assert sent[-1] == b"\xf8"


def test_clock_mirror_reports_recent_source_activity():
    mirror = MidiClockMirror("clock-in", ["out"])
    assert not mirror.clock_active(10.0)
    mirror.forward(MidiMessage(b"\xf8", 10.0, "clock-in"), lambda *_: None)
    assert mirror.clock_active(10.4)
    assert not mirror.clock_active(10.6)


def test_clock_mirror_reports_transport_without_clock_ticks():
    mirror = MidiClockMirror("clock-in", ["out"])
    mirror.forward(MidiMessage(b"\xfa", 10.0, "clock-in"), lambda *_: None)
    assert mirror.message_active(10.4)
    assert not mirror.clock_active(10.4)
