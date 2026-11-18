"""The shared mixer of Mix Together (remote mix, phase 6), Qt-free.

Both DJs already have both sounds (their own, and the other one bar late on
the grid), so the mixer doesn't send mixed sound: it shares its **settings**.
Every move of a fader, knob or the crossfader travels as a tiny message on the
control line, and each computer applies it to its own copy of the mixer, so
both DJs see and hear the same mixer.

Every computer shows the same mixer: one strip per DJ, named by DJ id (the
host is 0, guests 1, 2, 3: ``dj1_low``, ``dj0_volume``), and a crossfader
whose A and B sides each strip is assigned to (``dj2_xf``), as on a club
mixer.

Two DJs may move the same control at once: the last gesture wins. Every value
carries a Lamport stamp (a counter both sides keep ahead of anything they've
seen, then the lower DJ id on a tie), so a lost or late packet can
never undo a newer move, and a regular full snapshot repairs lost packets.
"""

from __future__ import annotations

from dataclasses import dataclass

HOST = 0  # DJ ids: the host is 0, guests 1, 2, 3 (phase 9)
MESSAGE_KIND = "mix"
REGIE = "regie"  # which computer makes the official mix (phase 7): the host until someone claims it
CROSSFADER = "crossfader"
CROSSFADER_TOP = 100
# Crossfader assign per strip, as on a club mixer.
XF_A, XF_THRU, XF_B = 0, 1, 2
_MAX_RANK = 100


def strip_control(dj: int, control: str) -> str:
    """'dj1_low', 'dj0_volume', 'dj2_xf': a strip's control, named the same on every computer."""
    return f"dj{dj}_{control}"


def default_assign(dj: int) -> int:
    """The host on side A, the first guest on B, the others through."""
    return XF_A if dj == HOST else XF_B if dj == 1 else XF_THRU


def _rank(dj: int) -> int:
    return _MAX_RANK - dj  # on a tie, the host's move wins, then the first guest's


@dataclass(frozen=True)
class Stamp:
    counter: int
    rank: int

    def newer_than(self, other: Stamp | None) -> bool:
        return other is None or (self.counter, self.rank) > (other.counter, other.rank)


def _three_ints(raw: object) -> bool:
    return (
        isinstance(raw, list)
        and len(raw) == 3
        and all(isinstance(part, int) and not isinstance(part, bool) for part in raw)
    )


class SharedTable:
    """This computer's copy of the shared mixer."""

    def __init__(self, me: int) -> None:
        self.me = me
        self._counter = 0
        self.values: dict[str, int] = {}
        self._stamps: dict[str, Stamp] = {}
        self._regie = HOST
        self._regie_stamp: Stamp | None = None

    @property
    def regie(self) -> int:
        return self._regie

    @property
    def regie_is_mine(self) -> bool:
        """Whether this computer makes the official program mix (the régie)."""
        return self._regie == self.me

    def _stamp(self) -> Stamp:
        self._counter += 1
        return Stamp(self._counter, _rank(self.me))

    def claim_regie(self) -> dict:
        """This computer becomes the régie; the message tells the others."""
        self._regie, self._regie_stamp = self.me, self._stamp()
        return {"k": MESSAGE_KIND, "c": {REGIE: self._regie_entry()}}

    def _regie_entry(self) -> list[int]:
        assert self._regie_stamp is not None
        return [self._regie, self._regie_stamp.counter, self._regie_stamp.rank]

    def _entry(self, name: str) -> list[int]:
        stamp = self._stamps[name]
        return [self.values[name], stamp.counter, stamp.rank]

    def local_change(self, name: str, value: int) -> dict:
        """A move on this computer: remember it and return the message to send."""
        self.values[name] = int(value)
        self._stamps[name] = self._stamp()
        return {"k": MESSAGE_KIND, "c": {name: self._entry(name)}}

    def snapshot(self) -> dict | None:
        """Every control this side has a value for (sent regularly to repair lost packets)."""
        entries = {name: self._entry(name) for name in self.values}
        if self._regie_stamp is not None:
            entries[REGIE] = self._regie_entry()
        return {"k": MESSAGE_KIND, "c": entries} if entries else None

    def receive(self, message: dict) -> list[tuple[str, int]]:
        """Another DJ's message → the (control, value) changes to apply here."""
        changes: list[tuple[str, int]] = []
        entries = message.get("c")
        if message.get("k") != MESSAGE_KIND or not isinstance(entries, dict):
            return changes
        for name, raw in entries.items():
            if not isinstance(name, str) or not _three_ints(raw):
                continue
            value, counter, rank = raw
            stamp = Stamp(counter, rank)
            self._counter = max(self._counter, counter)
            if name == REGIE:
                if 0 <= value < _MAX_RANK and stamp.newer_than(self._regie_stamp):
                    self._regie, self._regie_stamp = value, stamp
                continue
            if not _valid_name(name) or not stamp.newer_than(self._stamps.get(name)):
                continue
            self._stamps[name] = stamp
            if self.values.get(name) != value:
                self.values[name] = value
                changes.append((name, value))
        return changes


_STRIP_CONTROLS = ("volume", "low", "mid", "high", "filter", "xf")


def _valid_name(name: str) -> bool:
    if name == CROSSFADER:
        return True
    head, _, control = name.partition("_")
    return head.startswith("dj") and head[2:].isdigit() and control in _STRIP_CONTROLS
