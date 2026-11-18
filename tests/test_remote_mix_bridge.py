"""Remote mix phase 1: one leader's Link tempo and beat followed in another home."""

import time

import pytest

from djmidi.remote_mix import bridge as b
from djmidi.remote_mix import probe as p


def _local(tempo=124.0, beat=0.0, at=100.0):
    return p.LinkSnapshot(tempo=tempo, beat=beat, at=at)


def test_follower_copies_the_tempo_and_jumps_onto_the_leaders_beat():
    follower = b.LinkFollower()
    # Leader's clock is 50 s ahead; it read beat 10.0 at its 150.0 = our 100.0.
    remote = b.RemoteBeat(tempo=124.0, beat=10.0, sent=150.0, rtt=0.04, offset=50.0)
    correction = follower.update(remote, _local(tempo=120.0, beat=10.25, at=100.0), now=100.0)
    assert correction.tempo == 124.0
    assert correction.gap_ms == pytest.approx(0.25 * 60_000 / 124)
    assert correction.beat == pytest.approx(10.0)
    # A second gap right after is left alone (one jump every two seconds).
    again = follower.update(remote, _local(beat=10.25, at=100.0), now=100.5)
    assert again is None


def test_small_gaps_are_noise_and_the_fastest_round_trip_sets_the_offset():
    follower = b.LinkFollower()
    follower.update(b.RemoteBeat(124.0, 0.0, 0.0, rtt=0.200, offset=0.030), _local(beat=0.0, at=0.0), now=0.0)
    follower.update(b.RemoteBeat(124.0, 0.0, 0.0, rtt=0.040, offset=0.0), _local(beat=0.0, at=0.0), now=0.0)
    assert follower.offset() == 0.0
    assert follower.update(b.RemoteBeat(124.0, 0.0, 0.0, 0.04, 0.0), _local(beat=0.004, at=0.0), now=0.0) is None


def test_apply_and_phrase_position():
    calls = []

    class Control:
        def set_tempo(self, tempo):
            calls.append(("tempo", tempo))

        def force_beat(self, beat):
            calls.append(("beat", beat))

    b.apply(b.Correction(tempo=126.0, beat=3.0), Control())
    assert calls == [("tempo", 126.0), ("beat", 3.0)]
    assert b.phrase_position(0.2) == b.PhrasePosition(bar=1, beat=1, beats_to_phrase=0)
    assert b.phrase_position(13.5) == b.PhrasePosition(bar=4, beat=2, beats_to_phrase=3)
    assert b.phrase_position(16.0).bar == 1


class FakeLink:
    """A Link session on the shared monotonic clock."""

    def __init__(self, tempo, beat_offset):
        self.tempo, self.origin, self.base = tempo, time.monotonic(), beat_offset

    def beat(self, now):
        return self.base + (now - self.origin) * self.tempo / 60.0

    def read(self):
        now = time.monotonic()
        return p.LinkSnapshot(self.tempo, self.beat(now), now)

    def set_tempo(self, tempo):
        now = time.monotonic()
        self.base, self.origin, self.tempo = self.beat(now), now, tempo

    def force_beat(self, beat):
        self.base, self.origin = beat, time.monotonic()


def _run(host, guest, until, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)


def test_the_joining_dj_follows_the_host_then_takes_the_lead():
    host_link, guest_link = FakeLink(124.0, 0.0), FakeLink(120.0, 1.3)
    host = p.ProbeSession(port=0, bind_host="127.0.0.1", interval=0.02, link_reader=host_link.read,
                          link_control=host_link, follow=True)
    host.start()
    guest = p.ProbeSession(peer=("127.0.0.1", host.port), interval=0.02, link_reader=guest_link.read,
                           link_control=guest_link, follow=True)
    # Threads sharing one GIL bend single round trips: let the follower settle.
    guest.follower = b.LinkFollower(min_interval_s=0.1)
    guest.start()
    try:
        assert host.leading and not guest.leading
        _run(host, guest, lambda: guest.follower.corrections > 0 and guest_link.tempo == 124.0)
        time.sleep(0.6)
        now = time.monotonic()
        assert guest_link.tempo == 124.0
        assert abs(p.phase_gap_ms(guest_link.beat(now), host_link.beat(now), 124.0)) < 5.0
        assert host_link.tempo == 124.0  # the leader is never moved

        guest.take_lead()
        _run(host, guest, lambda: not host.leading)
        assert guest.leading and not host.leading
        guest_link.set_tempo(128.0)
        _run(host, guest, lambda: host_link.tempo == 128.0)
        assert host_link.tempo == 128.0
    finally:
        guest.stop()
        host.stop()


def test_without_follow_nothing_moves():
    host_link, guest_link = FakeLink(124.0, 0.0), FakeLink(120.0, 0.0)
    host = p.ProbeSession(port=0, bind_host="127.0.0.1", interval=0.02, link_reader=host_link.read)
    host.start()
    guest = p.ProbeSession(peer=("127.0.0.1", host.port), interval=0.02, link_reader=guest_link.read,
                           link_control=guest_link, follow=False)
    guest.start()
    try:
        _run(host, guest, lambda: len(guest.snapshot()[0]) >= 5)
    finally:
        guest.stop()
        host.stop()
    assert guest_link.tempo == 120.0
