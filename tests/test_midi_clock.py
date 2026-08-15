from djmidi.midi_api import MidiMessage
from djmidi.midi_clock import MidiClockMirror


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
