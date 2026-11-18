"""Hear each other on the grid (remote mix, phase 2).

Every audio packet carries the sender's Ableton Link beat at its first sample.
Once phase 1 keeps both Link sessions on one beat, the receiver plays a
sample when its *own* Link beat reaches that beat plus one bar: the other DJ
always lands exactly one bar late, on your grid, whatever the line's latency
(as long as it stays under a bar). No latency has to be measured; a small
**fine-tune** absorbs the sound cards' own delays.

Qt-free: packets, the bar-aligned player, the UDP link and the mixer maths.
The GUI feeds it from QtMultimedia devices.

Sound is sent as 16-bit PCM, either at 48 kHz (about 1.5 Mb/s per direction)
or at 24 kHz ("light", about 0.8 Mb/s). Packets hold 5 ms so they fit a
standard 1500-byte internet packet.
"""

from __future__ import annotations

import logging
import math
import socket
import struct
import threading
from dataclasses import dataclass

import numpy as np

_LOGGER = logging.getLogger(__name__)

RATE = 48_000
CHANNELS = 2
PACKET_FRAMES = 240  # 5 ms at 48 kHz
CODEC_PCM48 = 0
CODEC_PCM24 = 1
CODECS = (CODEC_PCM48, CODEC_PCM24)
QUANTUM = 4.0
AUDIO_PORT_OFFSET = 1  # audio uses the test port + 1

_MAGIC = b"DJMA"
_VERSION = 1
_HEADER = struct.Struct(">4sBBBBQdfH")  # magic, version, codec, channels, pad, position, beat, tempo, frames
MAX_PACKET = _HEADER.size + PACKET_FRAMES * CHANNELS * 2


@dataclass(frozen=True)
class AudioPacket:
    position: int  # first sample, counted at 48 kHz since the sender started
    beat: float  # sender's Link beat at that sample
    tempo: float
    samples: np.ndarray  # float32 (frames at 48 kHz, CHANNELS), -1..1
    codec: int = CODEC_PCM48


def _to_pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype(">i2").tobytes()


