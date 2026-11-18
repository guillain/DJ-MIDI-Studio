"""Connection test between two DJs (remote mix, phase 0).

One side hosts (binds a UDP port and waits), the other joins (sends to the
host's address). Both then ping each other ten times a second; every pong
carries the answering side's clock readings (NTP style, so round trip and
clock offset come out) and, when Ableton Link runs there, its tempo and beat.
With the offset known, the remote beat is moved onto the local clock and
compared with the local Link beat: that gap, and how it drifts, says whether
the two Link sessions are one timeline (same session through a VPN) or two.

Qt-free; the socket runs on a worker thread so a timestamp is taken the moment
a packet arrives, not when a GUI timer next looks.
"""

from __future__ import annotations

import json
import logging
import queue
import socket
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

_LOGGER = logging.getLogger(__name__)

PROTOCOL = "djmidi-mix/1"
DEFAULT_PORT = 47800
MAX_PACKET = 1024
MAX_DJS = 4  # the host and up to three guests (phase 9)
GUEST_TIMEOUT_S = 10.0
PING_INTERVAL_S = 0.1
QUANTUM = 4.0
MAX_SAMPLES = 36_000  # one hour at ten pings a second

GREEN, ORANGE, RED, UNKNOWN = "green", "orange", "red", "unknown"

# Thresholds (ms). A bar at 128 BPM is 1875 ms: the bar-delay alignment of
# phase 2 hides any steady latency, what hurts is jitter and loss.
RTT_GREEN, RTT_ORANGE = 150.0, 250.0
JITTER_GREEN, JITTER_ORANGE = 20.0, 40.0
LOSS_GREEN, LOSS_ORANGE = 1.0, 5.0
PHASE_GREEN, PHASE_ORANGE = 5.0, 20.0
TEMPO_TOLERANCE = 0.05


@dataclass(frozen=True)
class LinkSnapshot:
    """The local Link session at clock time ``at`` (seconds, the probe clock)."""

    tempo: float
    beat: float
    at: float
    peers: int = 0


LinkReader = Callable[[], LinkSnapshot | None]


@dataclass(frozen=True)
class Sample:
    t: float  # local clock when the pong arrived
    rtt_ms: float
    offset_ms: float  # remote clock minus local clock
    phase_ms: float | None = None
    local_tempo: float | None = None
    remote_tempo: float | None = None
    remote_peers: int | None = None


@dataclass(frozen=True)
class ProbeStats:
    sent: int
    received: int
    loss_pct: float
    rtt_min: float
    rtt_median: float
    rtt_p95: float
    jitter_ms: float
    offset_spread_ms: float
    phase_median_ms: float | None
    phase_drift_ms_per_min: float | None
    local_tempo: float | None
    remote_tempo: float | None
    duration_s: float


def encode(message: dict) -> bytes:
    return json.dumps({"p": PROTOCOL, **message}, separators=(",", ":")).encode()


def decode(data: bytes) -> dict | None:
    """A message from another DJ MIDI Studio, or None for anything else."""
    if len(data) > MAX_PACKET:
        return None
    try:
        message = json.loads(data.decode())
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict) or message.get("p") != PROTOCOL:
        return None
    return message


def _number(message: dict, key: str) -> float | None:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def round_trip(t0: float, t1: float, t2: float, t3: float) -> tuple[float, float]:
    """(round trip, offset) in seconds from NTP's four timestamps: ping sent
    (local), ping received and pong sent (remote), pong received (local)."""
    return (t3 - t0) - (t2 - t1), ((t1 - t0) + (t2 - t3)) / 2


def phase_gap_ms(local_beat: float, remote_beat: float, tempo: float, quantum: float = QUANTUM) -> float:
    """How far the local beat is ahead of the remote one, at the same instant,
    wrapped into half a bar either way, in milliseconds."""
    gap = (local_beat - remote_beat + quantum / 2) % quantum - quantum / 2
    return gap * 60_000.0 / tempo


