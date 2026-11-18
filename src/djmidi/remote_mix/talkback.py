"""Talkback between DJs (remote mix, phase 14), Qt-free.

Hold a button (or a pad of your controller) and talk: your microphone goes
to the other DJs over the same sound line as the music, flagged as a voice
(`audio.TALK_FLAG`). A voice isn't music: it isn't held back a bar to land
on the grid, it plays as soon as it arrives (a short buffer evens it out),
only in the headphones, and never in the official mix, its recording or what
the listeners hear.

The pad is learned like the signals' pads, but it is held: talking starts on
the press and stops on the release (Note Off, or Note On at velocity 0).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from djmidi.remote_mix import audio, listen
from djmidi.remote_mix.signals import PadTrigger

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

BUFFER_MS = 60
TALKING_S = 0.6  # someone "is talking" for this long after their last loud packet
_LOUD = 0.02
FILE_NAME = "mix-together-talk.json"
FORMAT = "djmidi-mix-talk/1"
PRESS, RELEASE = "press", "release"


class TalkReceiver:
    """The other DJs' voices, one short buffer each, mixed for the headphones."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._players: dict[int, listen.StreamPlayer] = {}
        self._loud_at: dict[int, float] = {}

    def push(self, dj: int, packet: audio.AudioPacket) -> None:
        player = self._players.get(dj)
        if player is None:
            player = self._players[dj] = listen.StreamPlayer(buffer_ms=BUFFER_MS, capacity_s=2.0)
        player.push(packet)
        if audio.peak(packet.samples) > _LOUD:
            self._loud_at[dj] = self._clock()

    def read(self, n: int) -> np.ndarray:
        out = np.zeros((n, audio.CHANNELS), dtype=np.float32)
        for player in list(self._players.values()):
            out += player.read(n)
        return out

    def talking(self) -> list[int]:
        now = self._clock()
        return sorted(dj for dj, at in self._loud_at.items() if now - at <= TALKING_S)


def pad_event(event: MidiEvent, pad: PadTrigger | None) -> str | None:
    """PRESS or RELEASE when the event is the talk pad, else None."""
    if pad is None or event.direction != "in" or event.channel != pad.channel or event.data1 != pad.note:
        return None
    if event.event_type == "Note Off":
        return RELEASE
    if event.event_type != "Note On":
        return None
    try:
        return PRESS if int(event.data2) > 0 else RELEASE
    except (TypeError, ValueError):
        return None


def load_pad(path: Path) -> PadTrigger | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _LOGGER.warning("Talk pad not read from %s: %s", path, exc)
        return None
    pad = data.get("pad") if isinstance(data, dict) and data.get("format") == FORMAT else None
    if not isinstance(pad, dict):
        return None
    return PadTrigger(str(pad.get("channel", "")), str(pad.get("note", "")))


def save_pad(path: Path, pad: PadTrigger | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    body = {"format": FORMAT, "pad": None if pad is None else {"channel": pad.channel, "note": pad.note}}
    tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
    tmp.replace(path)