def encode_packet(packet: AudioPacket) -> bytes:
    samples = packet.samples
    if packet.codec == CODEC_PCM24:
        even = samples[: len(samples) // 2 * 2]
        samples = (even[0::2] + even[1::2]) * 0.5
    header = _HEADER.pack(
        _MAGIC, _VERSION, packet.codec, CHANNELS, 0, packet.position, packet.beat, packet.tempo, len(samples)
    )
    return header + _to_pcm(samples)


def decode_packet(data: bytes) -> AudioPacket | None:
    """A packet from another DJ MIDI Studio, or None for anything else."""
    if len(data) < _HEADER.size or len(data) > MAX_PACKET:
        return None
    magic, version, codec, channels, _pad, position, beat, tempo, frames = _HEADER.unpack_from(data)
    if magic != _MAGIC or version != _VERSION or codec not in CODECS or channels != CHANNELS:
        return None
    if len(data) != _HEADER.size + frames * channels * 2 or not math.isfinite(beat) or not tempo > 0:
        return None
    pcm = np.frombuffer(data, dtype=">i2", offset=_HEADER.size).astype(np.float32) / 32767.0
    samples = pcm.reshape(frames, channels)
    if codec == CODEC_PCM24:
        samples = np.repeat(samples, 2, axis=0)
    return AudioPacket(position=position, beat=beat, tempo=tempo, samples=samples, codec=codec)


def packetize(samples: np.ndarray, position: int, beat: float, tempo: float, codec: int) -> list[AudioPacket]:
    """Cut a captured block into 5 ms packets, each stamped with its own beat."""
    packets = []
    for start in range(0, len(samples), PACKET_FRAMES):
        chunk = samples[start : start + PACKET_FRAMES]
        packets.append(
            AudioPacket(
                position=position + start,
                beat=beat + start / RATE * tempo / 60.0,
                tempo=tempo,
                samples=chunk,
                codec=codec,
            )
        )
    return packets


class BarAlignedPlayer:
    """Holds the other DJ's sound and gives it back one bar after its beat.

    ``read(n, beat)`` returns the ``n`` samples to be heard when the local Link
    beat is ``beat``: the sender's samples stamped ``beat - quantum``. The
    cursor runs on by itself and only jumps when it has drifted more than
    ``resync_ms`` from where the beats say it should be, so a jittery line
    doesn't make the sound crackle. Missing samples play as silence.
    """

    def __init__(self, *, capacity_s: float = 8.0, quantum: float = QUANTUM, resync_ms: float = 8.0) -> None:
        self._capacity = int(capacity_s * RATE)
        self._ring = np.zeros((self._capacity, CHANNELS), dtype=np.float32)
        self._stamp = np.full(self._capacity, -1, dtype=np.int64)  # absolute position held by each slot
        self._quantum = quantum
        self._resync = resync_ms / 1000.0 * RATE
        self._lock = threading.Lock()
        self._anchor: tuple[int, float, float] | None = None  # (position, beat, tempo) of the newest packet
        self._cursor: int | None = None
        self.received = 0
        self.played = 0
        self.missing = 0
        self.resyncs = 0
        self.last_peak = 0.0

    def push(self, packet: AudioPacket) -> None:
        n = len(packet.samples)
        positions = np.arange(packet.position, packet.position + n, dtype=np.int64)
        slots = positions % self._capacity
        with self._lock:
            self._ring[slots] = packet.samples
            self._stamp[slots] = positions
            if self._anchor is None or packet.position >= self._anchor[0]:
                self._anchor = (packet.position, packet.beat, packet.tempo)
            self.received += 1

    def target_position(self, beat: float) -> float | None:
        with self._lock:
            anchor = self._anchor
        if anchor is None:
            return None
        position, anchor_beat, tempo = anchor
        return position + (beat - self._quantum - anchor_beat) * 60.0 / tempo * RATE

    def read(self, n: int, beat: float) -> np.ndarray:
        out = np.zeros((n, CHANNELS), dtype=np.float32)
        target = self.target_position(beat)
        if target is None:
            return out
        if self._cursor is None or abs(target - self._cursor) > self._resync:
            if self._cursor is not None:
                self.resyncs += 1
            self._cursor = round(target)
        positions = np.arange(self._cursor, self._cursor + n, dtype=np.int64)
        slots = positions % self._capacity
        with self._lock:
            held = self._stamp[slots] == positions
            out[held] = self._ring[slots[held]]
        self._cursor += n
        self.played += n
        self.missing += int(n - held.sum())
        self.last_peak = peak(out)
        return out

    def gap_ratio(self) -> float:
        return self.missing / self.played if self.played else 0.0


def peak(samples: np.ndarray) -> float:
    return float(np.max(np.abs(samples))) if samples.size else 0.0


def crossfade_gains(position: float) -> tuple[float, float]:
    """Constant-power gains (me, them) for a crossfader at 0 (all me) .. 1 (all them)."""
    position = min(1.0, max(0.0, position))
    return math.cos(position * math.pi / 2), math.sin(position * math.pi / 2)


def program_mix(me: np.ndarray, them: np.ndarray, me_volume: float, them_volume: float, crossfader: float) -> np.ndarray:
    """The mix that gets recorded or streamed: both DJs, through the crossfader."""
    a, b = crossfade_gains(crossfader)
    n = min(len(me), len(them))
    return np.clip(me[:n] * (me_volume * a) + them[:n] * (them_volume * b), -1.0, 1.0)


class AudioLink:
    """The UDP socket the sound travels on (one per side, test port + 1).

    Packets are taken only from ``peer_host``; received packets go straight
    into ``player`` from a worker thread.
    """

    def __init__(self, *, port: int, peer: tuple[str, int], player: BarAlignedPlayer, bind_host: str = "0.0.0.0") -> None:
        self._peer = peer
        self._player = player
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._socket.bind((bind_host, port))
        self._socket.settimeout(0.05)
        self._stop = threading.Event()
        self.sent = 0
        self.rejected = 0
        self.error: str | None = None
        self._thread = threading.Thread(target=self._run, name="djmidi-remote-audio", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self._socket.getsockname()[1]

    def send(self, packets: list[AudioPacket]) -> None:
        for packet in packets:
            try:
                self._socket.sendto(encode_packet(packet), self._peer)
                self.sent += 1
            except OSError as exc:
                self.error = str(exc)
                return

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._socket.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data, address = self._socket.recvfrom(MAX_PACKET + 1)
            except TimeoutError:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.error = str(exc)
                continue
            packet = decode_packet(data) if address[0] == self._peer[0] else None
            if packet is None:
                self.rejected += 1
                continue
            self._player.push(packet)
