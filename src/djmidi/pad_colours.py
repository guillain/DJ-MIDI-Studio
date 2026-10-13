"""Pad LED colours for controllers whose official MIDI documentation
defines a velocity -> colour table (issue #232).

Qt-free so the Controller Emulator, the sync-set store and tests share one
contract. A :class:`PadColourPalette` holds one controller's documented
colours and the documented note each pad's LED listens on; a colour is
just a Note On whose velocity selects it, so a chosen colour turns into a
:class:`~djmidi.controller_sync.SyncMessage` and lands in that controller's
sync set (:func:`merge_into_sync_set`) -- sent again on every Sync.

Only documented palettes are registered, never guessed ones. Of the
controller documents bundled under ``controllers/``, only the Hercules
DJControl Inpulse 500 sheet prints a velocity -> colour table (page 5,
"COLOR PER DATA2 VALUE ON PAD MIDI OUT", repeated for deck 2 on page 14);
every Pioneer / AlphaTheta MIDI message list only says a pad is "lit in
color specified in color number (1-127)" without saying which number is
which colour, so no Pioneer palette exists here.

The pad notes come from the same Hercules sheet, not from
``catalog/hercules_inpulse_500.py``, whose community-sourced pad entries
(channels 1/2, notes 40-47) don't match that document (deck 1 pads on
status 0x96, deck 2 on 0x97, note = 16 * (mode - 1) + (pad - 1), +8 with
SHIFT). The LED note equals the pad's input note there ("MIDI OUT" columns
repeat the "MIDI IN" ones), and each pad mode / SHIFT layer has its own
note, so a colour is stored per deck, pad, mode and layer.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from djmidi.controller_sync import ControllerSyncSet, SyncMessage, normalize_scene


@dataclass(frozen=True)
class PadColour:
    name: str
    velocity: int
    # Approximate on-screen swatch, sampled from the document's own colour
    # bars -- display only, never sent anywhere.
    swatch: str


@dataclass(frozen=True)
class PadSlot:
    """One pad LED: deck and pad are 1-based, ``mode`` is the pad mode
    (1-based), ``shift`` the SHIFT layer."""

    deck: int
    pad: int
    mode: int = 1
    shift: bool = False


@dataclass(frozen=True)
class PadColourPalette:
    controller: str
    colours: tuple[PadColour, ...]
    decks: int
    pads: int
    modes: int
    # PadSlot -> (1-based MIDI channel, note) of that pad's LED.
    led_address: Callable[[PadSlot], tuple[int, int]]
    # Where the table comes from (relative to controllers/), for the docs.
    source: str

    def colour_for_velocity(self, velocity: int) -> PadColour | None:
        return next((colour for colour in self.colours if colour.velocity == velocity), None)

    def colour_named(self, name: str) -> PadColour | None:
        return next((colour for colour in self.colours if colour.name == name), None)

    def slots(self) -> list[PadSlot]:
        return [
            PadSlot(deck, pad, mode, shift)
            for deck in range(1, self.decks + 1)
            for mode in range(1, self.modes + 1)
            for shift in (False, True)
            for pad in range(1, self.pads + 1)
        ]

    def check_slot(self, slot: PadSlot) -> None:
        if not (1 <= slot.deck <= self.decks and 1 <= slot.pad <= self.pads and 1 <= slot.mode <= self.modes):
            raise ValueError(f"{self.controller} has no pad {slot}")

    def message_for(self, slot: PadSlot, colour: PadColour) -> SyncMessage:
        """The Note On that lights ``slot`` in ``colour``."""
        self.check_slot(slot)
        if colour not in self.colours:
            raise ValueError(f"{colour.name!r} is not a documented {self.controller} pad colour")
        channel, note = self.led_address(slot)
        return SyncMessage.create("Note On", channel, note, colour.velocity)

    def slot_for_message(self, message: SyncMessage) -> PadSlot | None:
        """The pad a Note On addresses, or ``None`` if it isn't a pad LED."""
        if message.event_type != "Note On":
            return None
        return self._slots_by_address().get((message.channel, message.data1))

    def _slots_by_address(self) -> dict[tuple[int, int], PadSlot]:
        return {self.led_address(slot): slot for slot in self.slots()}


