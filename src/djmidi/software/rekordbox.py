"""Pioneer/AlphaTheta rekordbox MIDI mapping plugin (read-only).

rekordbox mappings are CSV files: an ``@file,1,<device>`` line, a ``#name,
function,type,input,deck1..4,output,deck1..4,option,comment`` header, then
one row per binding. Decoded from the 67 mappings rekordbox 7 ships and
cross-checked trigger by trigger against the PDF-based catalogs, see
`software/rekordbox/README.md`:

- column 1 is the rekordbox command, column 2 the physical control (a
  ``+Shift`` suffix is the SHIFT layer); a row whose command starts with
  ``#`` is disabled, and ``# Title`` rows / blank rows only group the rest;
- ``input`` is four hex digits, status byte then data1 (``9058`` = Note On,
  channel 1, note 88), and each non-empty deck column is either a decimal
  0-based channel offset added to the status's channel or a full four-digit
  address of its own (then ``input`` may be empty); a row with no deck
  column is global, on the status's own channel;
- ``output`` and its deck columns encode LED feedback the same way;
- status ``Fx`` rows are rekordbox's internal parameters, not MIDI.

Each decoded address becomes a `Control` with a ``click`` (input) and/or
``output`` `UserIO` whose `MappingElement.tag` is the command and `deck_id`
the deck number (1-4) for a per-deck binding. Writing is refused: how
rekordbox saves a user's edits next to these defaults isn't known yet.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, replace

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software._registry import SoftwareDefinition, register

_LOGGER = logging.getLogger(__name__)

SIGNATURE = "@file,"
_EVENT_TYPES = {0x9: "Note On", 0xB: "Control Change", 0xE: "Pitch Bend"}
_INPUT_COLUMN, _OUTPUT_COLUMN = 3, 8
_OPTION_COLUMN, _COMMENT_COLUMN = 13, 14


class RekordboxMappingError(ValueError):
    """The text isn't a rekordbox mapping CSV this plugin can read."""


def is_rekordbox_text(text: str) -> bool:
    return text.lstrip("﻿").startswith(SIGNATURE)


def _address(value: str) -> tuple[int, int | None] | None:
    """``"9058"`` -> (0x90, 0x58), ``"E0"`` -> (0xE0, None); None if not hex."""
    if len(value) not in (2, 4):
        return None
    try:
        number = int(value, 16)
    except ValueError:
        return None
    return (number >> 8, number & 0xFF) if len(value) == 4 else (number, None)


def _addresses(row: list[str], start: int) -> list[tuple[int | None, int, int | None]]:
    """(deck, status, data1) for the address block starting at `start`."""
    base = _address(row[start]) if row[start] else None
    decks = row[start + 1 : start + 5]
    if not any(decks):
        return [] if base is None else [(None, *base)]
    found = []
    for deck, value in enumerate(decks, start=1):
        if not value:
            continue
        if value.isdigit() and len(value) <= 2:
            if base is None:
                continue
            status, data1 = base
            channel = (status & 0x0F) + int(value)
            if channel <= 0x0F:
                found.append((deck, (status & 0xF0) | channel, data1))
        elif (full := _address(value)) is not None:
            found.append((deck, *full))
    return found


def parse_string(text: str) -> MidiConfig:
    if not is_rekordbox_text(text):
        raise RekordboxMappingError("not a rekordbox mapping CSV (no '@file,' first line)")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header = rows[0]
    device = header[2] if len(header) > 2 else ""
    controls: dict[tuple[str, str, str], Control] = {}
    section = ""
    for line_number, row in enumerate(rows[1:], start=2):
        if row and row[0].startswith("#") and not any(row[1:]):
            section = row[0].lstrip("#").strip()  # "# Deck,,,," titles the rows below
            continue
        if not row or not row[0] or row[0].startswith("#"):
            continue
        row = row + [""] * (15 - len(row))
        command, control_name, kind = row[0], row[1], row[2]
        attrs = {"software": "rekordbox", "control_name": control_name, "type": kind, "row": str(line_number)}
        if section:
            attrs["section"] = section
        if row[_OPTION_COLUMN]:
            attrs["option"] = row[_OPTION_COLUMN]
        if row[_COMMENT_COLUMN]:
            attrs["comment"] = row[_COMMENT_COLUMN]
        for event, start in (("click", _INPUT_COLUMN), ("output", _OUTPUT_COLUMN)):
            for deck, status, data1 in _addresses(row, start):
                event_type = _EVENT_TYPES.get(status >> 4)
                if event_type is None:
                    continue  # Fx = rekordbox's own parameters, not a MIDI message
                channel = str((status & 0x0F) + 1)
                number = "0" if data1 is None else str(data1)
                control = controls.setdefault(
                    (channel, event_type, number), Control(channel=channel, event_type=event_type, control=number)
                )
                userio = next((item for item in control.userios if item.event == event), None)
                if userio is None:
                    userio = UserIO(event=event)
                    control.userios.append(userio)
                userio.mappings.append(
                    MappingElement(tag=command, deck_id=None if deck is None else str(deck), extra_attrs=dict(attrs))
                )
    _LOGGER.info("rekordbox mapping %r: %d control(s) from %d row(s)", device, len(controls), len(rows) - 1)
    return MidiConfig(
        app_version=header[1] if len(header) > 1 else None,
        controls=list(controls.values()),
        extra_attrs={"software": "rekordbox", "format": "csv", "device": device},
    )


