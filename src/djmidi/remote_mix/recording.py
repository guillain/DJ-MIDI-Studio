"""Recording the program mix at the régie (remote mix, phase 7), Qt-free.

The régie is the one computer that makes the official mix: both DJs through
the shared mixer. It can write that mix to a WAV file (48 kHz, stereo,
16-bit) in the workspace's Exports folder, block by block as it is played, so
a long set never sits in memory.

With separate tracks (phase 13), each DJ's own sound is also written to its
own WAV, before their EQ and fader, on the same timeline as the mix (a DJ who
joins later starts with silence), so the set can be re-edited afterwards.
"""

from __future__ import annotations

import re
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


def stem_name(started: datetime, dj: int, name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:30]
    return f"mix-together-{started:%Y%m%d-%H%M%S}-dj{dj + 1}" + (f"-{slug}" if slug else "") + ".wav"


class StemsRecorder:
    """One WAV per DJ, on the mix's timeline."""

    def __init__(self, folder: Path, started: datetime, frames_before: int = 0) -> None:
        self.folder = folder
        self.started = started
        self.frames = frames_before  # where the mix is on its timeline
        self.stems: dict[int, ProgramRecorder] = {}

    def write(self, blocks: dict[int, np.ndarray], names: dict[int, str]) -> None:
        """One block per DJ for the same stretch of time; a DJ missing here gets silence."""
        n = max((len(block) for block in blocks.values()), default=0)
        for dj, block in blocks.items():
            if dj not in self.stems:
                stem = ProgramRecorder(self.folder / stem_name(self.started, dj, names.get(dj, "")))
                if self.frames:
                    stem.write(np.zeros((self.frames, CHANNELS), dtype=np.float32))
                self.stems[dj] = stem
            self.stems[dj].write(block)
        for dj, stem in self.stems.items():
            if dj not in blocks and n:
                stem.write(np.zeros((n, CHANNELS), dtype=np.float32))
        self.frames += n

    @property
    def paths(self) -> list[Path]:
        return [stem.path for stem in self.stems.values()]

    def close(self) -> None:
        for stem in self.stems.values():
            stem.close()
