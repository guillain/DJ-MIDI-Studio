import pytest

from djmidi.midi_api import MidiMessage
from djmidi.midi_router import MidiRoute, MidiRouter


def _note(port_id: str = "in") -> MidiMessage:
    return MidiMessage(data=bytes((0x90, 60, 100)), received_time=1.0, port_id=port_id)


def test_router_forwards_matching_message_and_tracks_stats():
    router = MidiRouter()
    router.add_route(MidiRoute("in", "out", channels=frozenset({1})))
    sent: list[tuple[str, MidiMessage]] = []
    assert router.route_message("in", _note(), lambda port, msg: sent.append((port, msg))) == 1
    assert sent[0][0] == "out"
    assert router.stats.forwarded == 1


def test_router_drops_filtered_messages_and_rejects_cycles():
    router = MidiRouter()
    router.add_route(MidiRoute("in", "out", channels=frozenset({2})))
    assert router.route_message("in", _note(), lambda *_: None) == 0
    assert router.stats.dropped == 1
    with pytest.raises(ValueError, match="routing loop"):
        router.add_route(MidiRoute("out", "in"))
