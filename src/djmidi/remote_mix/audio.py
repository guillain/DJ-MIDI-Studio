"""Hear each other on the grid (remote mix, phase 2).

Every audio packet carries the sender's Ableton Link beat at its first sample.
Once phase 1 keeps both Link sessions on one beat, the receiver plays a
sample when its *own* Link beat reaches that beat plus one bar: the other DJ
always lands exactly one bar late, on your grid, whatever the line's latency
(as long as it stays under a bar). No latency has to be measured; a small
**fine-tune** absorbs the sound cards' own delays.

Qt-free: packets, the bar-aligned player, the UDP link and the mixer maths.
The GUI feeds it from QtMultimedia devices.

Sound is sent compressed with Opus (about 0.25 Mb/s per direction, see
``opus.py``) or as 16-bit PCM, at 48 kHz (about 1.5 Mb/s) or 24 kHz ("light",
about 0.8 Mb/s). Packets hold 5 ms so they fit a standard 1500-byte internet
packet.
"""

from __future__ import annotations

import logging
import math
import socket
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from djmidi.remote_mix import opus

_LOGGER = logging.getLogger(__name__)

RATE = 48_000
CHANNELS = 2
PACKET_FRAMES = 240  # 5 ms at 48 kHz
CODEC_PCM48 = 0
CODEC_PCM24 = 1
CODEC_OPUS = 2
CODECS = (CODEC_PCM48, CODEC_PCM24, CODEC_OPUS)
_OPUS_MAX = 1275  # the largest Opus frame
QUANTUM = 4.0
AUDIO_PORT_OFFSET = 1  # audio uses the test port + 1

_MAGIC = b"DJMA"
_VERSION = 2  # 2: signed positions (Opus look-ahead), Opus codec
_HEADER = struct.Struct(">4sBBBBqdfH")  # magic, version, codec, channels, source, position, beat, tempo, frames
_SOURCE_BYTE = 7  # which DJ the sound is from (phase 9): the hub stamps it when it relays
MAX_PACKET = _HEADER.size + max(PACKET_FRAMES * CHANNELS * 2, _OPUS_MAX)


@dataclass(frozen=True)
class AudioPacket:
    position: int  # first sample, counted at 48 kHz since the sender started
    beat: float  # sender's Link beat at that sample
    tempo: float
    samples: np.ndarray  # float32 (frames at 48 kHz, CHANNELS), -1..1
    codec: int = CODEC_PCM48
    source: int = 0  # DJ id: 0 the host, 1-3 the guests


def _to_pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype(">i2").tobytes()


def _header(packet: AudioPacket, frames: int) -> bytes:
    return _HEADER.pack(
        _MAGIC, _VERSION, packet.codec, CHANNELS, packet.source, packet.position, packet.beat, packet.tempo, frames
    )


def encode_opus(packet: AudioPacket, encoder: opus.OpusEncoder) -> list[bytes]:
    """A full 5 ms packet through Opus. The encoder's look-ahead shifts the
    sound, so each datagram is stamped with the input sample it really starts at."""
    datagrams = []
    beats_per_frame = packet.tempo / 60.0 / RATE
    for start, payload in encoder.encode(packet.samples, packet.position):
        shifted = AudioPacket(
            position=start,
            beat=packet.beat + (start - packet.position) * beats_per_frame,
            tempo=packet.tempo,
            samples=packet.samples,
            codec=CODEC_OPUS,
            source=packet.source,
        )
        datagrams.append(_header(shifted, PACKET_FRAMES) + payload)
    return datagrams