# Hercules DJControl Inpulse 500 -- page 5 of the bundled product sheet,
# read from a 300 DPI render (velocities in hex as printed there).
_INPULSE_500_COLOURS = (
    PadColour("No light", 0x00, "#000000"),
    PadColour("Blue low", 0x02, "#000033"),
    PadColour("Blue", 0x03, "#0000ff"),
    PadColour("Green low", 0x10, "#003300"),
    PadColour("Cyan low", 0x12, "#003333"),
    PadColour("Green", 0x1C, "#00ff00"),
    PadColour("Cyan", 0x1F, "#00ffff"),
    PadColour("Lime low", 0x30, "#223300"),
    PadColour("Red low", 0x40, "#330000"),
    PadColour("Fuchsia low", 0x42, "#330033"),
    PadColour("Orange low", 0x4C, "#331d00"),
    PadColour("Yellow low", 0x50, "#333300"),
    PadColour("White low", 0x52, "#333333"),
    PadColour("Lime", 0x5C, "#33ff00"),
    PadColour("Red", 0x60, "#ff0000"),
    PadColour("Fuchsia", 0x63, "#ff00ff"),
    PadColour("Orange", 0x74, "#ff6622"),
    PadColour("Yellow", 0x7C, "#ffff00"),
    PadColour("White", 0x7F, "#ffffff"),
)


def _inpulse_500_led_address(slot: PadSlot) -> tuple[int, int]:
    # Deck 1 pads on status 0x96 (channel 7), deck 2 on 0x97 (channel 8);
    # 16 notes per pad mode, the SHIFT layer 8 above the plain one.
    return 6 + slot.deck, 16 * (slot.mode - 1) + (slot.pad - 1) + (8 if slot.shift else 0)


_PALETTES: dict[str, PadColourPalette] = {}


def register_palette(palette: PadColourPalette) -> None:
    _PALETTES[palette.controller] = palette


def palette_for(controller: str) -> PadColourPalette | None:
    """The documented palette of ``controller``, or ``None``."""
    return _PALETTES.get(controller)


def palette_controllers() -> list[str]:
    return sorted(_PALETTES)


register_palette(
    PadColourPalette(
        controller="Hercules DJControl Inpulse 500",
        colours=_INPULSE_500_COLOURS,
        decks=2,
        pads=8,
        modes=8,
        led_address=_inpulse_500_led_address,
        source="hardware/hercules/DJControl-Inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf",
    )
)


_PAD_NUMBER = re.compile(r"\bPad (\d+)\b")


def pad_number(label: str) -> int | None:
    """``"Pad 3"`` / ``"Deck 2 Pad 3 (R)"`` -> ``3``; ``None`` otherwise."""
    match = _PAD_NUMBER.search(label)
    return int(match.group(1)) if match else None


def colours_from_messages(palette: PadColourPalette, messages: Iterable[SyncMessage]) -> dict[PadSlot, PadColour]:
    """The pad colours a sync set's messages leave each pad in (the last
    message for a pad wins, as when they are sent). Velocities outside the
    documented table are ignored."""
    by_address = palette._slots_by_address()
    colours: dict[PadSlot, PadColour] = {}
    for message in messages:
        if message.event_type != "Note On":
            continue
        slot = by_address.get((message.channel, message.data1))
        colour = palette.colour_for_velocity(message.data2)
        if slot is not None and colour is not None:
            colours[slot] = colour
    return colours


def merge_into_sync_set(
    palette: PadColourPalette,
    existing: ControllerSyncSet | None,
    colours: Mapping[PadSlot, PadColour],
    scene: str | None = None,
) -> ControllerSyncSet:
    """``existing`` (or a new set for the palette's controller) with one
    Note On per entry of ``colours``: a message already addressing that pad
    is replaced in place, the others are appended in pad order, and every
    unrelated message is kept untouched."""
    pending = {palette.led_address(slot): palette.message_for(slot, colour) for slot, colour in colours.items()}
    messages: list[SyncMessage] = []
    for message in existing.messages if existing is not None else ():
        address = (message.channel, message.data1)
        if message.event_type == "Note On" and address in pending:
            messages.append(pending.pop(address))
        else:
            messages.append(message)
    messages.extend(pending[address] for address in sorted(pending))
    if existing is None:
        return ControllerSyncSet(palette.controller, messages=tuple(messages), scene=normalize_scene(scene))
    return existing.with_messages(messages)


__all__ = [
    "PadColour",
    "PadColourPalette",
    "PadSlot",
    "colours_from_messages",
    "merge_into_sync_set",
    "pad_number",
    "palette_controllers",
    "palette_for",
    "register_palette",
]