def local_beat_at(snapshot: LinkSnapshot, t: float) -> float:
    return snapshot.beat + (t - snapshot.at) * snapshot.tempo / 60.0


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _slope_per_min(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 10:
        return None
    xs = [t for t, _ in points]
    span = max(xs) - min(xs)
    if span < 10.0:
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(y for _, y in points)
    num = sum((x - mean_x) * (y - mean_y) for x, y in points)
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den * 60.0 if den else None


def summarise(samples: list[Sample], sent: int) -> ProbeStats | None:
    if not samples:
        return None
    rtts = [s.rtt_ms for s in samples]
    jitter = statistics.fmean(abs(b - a) for a, b in pairwise(rtts)) if len(rtts) > 1 else 0.0
    offsets = [s.offset_ms for s in samples]
    phased = [(s.t, s.phase_ms) for s in samples if s.phase_ms is not None]
    last_local = next((s.local_tempo for s in reversed(samples) if s.local_tempo), None)
    last_remote = next((s.remote_tempo for s in reversed(samples) if s.remote_tempo), None)
    received = len(samples)
    loss = max(0.0, 100.0 * (sent - received) / sent) if sent else 0.0
    return ProbeStats(
        sent=sent,
        received=received,
        loss_pct=loss,
        rtt_min=min(rtts),
        rtt_median=statistics.median(rtts),
        rtt_p95=_percentile(rtts, 0.95),
        jitter_ms=jitter,
        offset_spread_ms=_percentile(offsets, 0.95) - _percentile(offsets, 0.05),
        phase_median_ms=statistics.median(p for _, p in phased) if phased else None,
        phase_drift_ms_per_min=_slope_per_min(phased),
        local_tempo=last_local,
        remote_tempo=last_remote,
        duration_s=samples[-1].t - samples[0].t,
    )


def _grade(value: float, green: float, orange: float) -> str:
    return GREEN if value < green else ORANGE if value < orange else RED


def verdicts(stats: ProbeStats | None) -> dict[str, str]:
    """A light per check: ``network`` (round trip and loss), ``stability``
    (jitter) and ``link`` (same tempo, same phase)."""
    if stats is None:
        return {"network": UNKNOWN, "stability": UNKNOWN, "link": UNKNOWN}
    order = [GREEN, ORANGE, RED]
    network = max(
        _grade(stats.rtt_median, RTT_GREEN, RTT_ORANGE),
        _grade(stats.loss_pct, LOSS_GREEN, LOSS_ORANGE),
        key=order.index,
    )
    link = UNKNOWN
    if stats.local_tempo and stats.remote_tempo:
        if abs(stats.local_tempo - stats.remote_tempo) > TEMPO_TOLERANCE:
            link = RED
        elif stats.phase_median_ms is not None:
            link = _grade(abs(stats.phase_median_ms), PHASE_GREEN, PHASE_ORANGE)
    return {
        "network": network,
        "stability": _grade(stats.jitter_ms, JITTER_GREEN, JITTER_ORANGE),
        "link": link,
    }


_STARTED = QT_TRANSLATE_NOOP("RemoteMixReport", "Started")
_THIS_SIDE = QT_TRANSLATE_NOOP("RemoteMixReport", "This side")
_OTHER_DJ = QT_TRANSLATE_NOOP("RemoteMixReport", "Other DJ")
_PROTOCOL_WORD = QT_TRANSLATE_NOOP("RemoteMixReport", "Protocol")
_MEASURE = QT_TRANSLATE_NOOP("RemoteMixReport", "Measure")
_NETWORK = QT_TRANSLATE_NOOP("RemoteMixReport", "Network")
_STABILITY = QT_TRANSLATE_NOOP("RemoteMixReport", "Stability")
_TEMPO_PHASE = QT_TRANSLATE_NOOP("RemoteMixReport", "Tempo and phase")
_LIGHT_WORDS = {
    GREEN: QT_TRANSLATE_NOOP("RemoteMixReport", "green"),
    ORANGE: QT_TRANSLATE_NOOP("RemoteMixReport", "orange"),
    RED: QT_TRANSLATE_NOOP("RemoteMixReport", "red"),
    UNKNOWN: QT_TRANSLATE_NOOP("RemoteMixReport", "not measured"),
}


def _ms(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ms"


def report_markdown(
    stats: ProbeStats | None,
    *,
    role: str,
    peer: str,
    started: datetime,
    translate: Translate = untranslated,
) -> str:
    """The test as a small Markdown report the DJs can send to each other."""
    t = translate
    lights = verdicts(stats)
    lines = [
        "# " + t(QT_TRANSLATE_NOOP("RemoteMixReport", "Mix together: connection test")),
        "",
        f"- {t(_STARTED)}: {started:%Y-%m-%d %H:%M:%S}",
        f"- {t(_THIS_SIDE)}: {role}",
        f"- {t(_OTHER_DJ)}: {peer}",
        f"- {t(_PROTOCOL_WORD)}: {PROTOCOL}",
        "",
    ]
    if stats is None:
        lines.append(t(QT_TRANSLATE_NOOP("RemoteMixReport", "No answer from the other DJ.")))
        return "\n".join(lines) + "\n"
    tempo = lambda v: "—" if v is None else f"{v:.2f} BPM"
    drift = "—" if stats.phase_drift_ms_per_min is None else f"{stats.phase_drift_ms_per_min:+.2f} ms/min"
    rows = [
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Duration"), f"{stats.duration_s:.0f} s"),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Pings sent / answered"), f"{stats.sent} / {stats.received}"),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Lost"), f"{stats.loss_pct:.1f} %"),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Round trip min / median / 95 %"),
         f"{_ms(stats.rtt_min)} / {_ms(stats.rtt_median)} / {_ms(stats.rtt_p95)}"),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Jitter"), _ms(stats.jitter_ms)),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Clock offset spread"), _ms(stats.offset_spread_ms)),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Link tempo here / there"),
         f"{tempo(stats.local_tempo)} / {tempo(stats.remote_tempo)}"),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Link phase gap"), _ms(stats.phase_median_ms)),
        (QT_TRANSLATE_NOOP("RemoteMixReport", "Link phase drift"), drift),
    ]
    lines += [f"| {t(_MEASURE)} | |", "|---|---|"]
    lines += [f"| {t(label)} | {value} |" for label, value in rows]
    lines += [
        "",
        f"- {t(_NETWORK)}: {t(_LIGHT_WORDS[lights['network']])}",
        f"- {t(_STABILITY)}: {t(_LIGHT_WORDS[lights['stability']])}",
        f"- {t(_TEMPO_PHASE)}: {t(_LIGHT_WORDS[lights['link']])}",
    ]
    return "\n".join(lines) + "\n"


