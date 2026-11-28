"""rekordbox's own MIDI command list, read from the DJ's installed rekordbox (Qt-free).

rekordbox's MIDI Settings window is built from a table embedded in its
executable: ``<MIDI_COMMAND_DATA>`` blocks (one per tab: DECK, PAD, FX,
SAMPLER, MIXER, BROWSE, OTHER, VIDEO, LIGHTING, MIXPOINTLINK) of
``<COMMAND displayname csvname type category deck/>``. ``csvname`` is what a
``.midi.csv`` mapping writes, ``displayname`` what the DJ sees in rekordbox.

The maintainer chose (2026-11-28) to read that table at runtime, read-only,
on the DJ's own machine: nothing from it is shipped with the app or copied
into the repository. :func:`load` reads it once; :func:`display_name` then
gives a ``.midi.csv`` command its rekordbox label (``function_names`` uses it).
The meaning of ``type`` codes is unknown and not interpreted.
"""

from __future__ import annotations

import logging
import mmap
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_START = b"<MIDI_COMMAND_DATA>"
_END = b"</MIDI_COMMAND_DATA>"
# The tables are a few hundred kilobytes; a block is never larger than this.
_MAX_BLOCK = 1_000_000


@dataclass(frozen=True)
class RekordboxCommand:
    tab: str  # the MIDI Settings tab (DECK, PAD, ...)
    display_name: str
    csv_name: str
    type: str
    category: str
    deck: str  # "1": per deck, "0": global


def candidate_paths() -> list[Path]:
    """Where rekordbox's executable usually is, newest major version first."""
    found: list[Path] = []
    if sys.platform == "darwin":
        for app in sorted(Path("/Applications").glob("rekordbox */rekordbox.app"), reverse=True):
            found.append(app / "Contents" / "MacOS" / "rekordbox")
    elif os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "rekordbox"
        for folder in sorted(root.glob("rekordbox *"), reverse=True):
            found.append(folder / "rekordbox.exe")
    return [path for path in found if path.is_file()]


def _parse_block(block: bytes) -> list[RekordboxCommand]:
    root = ET.fromstring(block.decode("utf-8", errors="replace"))
    commands = []
    for tab in root:
        for element in tab.iter("COMMAND"):
            csv_name = (element.get("csvname") or "").strip()
            if not csv_name:
                continue
            commands.append(
                RekordboxCommand(
                    tab=tab.tag,
                    display_name=(element.get("displayname") or "").strip(),
                    csv_name=csv_name,
                    type=(element.get("type") or "").strip(),
                    category=(element.get("category") or "").strip(),
                    deck=(element.get("deck") or "").strip(),
                )
            )
    return commands


def read_commands(path: str | Path) -> list[RekordboxCommand]:
    """Every command of the first table in ``path`` (an executable holds one
    copy per architecture). Read-only; [] when there is no table."""
    commands: list[RekordboxCommand] = []
    tabs_seen: set[str] = set()
    with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        position = 0
        while True:
            start = data.find(_START, position)
            if start < 0:
                break
            end = data.find(_END, start, start + _MAX_BLOCK)
            if end < 0:
                break
            position = end + len(_END)
            try:
                block = _parse_block(bytes(data[start:position]))
            except ET.ParseError as error:
                _LOGGER.warning("rekordbox command block at %d not readable: %s", start, error)
                continue
            tab = block[0].tab if block else ""
            if tab in tabs_seen:
                break  # the next architecture's copy of the same table
            tabs_seen.add(tab)
            commands.extend(block)
    return commands


_display_names: dict[str, str] = {}
_source: Path | None = None


def load(path: str | Path | None = None) -> int:
    """Reads the table once (the newest installed rekordbox when ``path`` is
    None); returns how many commands are known. Never raises."""
    global _source
    if path is None:
        if _display_names:
            return len(_display_names)
        candidates = candidate_paths()
        if not candidates:
            return 0
        path = candidates[0]
    try:
        commands = read_commands(path)
    except OSError as error:
        _LOGGER.warning("Could not read rekordbox's command table in %s: %s", path, error)
        return 0
    _display_names.clear()
    for command in commands:
        if command.display_name:
            _display_names.setdefault(command.csv_name, command.display_name)
    _source = Path(path)
    _LOGGER.info("Read %d rekordbox commands from %s", len(_display_names), path)
    return len(_display_names)


def display_name(csv_name: str) -> str:
    """rekordbox's label for a ``.midi.csv`` command, "" when unknown or not
    loaded. A ``+Shift`` suffix keeps its meaning: "PlayPause+Shift" is the
    label of ``PlayPause`` on the SHIFT layer unless the table names it."""
    if csv_name in _display_names:
        return _display_names[csv_name]
    base, plus, suffix = csv_name.partition("+")
    if plus and base in _display_names:
        return f"{_display_names[base]} +{suffix}"
    return ""


def loaded_from() -> Path | None:
    return _source


def clear() -> None:
    global _source
    _display_names.clear()
    _source = None


__all__ = ["RekordboxCommand", "candidate_paths", "clear", "display_name", "load", "loaded_from", "read_commands"]
