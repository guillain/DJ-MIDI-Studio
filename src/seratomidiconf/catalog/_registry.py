"""The plumbing behind catalog.py's plugin-style registry: a ControllerDefinition
per controller, registered by importing its module (see catalog/__init__.py).
Add a new controller by writing one new module here, not by editing this file
or any GUI code — see catalog/__init__.py's module docstring for the steps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

NoteOrCC = Literal["NOTE", "CC"]


@dataclass(frozen=True)
class ControlInfo:
    controller: str
    section: str
    name: str
    note_or_cc: NoteOrCC
    channels: tuple[str, ...]
    data1: str


PadLookup = Callable[[str, NoteOrCC, str], "ControlInfo | None"]


@dataclass(frozen=True)
class ControllerDefinition:
    """Everything catalog.py, gui/layout.py and gui/controller_image_view.py
    need to know about one controller. `pad_count=0` (the default) means no
    pad grid — fine for a controller that's only faders/knobs/buttons."""

    name: str
    static_entries: list[ControlInfo] = field(default_factory=list)
    pad_lookup: PadLookup | None = None
    pad_count: int = 0
    pad_columns: int = 4
    # Display order for gui/layout.py's non-pad sections; sections not listed
    # here are appended after, in whatever order they were first seen.
    section_order: tuple[str, ...] = ()


def _event_kind(event_type: str | None) -> NoteOrCC | None:
    if not event_type:
        return None
    lowered = event_type.lower()
    if "note" in lowered:
        return "NOTE"
    if "control" in lowered:
        return "CC"
    return None


_REGISTRY: dict[str, ControllerDefinition] = {}


def register(definition: ControllerDefinition) -> None:
    if definition.name in _REGISTRY:
        raise ValueError(f"Controller already registered: {definition.name}")
    _REGISTRY[definition.name] = definition


def get_definition(controller: str) -> ControllerDefinition:
    try:
        return _REGISTRY[controller]
    except KeyError:
        raise ValueError(f"Unknown controller: {controller}") from None


def all_controller_names() -> list[str]:
    """In registration order (see catalog/__init__.py's import order)."""
    return list(_REGISTRY.keys())


def make_sequential_pad_lookup(
    controller: str,
    channel_to_deck: dict[str, int],
    pad_count: int,
    mode_names: list[str] | None = None,
    label: str = "Pad",
) -> PadLookup:
    """Factory for the common case: pad N (1-indexed) sits at MIDI note
    (N-1) + mode_index*16, one identical physical grid repeated per entry in
    channel_to_deck. Covers most straightforward pad controllers — write a
    bespoke function (see ddj_xp2.py) only for a non-sequential note order."""
    modes = mode_names or ["DEFAULT"]

    def pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
        if kind != "NOTE" or channel not in channel_to_deck:
            return None
        try:
            note = int(data1)
        except ValueError:
            return None
        if not 0 <= note <= 127:
            return None
        mode_index, pad0 = divmod(note, 16)
        if mode_index >= len(modes) or pad0 >= pad_count:
            return None
        deck = channel_to_deck[channel]
        mode_suffix = f" ({modes[mode_index]})" if len(modes) > 1 else ""
        name = f"Deck {deck} {label} {pad0 + 1}{mode_suffix}"
        return ControlInfo(controller, "PAD", name, "NOTE", (channel,), data1)

    return pad_lookup


__all__ = [
    "ControlInfo",
    "ControllerDefinition",
    "NoteOrCC",
    "PadLookup",
    "all_controller_names",
    "get_definition",
    "make_sequential_pad_lookup",
    "register",
]
