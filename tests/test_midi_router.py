import pytest

from djmidi.midi_api import MidiMessage
from djmidi.midi_router import MidiRoute, MidiRouter, MidiValueTransform
from djmidi.midi_virtual import VirtualMidiBus


def _note(port_id: str = "in", channel: int = 1, note: int = 60, velocity: int = 100) -> MidiMessage:
    return MidiMessage(data=bytes((0x90 | (channel - 1), note, velocity)), received_time=1.0, port_id=port_id)


def _sysex() -> MidiMessage:
    return MidiMessage(data=bytes((0xF0, 0x7E, 0xF7)), received_time=1.0, port_id="in")


def test_transform_overrides_channel():
    transform = MidiValueTransform(channel_override=3)
    result = transform.apply(_note(channel=1))
    assert result.status == 0x92
    assert result.data[1:] == bytes((60, 100))


def test_transform_offsets_data1_and_clamps():
    assert MidiValueTransform(data1_offset=12).apply(_note(note=100)).data[1] == 112
    assert MidiValueTransform(data1_offset=50).apply(_note(note=100)).data[1] == 127
    assert MidiValueTransform(data1_offset=-200).apply(_note(note=10)).data[1] == 0


def test_transform_inverts_data2():
    assert MidiValueTransform(invert_data2=True).apply(_note(velocity=100)).data[2] == 27
    assert MidiValueTransform(invert_data2=True).apply(_note(velocity=0)).data[2] == 127


def test_transform_ignores_sysex_and_non_channel_voice():
    transform = MidiValueTransform(channel_override=3, data1_offset=12, invert_data2=True)
    sysex = _sysex()
    assert transform.apply(sysex) == sysex
    clock = MidiMessage(data=bytes((0xF8,)), received_time=1.0, port_id="in")
    assert transform.apply(clock) == clock


def test_router_applies_transform_before_forwarding():
    router = MidiRouter()
    router.add_route(MidiRoute("in", "out", transform=MidiValueTransform(channel_override=3, invert_data2=True)))
    sent: list[tuple[str, MidiMessage]] = []
    router.route_message("in", _note(channel=1, velocity=100), lambda port, msg: sent.append((port, msg)))
    assert len(sent) == 1
    forwarded = sent[0][1]
    assert forwarded.status == 0x92
    assert forwarded.data[2] == 27


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


def test_router_integrates_with_virtual_midi_bus():
    bus = VirtualMidiBus(["in", "out"])
    router = MidiRouter()
    router.add_route(MidiRoute("in", "out"))
    message = _note()
    bus.send("in", message)
    for received in bus.receive("in"):
        router.route_message("in", received, bus.send)
    assert bus.receive("out") == [message]
