"""Try Mix Together alone (demo mode), Qt-free.

Nobody to mix with yet? The demo plays a pretend second DJ on this very
computer, so a DJ can find every part of the tab before the real session:

- the "Demo DJ" is connected at once (a steady, made-up line, shown as such);
- it plays **your own sound back**, a bar late on your grid, as a real
  partner's would land, and **repeats your talkback**, so you hear your mic;
- it answers your signals, and has a strip on the shared mixer.

Nothing leaves the computer: no port is opened.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

from djmidi.remote_mix import audio, probe, signals

DEMO_DJ = 1
DEMO_NAME = "Demo DJ"
DEMO_TEMPO = 120.0
REPLY_AFTER_S = 1.5
_REPLIES = {"next": "love", "drop": "love", "your_turn": "next", "hold": "love", "love": "love"}


class DemoClock:
    """A Link stand-in when Link isn't available: a steady 120 BPM."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._t0 = clock()
        self.control = None

    def __call__(self) -> probe.LinkSnapshot:
        now = self._clock()
        return probe.LinkSnapshot(tempo=DEMO_TEMPO, beat=(now - self._t0) * DEMO_TEMPO / 60.0, at=now, peers=1)


class DemoSession:
    """Stands where a `probe.ProbeSession` would: the host, with the Demo DJ as its guest."""

    def __init__(
        self,
        *,
        port: int,
        name: str = "",
        link_reader: Callable[[], probe.LinkSnapshot | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        **_ignored,
    ) -> None:
        self._clock = clock
        self._link_reader = link_reader
        self.port = port
        self.peer = (DEMO_NAME, port)  # shown where the other DJ's address would be
        self.leading, self.remote_leading = True, False
        self.follow_error = self.error = None
        self.my_id = 0  # the host
        self.roster = {0: name, DEMO_DJ: DEMO_NAME}
        self.inbox: queue.Queue[dict] = queue.Queue()
        self.peer_ids = None  # no star: the Demo DJ lives in this computer
        self._started = clock()
        self._board = signals.SignalBoard(DEMO_DJ)
        self._replies: list[tuple[float, str]] = []

    def start(self) -> None:
        self._started = self._clock()

    def stop(self) -> None:
        self._replies.clear()

    def take_lead(self) -> None:
        self.leading = True

    def send(self, message: dict) -> None:
        answer = message.get("k") == signals.MESSAGE_KIND and message.get("s") in _REPLIES
        if answer and not self._replies:  # one answer at a time
            self._replies.append((self._clock() + REPLY_AFTER_S, _REPLIES[message["s"]]))

    def stats(self) -> probe.ProbeStats | None:
        now = self._clock()
        for at, key in [reply for reply in self._replies if reply[0] <= now]:
            self._replies.remove((at, key))
            self.inbox.put(self._board.send(key))
        count = max(3, int(now - self._started) + 3)
        snapshot = self._link_reader() if self._link_reader is not None else None
        tempo = snapshot.tempo if snapshot is not None else None  # the Demo DJ follows you exactly
        samples = [
            probe.Sample(t=float(i), rtt_ms=20.0, offset_ms=0.0, phase_ms=0.0, local_tempo=tempo, remote_tempo=tempo)
            for i in range(count)
        ]
        return probe.summarise(samples, count)

    def audio_link(self, *, players: audio.PlayerBank | None = None, **_ignored) -> DemoAudioLink:
        return DemoAudioLink(players)


class DemoAudioLink:
    """The Demo DJ's sound: yours, played back as theirs; your voice, repeated."""

    def __init__(self, players: audio.PlayerBank | None) -> None:
        self._players = players
        self.talk_sink: Callable[[int, audio.AudioPacket], None] | None = None
        self.error: str | None = None
        self.sent = self.relayed = self.rejected = 0

    def send(self, packets: list[audio.AudioPacket]) -> None:
        if self._players is None:
            return
        player = self._players.get(DEMO_DJ)
        for packet in packets:
            player.push(packet)
            self.sent += 1

    def send_talk(self, packets: list[audio.AudioPacket]) -> None:
        sink = self.talk_sink
        if sink is not None:
            for packet in packets:
                sink(DEMO_DJ, packet)

    def close(self) -> None:
        self._players = None