class ProbeSession:
    """One side of the connection test.

    ``peer=None`` hosts: the first DJ MIDI Studio that pings becomes the peer
    (the only one answered from then on). ``peer=(host, port)`` joins.
    """

    def __init__(
        self,
        *,
        port: int = DEFAULT_PORT,
        peer: tuple[str, int] | None = None,
        link_reader: LinkReader | None = None,
        clock: Callable[[], float] = time.monotonic,
        interval: float = PING_INTERVAL_S,
        bind_host: str = "0.0.0.0",
        link_control=None,
        follow: bool = False,
        max_peers: int = 1,
        name: str = "",
    ) -> None:
        from djmidi.remote_mix.bridge import LinkFollower  # bridge imports this module

        self._link_control = link_control
        self.follow = follow
        self.follower = LinkFollower()
        self.leading = peer is None  # the host leads first
        self.remote_leading: bool | None = None
        self.follow_error: str | None = None
        self._port = port
        self._peer = peer
        self._link_reader = link_reader
        self._clock = clock
        self._interval = interval
        self._bind_host = bind_host
        self._lock = threading.Lock()
        self._samples: list[Sample] = []
        self._sent = 0
        self._pending: dict[int, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._join_target = peer
        self.error: str | None = None
        # Several DJs (phase 9): the host is the hub of a star of up to `max_peers` guests.
        self.max_peers = max(1, max_peers)
        self.name = name
        self._guests: dict[tuple[str, int], int] = {}  # guest address → DJ id (host side)
        self._seen: dict[tuple[str, int], float] = {}
        self.my_id: int | None = 0 if peer is None else None  # the host is DJ 0; a guest learns its id
        self.roster: dict[int, str] = {0: name} if peer is None else {}
        # Shared-mixer messages from the other DJ (phase 6), drained by the GUI.
        self.inbox: queue.SimpleQueue[dict] = queue.SimpleQueue()

    @property
    def hosting(self) -> bool:
        return self._thread is not None and self._join_target is None

    @property
    def port(self) -> int:
        return self._socket.getsockname()[1] if self._socket else self._port

    @property
    def peer(self) -> tuple[str, int] | None:
        return self._peer

    def peer_ids(self) -> dict[str, int]:
        """Each other DJ's IP → DJ id (the host knows every guest; a guest only the host)."""
        if self._join_target is not None:
            return {self._join_target[0]: 0}
        with self._lock:
            return {address[0]: dj for address, dj in self._guests.items()}

    def _targets(self) -> list[tuple[str, int]]:
        if self._join_target is not None:
            return [self._join_target]
        with self._lock:
            return list(self._guests)

    def _forget_silent_guests(self, now: float) -> None:
        with self._lock:
            for address in [a for a, seen in self._seen.items() if now - seen > GUEST_TIMEOUT_S]:
                dj = self._guests.pop(address, None)
                self._seen.pop(address, None)
                self.roster.pop(dj, None)
                if self._peer == address:
                    self._peer = min(self._guests, key=self._guests.get) if self._guests else None

    def _roster_message(self, address: tuple[str, int]) -> dict:
        with self._lock:
            return {"you": self._guests.get(address), "roster": [[dj, name] for dj, name in sorted(self.roster.items())]}

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._bind_host, self._port if self._peer is None else 0))
        sock.settimeout(0.01)
        self._socket = sock
        self._thread = threading.Thread(target=self._run, name="djmidi-remote-probe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._socket is not None:
            self._socket.close()

    def snapshot(self) -> tuple[list[Sample], int]:
        with self._lock:
            return list(self._samples), self._sent

    def stats(self) -> ProbeStats | None:
        samples, sent = self.snapshot()
        return summarise(samples, sent)

    def _link(self) -> LinkSnapshot | None:
        if self._link_reader is None:
            return None
        try:
            return self._link_reader()
        except Exception:
            _LOGGER.debug("Link snapshot failed", exc_info=True)
            return None

    def _run(self) -> None:
        sock = self._socket
        assert sock is not None
        next_ping = self._clock()
        seq = 0
        while not self._stop.is_set():
            now = self._clock()
            if self._peer is not None and now >= next_ping:
                if self._join_target is None:
                    self._forget_silent_guests(now)
                for address in self._targets():
                    seq += 1
                    ping = {"k": "ping", "s": seq, "t0": now, "lead": self.leading, "name": self.name}
                    if self._join_target is None:
                        ping.update(self._roster_message(address))
                    self._send_to(sock, ping, address)
                    with self._lock:
                        self._sent += 1
                        self._pending[seq] = now
                        if len(self._pending) > 100 * self.max_peers:
                            self._pending.pop(min(self._pending))
                next_ping = now + self._interval
            try:
                data, address = sock.recvfrom(MAX_PACKET + 1)
            except TimeoutError:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.error = str(exc)
                    _LOGGER.warning("Remote mix probe socket error: %s", exc)
                continue
            self._handle(sock, data, address, self._clock())

    def send(self, message: dict) -> None:
        """Send one message to the other DJs (the shared mixer's moves); nothing before a peer."""
        if self._socket is not None:
            self._send(self._socket, message)

    def take_lead(self) -> None:
        """This side leads from now on; the other side follows (sent three
        times: a lost packet must not leave two leaders)."""
        self.leading = True
        self.remote_leading = False
        sock = self._socket
        if sock is not None:
            for _ in range(3):
                self._send(sock, {"k": "take"})

    def _follow(self, tempo: float, beat: float, sent: float, rtt: float, offset: float, link: LinkSnapshot) -> None:
        from djmidi.remote_mix import bridge

        correction = self.follower.update(bridge.RemoteBeat(tempo, beat, sent, rtt, offset), link, self._clock())
        if correction is None:
            return
        try:
            bridge.apply(correction, self._link_control)
            self.follow_error = None
        except Exception as exc:  # noqa: BLE001 - keep measuring when Link refuses
            self.follow_error = str(exc)
            _LOGGER.warning("Remote mix: Link correction failed: %s", exc)

    def _send(self, sock: socket.socket, message: dict, *, skip: tuple[str, int] | None = None) -> None:
        """To the host (guest), or to every guest (host) but ``skip``."""
        for address in self._targets():
            if address != skip:
                self._send_to(sock, message, address)

    def _send_to(self, sock: socket.socket, message: dict, address: tuple[str, int]) -> None:
        try:
            sock.sendto(encode(message), address)
        except OSError as exc:
            self.error = str(exc)

    def _handle(self, sock: socket.socket, data: bytes, address: tuple[str, int], received: float) -> None:
        message = decode(data)
        if message is None:
            return
        address = (address[0], address[1])
        if self._join_target is None:
            if not self._admit(address, message):
                return  # hosting: the room is full
        elif address != self._peer:
            return
        else:
            self._learn_roster(message)
        kind = message.get("k")
        if isinstance(message.get("lead"), bool):
            self.remote_leading = message["lead"]
        if kind in ("mix", "sig", "trk"):  # the shared mixer's moves, signals, the tracklist
            self.inbox.put(message)
            if self._join_target is None:
                self._send(sock, message, skip=address)  # the hub passes it on to the other guests
            return
        if kind == "take":
            if self._join_target is None and len(self._guests) > 1:
                return  # with several DJs the host keeps the lead
            self.leading = False
            self.remote_leading = True
            self.follower.reset()
            return
        if kind == "ping":
            t0, seq = _number(message, "t0"), message.get("s")
            if t0 is None or not isinstance(seq, int):
                return
            link = self._link()
            sent = self._clock()
            reply = {"k": "pong", "s": seq, "t0": t0, "t1": received, "t2": sent, "lead": self.leading, "name": self.name}
            if self._join_target is None:
                reply.update(self._roster_message(address))
            if link is not None:
                reply.update(tempo=link.tempo, beat=local_beat_at(link, sent), peers=link.peers)
            self._send_to(sock, reply, address)
        elif kind == "pong":
            self._on_pong(message, received)

    def _admit(self, address: tuple[str, int], message: dict) -> bool:
        """Host: a known guest, or a new one while there is room (ids 1, 2, 3 …)."""
        name = message.get("name")
        with self._lock:
            if address not in self._guests:
                if len(self._guests) >= self.max_peers:
                    return False
                taken = set(self._guests.values())
                self._guests[address] = next(dj for dj in range(1, self.max_peers + 1) if dj not in taken)
                if self._peer is None:
                    self._peer = address
            self._seen[address] = self._clock()
            dj = self._guests[address]
            if isinstance(name, str):
                self.roster[dj] = name[:40]
            else:
                self.roster.setdefault(dj, "")
        return True

    def _learn_roster(self, message: dict) -> None:
        """Guest: its own id and who is in the room, from the host's messages."""
        you, roster = message.get("you"), message.get("roster")
        if isinstance(you, int) and not isinstance(you, bool):
            self.my_id = you
        if isinstance(roster, list):
            known = {}
            for entry in roster:
                if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], int) and isinstance(entry[1], str):
                    known[entry[0]] = entry[1][:40]
            if known:
                self.roster = known

    def _on_pong(self, message: dict, t3: float) -> None:
        t0, t1, t2 = (_number(message, key) for key in ("t0", "t1", "t2"))
        seq = message.get("s")
        if t0 is None or t1 is None or t2 is None or not isinstance(seq, int):
            return
        with self._lock:
            if self._pending.pop(seq, None) != t0:
                return  # duplicate, stale or forged
        rtt, offset = round_trip(t0, t1, t2, t3)
        remote_tempo, remote_beat = _number(message, "tempo"), _number(message, "beat")
        peers = message.get("peers")
        link = self._link()
        phase = None
        if link is not None and remote_tempo and remote_beat is not None and link.tempo > 0:
            phase = phase_gap_ms(local_beat_at(link, t2 - offset), remote_beat, link.tempo)
        if (
            self.follow
            and not self.leading
            and self.remote_leading
            and link is not None
            and self._link_control is not None
            and remote_tempo
            and remote_beat is not None
        ):
            self._follow(remote_tempo, remote_beat, t2, rtt, offset, link)
        sample = Sample(
            t=t3,
            rtt_ms=rtt * 1000.0,
            offset_ms=offset * 1000.0,
            phase_ms=phase,
            local_tempo=link.tempo if link else None,
            remote_tempo=remote_tempo,
            remote_peers=peers if isinstance(peers, int) else None,
        )
        with self._lock:
            self._samples.append(sample)
            if len(self._samples) > MAX_SAMPLES:
                del self._samples[: len(self._samples) - MAX_SAMPLES]


def link_reader_from(provider, clock: Callable[[], float] = time.monotonic) -> LinkReader:
    """A `LinkReader` over an `ableton_link.LinkStateProvider` (the probe and
    the provider must share ``clock``)."""

    def read() -> LinkSnapshot:
        now = clock()
        state = provider.state_at(now)
        peers = getattr(provider, "num_peers", None)
        return LinkSnapshot(state.tempo, state.beat, now, int(peers()) if callable(peers) else 0)

    return read


def report_file_name(started: datetime) -> str:
    return f"remote-mix-test-{started:%Y%m%d-%H%M%S}.md"
