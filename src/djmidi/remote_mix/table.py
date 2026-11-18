"""The shared mixer of Mix Together (remote mix, phase 6), Qt-free.

Both DJs already have both sounds (their own, and the other one bar late on
the grid), so the mixer doesn't send mixed sound: it shares its **settings**.
Every move of a fader, knob or the crossfader travels as a tiny message on the
control line, and each computer applies it to its own copy of the mixer, so
both DJs see and hear the same mixer.

On the wire the controls are named by owner, not by "me" / "them": the host's
channel is ``host_*``, the joining DJ's ``guest_*``, and the crossfader runs
from the host (0) to the guest (100). Each side maps that onto its own view
(its own channel is "me", its crossfader has itself on the left).

Two DJs may move the same control at once: the last gesture wins. Every value
carries a Lamport stamp (a counter both sides keep ahead of anything they've
seen, then the host before the guest on a tie), so a lost or late packet can
never undo a newer move, and a regular full snapshot repairs lost packets.
"""

from __future__ import annotations

from dataclasses import dataclass

from djmidi.remote_mix import controls

HOST = "host"
GUEST = "guest"
MESSAGE_KIND = "mix"
CROSSFADER_TOP = 100
_RANK = {GUEST: 0, HOST: 1}


def _wire_name(local: str, role: str) -> str:
    """'me_low' → 'host_low' on the host, 'guest_low' on the guest."""
    if local == controls.CROSSFADER:
        return local
    other = GUEST if role == HOST else HOST
    for side, owner in ((controls.ME, role), (controls.THEM, other)):
        if local == side:
            return f"{owner}_volume"
        if local.startswith(side + "_"):
            return owner + local[len(side) :]
    raise ValueError(local)


def _local_name(wire: str, role: str) -> str | None:
    if wire == controls.CROSSFADER:
        return wire
    owner, _, rest = wire.partition("_")
    if owner not in _RANK or not rest:
        return None
    side = controls.ME if owner == role else controls.THEM
    name = side if rest == "volume" else f"{side}_{rest}"
    return name if name in controls.TARGETS else None


@dataclass(frozen=True)
class Stamp:
    counter: int
    rank: int

    def newer_than(self, other: Stamp | None) -> bool:
        return other is None or (self.counter, self.rank) > (other.counter, other.rank)


class SharedTable:
    """This side's copy of the shared mixer (values in local terms)."""

    def __init__(self, role: str) -> None:
        if role not in _RANK:
            raise ValueError(role)
        self.role = role
        self._counter = 0
        self.values: dict[str, int] = {}
        self._stamps: dict[str, Stamp] = {}

    def _wire_value(self, local: str, value: int) -> int:
        if local == controls.CROSSFADER and self.role == GUEST:
            return CROSSFADER_TOP - value
        return value

    def _local_value(self, local: str, value: int) -> int:
        return self._wire_value(local, value)  # the crossfader flip is its own inverse

    def _entry(self, local: str) -> list[int]:
        stamp = self._stamps[local]
        return [self._wire_value(local, self.values[local]), stamp.counter, stamp.rank]

    def local_change(self, local: str, value: int) -> dict:
        """A move on this side: remember it and return the message to send."""
        self._counter += 1
        self.values[local] = int(value)
        self._stamps[local] = Stamp(self._counter, _RANK[self.role])
        return {"k": MESSAGE_KIND, "c": {_wire_name(local, self.role): self._entry(local)}}

    def snapshot(self) -> dict | None:
        """Every control this side has a value for (sent regularly to repair lost packets)."""
        if not self.values:
            return None
        return {"k": MESSAGE_KIND, "c": {_wire_name(local, self.role): self._entry(local) for local in self.values}}

    def receive(self, message: dict) -> list[tuple[str, int]]:
        """The other side's message → the (local control, value) changes to apply here."""
        changes: list[tuple[str, int]] = []
        entries = message.get("c")
        if message.get("k") != MESSAGE_KIND or not isinstance(entries, dict):
            return changes
        for wire, raw in entries.items():
            local = _local_name(str(wire), self.role)
            if local is None or not isinstance(raw, list) or len(raw) != 3:
                continue
            if not all(isinstance(part, int) and not isinstance(part, bool) for part in raw):
                continue
            value, counter, rank = raw
            stamp = Stamp(counter, rank)
            self._counter = max(self._counter, counter)
            if not stamp.newer_than(self._stamps.get(local)):
                continue
            value = self._local_value(local, value)
            self._stamps[local] = stamp
            if self.values.get(local) != value:
                self.values[local] = value
                changes.append((local, value))
        return changes
