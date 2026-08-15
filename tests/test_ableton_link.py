from dataclasses import dataclass

from djmidi.ableton_link import LinkClockFollower, LinkState


@dataclass
class _FakeLink:
    state: LinkState

    def state_at(self, _now):
        return self.state

    def close(self):
        pass


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