# Control types that are one press, the catalog's scope (continuous
# controls -- knobs, faders, jogs, encoders -- are left out of profiles).
DISCRETE_TYPES = frozenset({"Button", "Pad"})
_KINDS = {"Note On": "NOTE", "Control Change": "CC"}


@dataclass(frozen=True)
class ProfileRow:
    """One input trigger of a rekordbox mapping, named for a controller
    profile: `section` is the file's `# Title` group, `name` its control."""

    channel: str
    kind: str  # "NOTE" or "CC"
    data1: str
    section: str
    name: str


DEFAULT_SECTION = "Other"
_PAD_NAME = re.compile(r"^PAD(\d+)[._](.+)$", re.IGNORECASE)
_SHIFT_SUFFIX = re.compile(r"\+Shift$", re.IGNORECASE)


def profile_name(section: str, control_name: str) -> tuple[str, str]:
    """(section, name) for a rekordbox control in this app's catalog
    convention: a ``+Shift`` suffix becomes `` +SHIFT``, and a pad
    (``PAD3_PadMode2``, ``PAD3.HotCue``) becomes ``Pad 3 (PadMode2)`` in the
    ``PAD`` section, so the views group a pad's modes, and a button's SHIFT
    layer, onto one control."""
    name, shifted = control_name.strip(), False
    if _SHIFT_SUFFIX.search(name):
        name, shifted = _SHIFT_SUFFIX.sub("", name).strip(), True
    if (pad := _PAD_NAME.match(name)) is not None:
        section, name = "PAD", f"Pad {int(pad.group(1))} ({pad.group(2)})"
    # A row above the file's first "# Title" has no group; a profile entry needs one.
    return section.strip() or DEFAULT_SECTION, f"{name} +SHIFT" if shifted else name


def profile_rows(config: MidiConfig) -> list[ProfileRow]:
    """The discrete input controls of a parsed rekordbox mapping, in file
    order, named by rekordbox's own control column through
    :func:`profile_name` (``Sync+Shift`` -> ``Sync +SHIFT``).

    That column isn't unique per address, so two suffixes keep every row's
    name distinct: a control with several notes on one deck (a pad-mode
    page button: one note per mode) gets its command in brackets, and one
    with its own note per deck (``Load``: notes 70-73 on one channel) gets
    `` (Deck N)``, since a profile row can only fold decks that differ by
    channel."""
    found: list[tuple[ProfileRow, str | None, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for control in config.controls:
        kind = _KINDS.get(control.event_type)
        if kind is None or (control.channel, kind, control.control) in seen:
            continue
        mapping = next(
            (
                m
                for u in control.userios
                if u.event == "click"
                for m in u.mappings
                if m.extra_attrs.get("type") in DISCRETE_TYPES and m.extra_attrs.get("control_name")
            ),
            None,
        )
        if mapping is None:
            continue
        seen.add((control.channel, kind, control.control))
        section, name = profile_name(mapping.extra_attrs.get("section", ""), mapping.extra_attrs["control_name"])
        row = ProfileRow(control.channel, kind, control.control, section, name)
        found.append((row, mapping.deck_id, mapping.tag))

    def numbers_by(key) -> dict:
        grouped: dict = {}
        for row, deck, command in found:
            grouped.setdefault(key(row, deck, command), set()).add((row.kind, row.data1))
        return grouped

    per_deck = numbers_by(lambda row, deck, _command: (row.section, row.name, deck))
    found = [
        (
            replace(row, name=f"{row.name} [{command}]") if len(per_deck[(row.section, row.name, deck)]) > 1 else row,
            deck,
            command,
        )
        for row, deck, command in found
    ]
    per_name = numbers_by(lambda row, _deck, _command: (row.section, row.name))
    named = [
        replace(row, name=f"{row.name} (Deck {deck})")
        if deck is not None and len(per_name[(row.section, row.name)]) > 1
        else row
        for row, deck, _command in found
    ]
    # Last resort (same control and command on several notes): number the
    # addresses in file order, the first one keeping the plain name.
    order: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for row in named:
        numbers = order.setdefault((row.section, row.name), [])
        if (row.kind, row.data1) not in numbers:
            numbers.append((row.kind, row.data1))
    unique = []
    for row in named:
        index = order[(row.section, row.name)].index((row.kind, row.data1))
        unique.append(replace(row, name=f"{row.name} #{index + 1}") if index else row)
    return unique


def to_csv_string(config: MidiConfig) -> str:
    raise RekordboxMappingError(
        "Saving a rekordbox mapping isn't supported yet: edit it in rekordbox's MIDI settings."
    )


register(
    SoftwareDefinition(
        plugin_id="rekordbox",
        name="Pioneer rekordbox",
        extensions=(".csv",),
        parser=parse_string,
        exporter=to_csv_string,
        display_order=30,
        capabilities=("mapping.parse", "mapping.validate"),
        permissions=("mapping.read",),
        signature=is_rekordbox_text,
    )
)


__all__ = [
    "DEFAULT_SECTION",
    "DISCRETE_TYPES",
    "ProfileRow",
    "RekordboxMappingError",
    "is_rekordbox_text",
    "parse_string",
    "profile_name",
    "profile_rows",
    "to_csv_string",
]
