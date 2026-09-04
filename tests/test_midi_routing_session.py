from __future__ import annotations

import mido

from djmidi.midi_api import MidiMessage
from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_router import MidiRoute, MidiRouter
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME, MidiRoutingSession


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


class _CloseFailingPort(_FakePort):
    def close(self):
        self.closed = True
        raise OSError("endpoint already gone")


class _FakeLinkFollower:
    """Minimal double for LinkClockFollower, tracking bridged transport calls."""

    def __init__(self, destination_port_ids=("link-out",)):
        self.source_port_id = "Ableton Link (DJ MIDI Studio)"
        self.destination_port_ids = tuple(destination_port_ids)
        self.published = []
        self.reset_calls = 0

    def poll(self, send):
        return 0

    def publish_transport(self, is_playing):
        self.published.append(is_playing)

    def reset(self):
        self.reset_calls += 1


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


def test_session_forwards_clock_messages_without_a_regular_route():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("clock")])
    output_port = _FakePort()
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror("clock-in", ["clock-out"]),
    )

    session.start()
    assert session.poll() == 1
    assert output_port.sent == [mido.Message("clock")]
    session.stop()


def test_session_forwards_clock_to_multiple_independent_destinations():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("start")])
    outputs = {name: _FakePort() for name in ("clock-a", "clock-b", "clock-c")}
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: input_port,
        output_opener=lambda name: outputs[name],
        clock_mirrors=(
            MidiClockMirror("clock-in", ["clock-a", "clock-b"]),
            MidiClockMirror("clock-in", ["clock-c"]),
        ),
    )

    session.start()
    assert session.poll() == 3
    assert all(port.sent == [mido.Message("start")] for port in outputs.values())
    session.stop()


def test_session_rejects_cycle_that_combines_regular_and_clock_routes():
    router = MidiRouter()
    router.add_route(MidiRoute("controller", "software"))
    session = MidiRoutingSession(
        router,
        clock_mirror=MidiClockMirror("software", ["controller"]),
    )
    try:
        session.start()
    except ValueError as exc:
        assert "feedback loop" in str(exc)
    else:
        raise AssertionError("combined MIDI and Clock cycle must be rejected")


def test_session_opens_configured_clock_source_as_virtual_input():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("start")])
    output_port = _FakePort()
    virtual_names = []
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: (_ for _ in ()).throw(AssertionError("physical opener used")),
        virtual_input_ids=("serato-clock",),
        virtual_input_opener=lambda name: (virtual_names.append(name) or input_port),
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror("serato-clock", ["controller"]),
    )

    session.start()
    assert virtual_names == ["serato-clock"]
    assert session.poll() == 1
    session.stop()


def test_serato_virtual_clock_forwards_transport_and_ticks():
    router = MidiRouter()
    input_port = _FakePort(
        [mido.Message("start"), mido.Message("clock"), mido.Message("stop")]
    )
    output_port = _FakePort()
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: (_ for _ in ()).throw(AssertionError("physical opener used")),
        virtual_input_ids=("DJ MIDI Studio Serato Clock In",),
        virtual_input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror("DJ MIDI Studio Serato Clock In", ["traktor-clock-in"]),
    )
    session.start()
    assert session.poll() == 3
    assert [message.type for message in output_port.sent] == ["start", "clock", "stop"]
    session.stop()


def test_session_stop_closes_all_ports_and_resets_clock_after_close_failure():
    router = MidiRouter()
    router.add_route(MidiRoute("in", "out"))
    input_port = _CloseFailingPort()
    output_port = _FakePort()
    mirror = MidiClockMirror("clock-in", ["out"])
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=mirror,
    )
    session.start()
    # The mirror receives state independently of the physical input lifecycle.
    mirror.forward(MidiMessage(b"\xf8", 1.0, "clock-in"), lambda *_: None)
    session.stop()
    assert input_port.closed and output_port.closed
    assert session.input_port_ids == ()
    assert session.output_port_ids == ()
    assert not mirror.clock_active(1.1)


def test_serato_clock_bridges_start_stop_to_link_followers():
    router = MidiRouter()
    input_port = _FakePort(
        [mido.Message("start"), mido.Message("clock"), mido.Message("stop")]
    )
    output_port = _FakePort()
    follower = _FakeLinkFollower()
    session = MidiRoutingSession(
        router,
        virtual_input_ids=(SERATO_CLOCK_INPUT_NAME,),
        virtual_input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror(SERATO_CLOCK_INPUT_NAME, ["clock-out"]),
        link_followers=(follower,),
    )
    session.start()
    session.poll()
    session.stop()
    assert follower.published == [True, False]
    # start() itself calls stop() first to clear any prior state, then the
    # explicit stop() below runs a second time.
    assert follower.reset_calls == 2


def test_serato_clock_bridge_treats_a_bare_tick_as_playing():
    """Joining an already-running Clock stream (e.g. routing starts after the
    external producer was already playing) never sends a fresh Start byte,
    only ticks -- the bridge must still detect it as playing (regression for
    a real hardware session where Ableton Live was already playing when
    routing started, so no Start edge was ever seen)."""
    router = MidiRouter()
    input_port = _FakePort([mido.Message("clock")])
    output_port = _FakePort()
    follower = _FakeLinkFollower()
    session = MidiRoutingSession(
        router,
        virtual_input_ids=(SERATO_CLOCK_INPUT_NAME,),
        virtual_input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror(SERATO_CLOCK_INPUT_NAME, ["clock-out"]),
        link_followers=(follower,),
    )
    session.start()
    session.poll()
    assert follower.published == [True]


def test_serato_clock_bridge_ignores_repeated_start_messages():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("start"), mido.Message("start")])
    output_port = _FakePort()
    follower = _FakeLinkFollower()
    session = MidiRoutingSession(
        router,
        virtual_input_ids=(SERATO_CLOCK_INPUT_NAME,),
        virtual_input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror(SERATO_CLOCK_INPUT_NAME, ["clock-out"]),
        link_followers=(follower,),
    )
    session.start()
    session.poll()
    assert follower.published == [True]


def test_non_serato_clock_source_does_not_bridge_to_link_followers():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("start")])
    output_port = _FakePort()
    follower = _FakeLinkFollower()
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror("clock-in", ["clock-out"]),
        link_followers=(follower,),
    )
    session.start()
    session.poll()
    assert follower.published == []


def test_serato_clock_does_not_bridge_without_link_followers():
    router = MidiRouter()
    input_port = _FakePort([mido.Message("start")])
    output_port = _FakePort()
    session = MidiRoutingSession(
        router,
        virtual_input_ids=(SERATO_CLOCK_INPUT_NAME,),
        virtual_input_opener=lambda name: input_port,
        output_opener=lambda name: output_port,
        clock_mirror=MidiClockMirror(SERATO_CLOCK_INPUT_NAME, ["clock-out"]),
    )
    session.start()
    # No Link followers configured: forwarding must succeed without error.
    assert session.poll() == 1