def encode_packet(packet: AudioPacket) -> bytes:
    """A PCM packet (Opus goes through ``encode_opus``, which keeps state)."""
    if packet.codec == CODEC_OPUS:
        raise ValueError("Opus packets need an encoder: use encode_opus")
    samples = packet.samples
    if packet.codec == CODEC_PCM24:
        even = samples[: len(samples) // 2 * 2]
        samples = (even[0::2] + even[1::2]) * 0.5
    return _header(packet, len(samples)) + _to_pcm(samples)


def decode_packet(data: bytes, decoder: opus.OpusDecoder | None = None) -> AudioPacket | None:
    """A packet from another DJ MIDI Studio, or None for anything else (an
    Opus packet needs the link's ``decoder``)."""
    if len(data) < _HEADER.size or len(data) > MAX_PACKET:
        return None
    magic, version, codec, channels, source, position, beat, tempo, frames = _HEADER.unpack_from(data)
    if magic != _MAGIC or version != _VERSION or codec not in CODECS or channels != CHANNELS:
        return None
    if not math.isfinite(beat) or not tempo > 0:
        return None
    if codec == CODEC_OPUS:
        if decoder is None or frames != PACKET_FRAMES:
            return None
        samples = decoder.decode(data[_HEADER.size :])
        if samples is None or len(samples) != frames:
            return None
        return AudioPacket(position=position, beat=beat, tempo=tempo, samples=samples, codec=codec, source=source)
    if len(data) != _HEADER.size + frames * channels * 2:
        return None
    pcm = np.frombuffer(data, dtype=">i2", offset=_HEADER.size).astype(np.float32) / 32767.0
    samples = pcm.reshape(frames, channels)
    if codec == CODEC_PCM24:
        samples = np.repeat(samples, 2, axis=0)
    return AudioPacket(position=position, beat=beat, tempo=tempo, samples=samples, codec=codec, source=source)


TALK_FLAG = 0x80  # in the source byte: a DJ's voice (talkback), not their music


def packet_source(data: bytes) -> int | None:
    return data[_SOURCE_BYTE] if len(data) > _SOURCE_BYTE else None


def with_source(data: bytes, source: int) -> bytes:
    """The same datagram, stamped as coming from DJ ``source`` (the hub does it when relaying)."""
    return data[:_SOURCE_BYTE] + bytes([source]) + data[_SOURCE_BYTE + 1 :]


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


class SendBuffer:
    """Turns captured blocks of any size into whole 5 ms packets (Opus only
    takes whole frames); the remainder waits for the next block."""

    def __init__(self) -> None:
        self._pending = np.zeros((0, CHANNELS), dtype=np.float32)
        self._position = 0
        self._beat = 0.0

    def add(self, block: np.ndarray, position: int, beat: float, tempo: float, codec: int) -> list[AudioPacket]:
        """``block`` starts at sample ``position`` and Link beat ``beat``."""
        held = len(self._pending)
        if held == 0 or self._position + held != position:
            self._pending = np.zeros((0, CHANNELS), dtype=np.float32)
            self._position, self._beat = position, beat
        else:
            self._beat = beat - held / RATE * tempo / 60.0
        self._pending = np.concatenate([self._pending, block.astype(np.float32, copy=False)])
        whole = len(self._pending) // PACKET_FRAMES * PACKET_FRAMES
        packets = packetize(self._pending[:whole], self._position, self._beat, tempo, codec)
        self._pending = self._pending[whole:]
        self._position += whole
        self._beat += whole / RATE * tempo / 60.0
        return packets


PLAY_MARGIN_S = 0.1  # least time a packet waits before it plays


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
        self._bars = 0.0  # whole bars added to the sender's beat numbers
        self.rebars = 0
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
        # Two homes never count beats from the same zero (two Link sessions, or
        # our listening clock): only the phase within the bar is shared. Play
        # whole bars behind the newest packet, at least a margin late; keep
        # that choice while it holds so the sound never jumps a bar.
        lag = anchor_beat + self._quantum - beat + self._bars  # beats behind the newest packet
        margin = PLAY_MARGIN_S * tempo / 60.0
        if not 0.0 <= lag <= 2 * self._quantum + margin:
            self._bars = self._quantum * math.floor((beat - anchor_beat - self._quantum + margin) / self._quantum + 1)
            lag = anchor_beat + self._quantum - beat + self._bars
            self.rebars += 1
        return position - lag * 60.0 / tempo * RATE

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


def strip_gain(assign: int, crossfader: float) -> float:
    """A strip's crossfader gain: side A (0), through (1) or side B (2)."""
    a, b = crossfade_gains(crossfader)
    return a if assign == 0 else b if assign == 2 else 1.0


def mix_strips(strips: list[tuple[np.ndarray, float, int]], crossfader: float, frames: int) -> np.ndarray:
    """The program mix of several DJs: (samples, volume, crossfader assign) each."""
    out = np.zeros((frames, CHANNELS), dtype=np.float32)
    for samples, volume, assign in strips:
        n = min(frames, len(samples))
        out[:n] += samples[:n] * (volume * strip_gain(assign, crossfader))
    return np.clip(out, -1.0, 1.0)


class PlayerBank:
    """One bar-aligned player per other DJ, made when their sound first arrives."""

    def __init__(self) -> None:
        self._players: dict[int, BarAlignedPlayer] = {}
        self._lock = threading.Lock()

    def get(self, dj: int) -> BarAlignedPlayer:
        with self._lock:
            if dj not in self._players:
                self._players[dj] = BarAlignedPlayer()
            return self._players[dj]

    def items(self) -> list[tuple[int, BarAlignedPlayer]]:
        with self._lock:
            return sorted(self._players.items())


class AudioLink:
    """The UDP socket the sound travels on (one per computer, test port + 1).

    Two DJs: each side sends to the other. Several DJs (phase 9): a star around
    the host. A guest sends to the host and hears everyone from it; the host
    (``hub``) sends its own sound to every guest, and relays each guest's
    packets to the other guests, stamped with that guest's DJ id. Received
    packets go straight into the ``players`` bank (one per DJ) from a worker
    thread; ``player`` alone serves the two-DJ case.
    """

    def __init__(
        self,
        *,
        port: int,
        peer: tuple[str, int],
        player: BarAlignedPlayer | None = None,
        bind_host: str = "0.0.0.0",
        players: PlayerBank | None = None,
        peer_ids: Callable[[], dict[str, int]] | None = None,
        hub: bool = False,
        me: Callable[[], int | None] | None = None,
    ) -> None:
        self._peer = peer
        self._player = player
        self._players = players
        self._peer_ids = peer_ids
        self._hub = hub
        self._me = me
        self._port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._socket.bind((bind_host, port))
        self._socket.settimeout(0.05)
        self._stop = threading.Event()
        self.sent = 0
        self.rejected = 0
        self.relayed = 0
        self.error: str | None = None
        self._encoder: opus.OpusEncoder | None = None
        self._talk_encoder: opus.OpusEncoder | None = None
        self.talk_sink: Callable[[int, AudioPacket], None] | None = None  # who talks, their voice packet
        self._decoders: dict[int, opus.OpusDecoder] = {}
        self._thread = threading.Thread(target=self._run, name="djmidi-remote-audio", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self._socket.getsockname()[1]

    def _targets(self) -> list[tuple[str, int]]:
        if self._hub and self._peer_ids is not None:
            return [(ip, self._peer[1]) for ip in self._peer_ids()]
        return [self._peer]

    def send(self, packets: list[AudioPacket]) -> None:
        self._send(packets, talk=False)

    def send_talk(self, packets: list[AudioPacket]) -> None:
        """This DJ's voice (talkback): played at once by the others, never in the mix."""
        self._send(packets, talk=True)

    def _send(self, packets: list[AudioPacket], *, talk: bool) -> None:
        source = (self._me() if self._me is not None else 0) or 0
        if talk:
            source |= TALK_FLAG
        targets = self._targets()
        for packet in packets:
            packet = AudioPacket(packet.position, packet.beat, packet.tempo, packet.samples, packet.codec, source)
            try:
                if packet.codec == CODEC_OPUS:
                    if talk:
                        if self._talk_encoder is None:
                            self._talk_encoder = opus.OpusEncoder()
                        encoder = self._talk_encoder
                    else:
                        if self._encoder is None:
                            self._encoder = opus.OpusEncoder()
                        encoder = self._encoder
                    datagrams = encode_opus(packet, encoder)
                else:
                    datagrams = [encode_packet(packet)]
                for datagram in datagrams:
                    for target in targets:
                        self._socket.sendto(datagram, target)
                        self.sent += 1
            except OSError as exc:
                self.error = str(exc)
                return

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._socket.close()

    def _decoder(self, source: int) -> opus.OpusDecoder | None:
        if opus.unavailable():
            return None
        if source not in self._decoders:
            self._decoders[source] = opus.OpusDecoder()  # Opus streams keep state: one decoder per DJ
        return self._decoders[source]

    def _source_of(self, data: bytes, ip: str) -> int | None:
        """Which DJ a datagram is from, or None when it isn't from someone we mix with."""
        talk = (packet_source(data) or 0) & TALK_FLAG
        if self._hub and self._peer_ids is not None:
            dj = self._peer_ids().get(ip)
            return None if dj is None else dj | talk
        if ip != self._peer[0]:
            return None
        return packet_source(data) if self._players is not None else talk

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
            source = self._source_of(data, address[0])
            if source is None:
                self.rejected += 1
                continue
            if self._hub:
                data = with_source(data, source)
                for target in self._targets():
                    if target[0] != address[0]:
                        try:
                            self._socket.sendto(data, target)  # the hub relays to the other guests
                            self.relayed += 1
                        except OSError as exc:
                            self.error = str(exc)
            packet = decode_packet(data, self._decoder(source))
            if packet is None:
                self.rejected += 1
                continue
            if source & TALK_FLAG:
                sink = self.talk_sink
                if sink is not None:
                    sink(source & ~TALK_FLAG, packet)
                continue
            player = self._players.get(source) if self._players is not None else self._player
            if player is not None:
                player.push(packet)
