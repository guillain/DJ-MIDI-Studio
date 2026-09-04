from dataclasses import dataclass, field
from unittest.mock import patch

from djmidi.ableton_link import AalinkStateProvider, LinkClockFollower, LinkState


@dataclass
class _FakeLink:
    state: LinkState
    published: list = field(default_factory=list)

    def state_at(self, _now):
        return self.state

    def close(self):
        pass

    def publish_transport(self, is_playing):
        self.published.append(is_playing)


def test_link_follower_emits_start_and_24_ppqn_ticks_from_tempo():
    provider = _FakeLink(LinkState(tempo=120, beat=0, playing=True))
    follower = LinkClockFollower(["out"], provider, clock_fn=lambda: 0)
    sent = []
    assert follower.poll(lambda destination, message: sent.append((destination, message.data)), now=0) == 2
    assert sent == [("out", b"\xfa"), ("out", b"\xf8")]
    assert follower.poll(lambda destination, message: sent.append((destination, message.data)), now=0.020) == 0
    assert follower.poll(lambda destination, message: sent.append((destination, message.data)), now=0.021) == 1
    assert sent[-1] == ("out", b"\xf8")


def test_link_follower_emits_stop_without_changing_link_tempo():
    provider = _FakeLink(LinkState(tempo=100, beat=0, playing=True))
    follower = LinkClockFollower(["out"], provider)
    sent = []
    follower.poll(lambda _destination, message: sent.append(message.data), now=1)
    provider.state = LinkState(tempo=100, beat=1, playing=False)
    assert follower.poll(lambda _destination, message: sent.append(message.data), now=1.1) == 1
    assert sent[-1] == b"\xfc"
    assert not follower.running


def test_link_follower_rejects_invalid_tempo():
    provider = _FakeLink(LinkState(tempo=0, beat=0, playing=True))
    follower = LinkClockFollower(["out"], provider)
    try:
        follower.poll(lambda *_: None, now=0)
    except ValueError as exc:
        assert "tempo" in str(exc)
    else:
        raise AssertionError("invalid Link tempo must be rejected")


def test_aalink_provider_uses_modern_async_backend_api():
    class FakeLink:
        enabled = False

        def __init__(self, tempo):
            self.tempo = tempo
            self.beat = 3.5
            self.playing = True

    with patch.dict("sys.modules", {"aalink": type("Module", (), {"Link": FakeLink})}):
        provider = AalinkStateProvider(128.0)
        try:
            assert provider.state_at(0) == LinkState(tempo=128.0, beat=3.5, playing=True)
        finally:
            provider.close()


def test_aalink_provider_enables_start_stop_sync():
    """A peer that hasn't opted into Start Stop Sync neither sends nor
    receives Start/Stop over Link, even if every other peer has it on --
    confirmed on real hardware (Serato, DDJ-XP2, XDJ-XZ, Ableton Live 12).
    Without this, `state_at().playing` could never become True from a real
    remote peer no matter what that peer did."""

    class FakeLink:
        enabled = False
        start_stop_sync_enabled = False

        def __init__(self, tempo):
            self.tempo = tempo
            self.beat = 0.0
            self.playing = False

    with patch.dict("sys.modules", {"aalink": type("Module", (), {"Link": FakeLink})}):
        provider = AalinkStateProvider(120.0)
        try:
            assert provider._link.start_stop_sync_enabled is True
        finally:
            provider.close()


def test_link_follower_publish_transport_forwards_to_provider():
    provider = _FakeLink(LinkState(tempo=120, beat=0, playing=False))
    follower = LinkClockFollower(["out"], provider)
    follower.publish_transport(True)
    follower.publish_transport(False)
    assert provider.published == [True, False]


def test_aalink_provider_publish_transport_calls_the_backend_setter():
    class FakeLink:
        enabled = False

        def __init__(self, tempo):
            self.tempo = tempo
            self.beat = 2.5
            self.playing = False
            self.time = "link-time-sentinel"
            self.calls = []

        def set_is_playing_and_request_beat_at_time(self, is_playing, time, beat):
            self.calls.append((is_playing, time, beat))

    with patch.dict("sys.modules", {"aalink": type("Module", (), {"Link": FakeLink})}):
        provider = AalinkStateProvider(128.0)
        try:
            provider.publish_transport(True)
            assert provider._link.calls == [(True, "link-time-sentinel", 2.5)]
        finally:
            provider.close()
