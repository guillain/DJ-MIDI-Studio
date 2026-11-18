"""Recording the program mix at the régie (remote mix, phase 7), Qt-free.

The régie is the one computer that makes the official mix: both DJs through
the shared mixer. It can write that mix to a WAV file (48 kHz, stereo,
16-bit) in the workspace's Exports folder, block by block as it is played, so
a long set never sits in memory.
"""

from __future__ import annotations

import wave
from datetime import datetime
from pathlib import Path

import numpy as np

RATE = 48_000
CHANNELS = 2


def recording_name(started: datetime) -> str:
    return f"mix-together-{started:%Y%m%d-%H%M%S}.wav"


class ProgramRecorder:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = wave.open(str(path), "wb")  # noqa: SIM115 - closed by close()
        self._file.setnchannels(CHANNELS)
        self._file.setsampwidth(2)
        self._file.setframerate(RATE)
        self.frames = 0

    @property
    def seconds(self) -> float:
        return self.frames / RATE

    def write(self, samples: np.ndarray) -> None:
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
        self._file.writeframes(pcm.tobytes())
        self.frames += len(samples)

    def close(self) -> None:
        self._file.close()
