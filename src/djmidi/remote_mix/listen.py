"""Listening to the official mix (remote mix, phase 8), Qt-free.

A listener is a computer without decks (a friend, a third DJ waiting for
their turn, a laptop feeding a stream) that hears the official mix. The
control room sends it its program mix, Opus-compressed (about 0.25 Mb/s per
listener), on the test port + 2:

- the listener sends a small ``listen`` hello every second; the control room
  keeps everyone heard from in the last few seconds and sends them the mix;
- the listener plays the packets after a short buffer (300 ms by default):
  it has no grid of its own, so it only needs the sound to flow evenly.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable

import numpy as np

from djmidi.remote_mix import audio, opus, probe

_LOGGER = logging.getLogger(__name__)

LISTEN_PORT_OFFSET = 2  # the test port + 2
HELLO_INTERVAL_S = 1.0
LISTENER_TIMEOUT_S = 5.0
MAX_LISTENERS = 16
BUFFER_MS = 300
_STREAM_TEMPO = 120.0  # packets need a tempo; a listener ignores the beat


class ListenerServer:
    """At the control room: who listens, and sending them the mix."""

    def __init__(
        self, *, port: int, bind_host: str = "0.0.0.0", clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._clock = clock
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((bind_host, port))
        self._socket.settimeout(0.05)
        self._listeners: dict[tuple[str, int], float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._buffer = audio.SendBuffer()
        self._encoder: opus.OpusEncoder | None = None
        self._position = 0
        self.sent = 0
        self.error: str | None = None
        self._thread = threading.Thread(target=self._run, name="djmidi-remote-listen", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self._socket.getsockname()[1]

    def listeners(self) -> list[tuple[str, int]]:
        now = self._clock()
        with self._lock:
            for address in [a for a, seen in self._listeners.items() if now - seen > LISTENER_TIMEOUT_S]:
                del self._listeners[address]
            return list(self._listeners)

    def send_mix(self, samples: np.ndarray) -> None:
        """The program mix just played at the control room, to every listener."""
        listeners = self.listeners()
        packets = self._buffer.add(samples, self._position, 0.0, _STREAM_TEMPO, audio.CODEC_OPUS)
        self._position += len(samples)
        if not listeners or not packets:
            return
        if self._encoder is None:
            self._encoder = opus.OpusEncoder()
        for packet in packets:
            for datagram in audio.encode_opus(packet, self._encoder):
                for address in listeners:
                    try:
                        self._socket.sendto(datagram, address)
                        self.sent += 1
                    except OSError as exc:
                        self.error = str(exc)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._socket.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data, address = self._socket.recvfrom(2048)
            except TimeoutError:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.error = str(exc)
                continue
            message = probe.decode(data)
            if message is None or message.get("k") != "listen":
                continue
            with self._lock:
                if address in self._listeners or len(self._listeners) < MAX_LISTENERS:
                    self._listeners[address] = self._clock()


class StreamPlayer:
    """Plays a packet stream evenly after a short buffer; gaps play as silence."""

    def __init__(self, *, buffer_ms: int = BUFFER_MS, capacity_s: float = 8.0) -> None:
        self._target = buffer_ms * audio.RATE // 1000
        self._capacity = int(capacity_s * audio.RATE)
        self._ring = np.zeros((self._capacity, audio.CHANNELS), dtype=np.float32)
        self._stamp = np.full(self._capacity, -1, dtype=np.int64)
        self._lock = threading.Lock()
        self._newest: int | None = None
        self._cursor: int | None = None
        self.received = 0
        self.played = 0
        self.missing = 0
        self.last_peak = 0.0

    def push(self, packet: audio.AudioPacket) -> None:
        n = len(packet.samples)
        positions = np.arange(packet.position, packet.position + n, dtype=np.int64)
        slots = positions % self._capacity
        with self._lock:
            self._ring[slots] = packet.samples
            self._stamp[slots] = positions
            end = packet.position + n
            self._newest = end if self._newest is None else max(self._newest, end)
            self.received += 1

    def buffered_ms(self) -> int:
        with self._lock:
            if self._newest is None or self._cursor is None:
                return 0
            return max(0, (self._newest - self._cursor) * 1000 // audio.RATE)

    def read(self, n: int) -> np.ndarray:
        out = np.zeros((n, audio.CHANNELS), dtype=np.float32)
        with self._lock:
            newest = self._newest
            if newest is None:
                return out
            ahead = None if self._cursor is None else newest - self._cursor
            if ahead is None or ahead < -self._target or ahead > 4 * self._target:
                self._cursor = newest - self._target  # start, or catch up after a long gap
            positions = np.arange(self._cursor, self._cursor + n, dtype=np.int64)
            slots = positions % self._capacity
            held = self._stamp[slots] == positions
            out[held] = self._ring[slots[held]]
            self._cursor += n
        self.played += n
        self.missing += int(n - held.sum())
        self.last_peak = audio.peak(out)
        return out

    def gap_ratio(self) -> float:
        return self.missing / self.played if self.played else 0.0


class ListenerClient:
    """At the listener: says hello to the control room and feeds the player."""

    def __init__(
        self,
        *,
        server: tuple[str, int],
        player: StreamPlayer,
        bind_host: str = "0.0.0.0",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._server = server
        self._player = player
        self._clock = clock
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._socket.bind((bind_host, 0))
        self._socket.settimeout(0.05)
        self._decoder = opus.OpusDecoder()
        self._stop = threading.Event()
        self.error: str | None = None
        self.rejected = 0
        self._thread = threading.Thread(target=self._run, name="djmidi-remote-listener", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._socket.close()

    def _hello(self) -> None:
        try:
            self._socket.sendto(probe.encode({"k": "listen"}), self._server)
        except OSError as exc:
            self.error = str(exc)

    def _run(self) -> None:
        next_hello = self._clock()
        while not self._stop.is_set():
            if self._clock() >= next_hello:
                self._hello()
                next_hello = self._clock() + HELLO_INTERVAL_S
            try:
                data, address = self._socket.recvfrom(audio.MAX_PACKET + 1)
            except TimeoutError:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.error = str(exc)
                continue
            packet = audio.decode_packet(data, self._decoder) if address[0] == self._server[0] else None
            if packet is None:
                self.rejected += 1
                continue
            self._player.push(packet)
