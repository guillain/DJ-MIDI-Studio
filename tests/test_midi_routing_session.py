from __future__ import annotations

import mido

from djmidi.midi_router import MidiRoute, MidiRouter
from djmidi.midi_routing_session import MidiRoutingSession


class _FakePort:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.sent = []
        self.closed = False

    def iter_pending(self):
        messages, self.messages = self.messages, []
        return messages

    def send(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


def test_session_forwards_messages_and_closes_ports():
    router = MidiRouter()
    router.add_route(MidiRoute("controller", "software"))
    input_port = _FakePort([mido.Message("note_on", note=60, velocity=100)])
    output_port = _FakePort()

    session = MidiRoutingSession(
        router,
        input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
    )
    session.start()

    assert session.poll() == 1
    assert output_port.sent == [mido.Message("note_on", note=60, velocity=100)]
    session.stop()
    assert input_port.closed
    assert output_port.closed


def test_session_requires_an_enabled_route():
    session = MidiRoutingSession(MidiRouter())

    try:
        session.start()
    except ValueError as exc:
        assert "enabled MIDI route" in str(exc)
    else:
        raise AssertionError("session should reject an empty route set")
