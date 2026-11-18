"""Opus compression for Mix Together's sound (remote mix, phase 4), Qt-free.

Opus at 128 kb/s stereo, 5 ms frames in low-delay mode: about 0.25 Mb/s per
direction with the packet headers, against 1.5 Mb/s for plain 48 kHz. The
codec comes from PyAV (FFmpeg's libopus, shipped inside its wheels); without
it the app keeps the uncompressed qualities.

The encoder delays the sound by a few samples (its look-ahead). Each encoded
packet says which input sample it starts at (its ``pts``), and the sender
stamps that position and beat, so the receiver still lands the sound exactly
on its grid.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np

try:  # PyAV may be missing from a source install
    import av
except ImportError as exc:  # pragma: no cover - depends on the environment
    av = None
    _IMPORT_ERROR: str | None = str(exc)
else:
    _IMPORT_ERROR = None

RATE = 48_000
FRAMES = 240  # 5 ms
BIT_RATE = 128_000


def unavailable() -> str | None:
    """Why Opus can't be used here, or None when it can."""
    return _IMPORT_ERROR


class OpusEncoder:
    def __init__(self, bit_rate: int = BIT_RATE) -> None:
        if av is None:
            raise RuntimeError(_IMPORT_ERROR)
        ctx = av.CodecContext.create("libopus", "w")
        ctx.sample_rate = RATE
        ctx.layout = "stereo"
        ctx.format = "flt"
        ctx.bit_rate = bit_rate
        ctx.time_base = Fraction(1, RATE)
        ctx.options = {"frame_duration": "5", "application": "lowdelay"}
        ctx.open()
        self._ctx = ctx

    def encode(self, samples: np.ndarray, position: int) -> list[tuple[int, bytes]]:
        """One 5 ms block (FRAMES x 2, float) → [(first input sample, packet bytes)]."""
        data = np.ascontiguousarray(np.clip(samples, -1.0, 1.0), dtype=np.float32).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(data, format="flt", layout="stereo")
        frame.sample_rate = RATE
        frame.pts = position
        return [(int(packet.pts), bytes(packet)) for packet in self._ctx.encode(frame)]


class OpusDecoder:
    def __init__(self) -> None:
        if av is None:
            raise RuntimeError(_IMPORT_ERROR)
        ctx = av.CodecContext.create("libopus", "r")
        ctx.sample_rate = RATE
        ctx.layout = "stereo"
        self._ctx = ctx

    def decode(self, payload: bytes) -> np.ndarray | None:
        """Packet bytes → float32 samples (frames x 2), or None when they don't decode."""
        try:
            frames = self._ctx.decode(av.Packet(payload))
        except (av.error.FFmpegError, ValueError):
            return None
        blocks = []
        for frame in frames:
            array = frame.to_ndarray()
            if not frame.format.is_packed:
                array = array.T
            array = array.reshape(-1, 2)
            if array.dtype == np.int16:
                array = array.astype(np.float32) / 32767.0
            blocks.append(array.astype(np.float32, copy=False))
        return np.concatenate(blocks) if blocks else None


def self_check() -> str | None:
    """Encode and decode a short tone: None when Opus works in this build, else
    what failed. The packaged app runs it with ``--self-check-opus``
    (scripts/smoke_test_executable.py) to prove PyAV and libopus are bundled."""
    if av is None:
        return f"PyAV is not installed ({_IMPORT_ERROR})"
    try:
        encoder, decoder = OpusEncoder(), OpusDecoder()
        t = np.arange(FRAMES * 20) / RATE
        tone = np.repeat((0.5 * np.sin(2 * np.pi * 440 * t))[:, None], 2, axis=1)
        heard = []
        for start in range(0, len(tone), FRAMES):
            for _position, payload in encoder.encode(tone[start : start + FRAMES], start):
                block = decoder.decode(payload)
                if block is not None:
                    heard.append(block)
    except Exception as error:  # noqa: BLE001 - reported, not hidden
        return f"{type(error).__name__}: {error}"
    if len(heard) < 10 or float(np.max(np.abs(np.concatenate(heard)))) < 0.1:
        return "Opus gave back no sound"
    return None
