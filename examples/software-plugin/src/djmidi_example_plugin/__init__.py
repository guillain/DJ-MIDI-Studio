"""An example DJ MIDI Studio software plugin, for a made-up format.

The ".djmap" format below isn't any real DJ program's: it exists only to
show, in a few lines, everything a software plugin does. A real plugin
(VirtualDJ, Engine DJ…) follows the same steps with its program's file
format -- read from real files, never guessed.

One binding per line, ``#`` starts a comment::

    # channel;message;number;event;function;deck
    1;Note On;11;click;play;1
    1;Note On;11;output;play_led;1

- ``channel`` 1-16, ``message`` Note On / Note Off / Control Change,
  ``number`` 0-127 (the note or CC), ``event`` click (input) or output
  (LED feedback), ``function`` the program's name for it, ``deck`` 1-4 or
  empty for a global function.
"""

from __future__ import annotations

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software import SoftwareDefinition, register

FIELDS = ("channel", "message", "number", "event", "function", "deck")
HEADER = "# " + ";".join(FIELDS)


class DjmapError(ValueError):
    """Not a readable .djmap file (a ValueError, so the app shows it)."""


def parse_string(text: str) -> MidiConfig:
    """.djmap text → the app's model: one `Control` per MIDI address, one
    `UserIO` per event on it, one `MappingElement` per function."""
    controls: dict[tuple[str, str, str], Control] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) != len(FIELDS):
            raise DjmapError(f"line {number}: expected {len(FIELDS)} fields, got {len(parts)}")
        channel, message, data1, event, function, deck = parts
        control = controls.setdefault((channel, message, data1), Control(channel, message, data1))
        userio = next((item for item in control.userios if item.event == event), None)
        if userio is None:
            userio = UserIO(event=event)
            control.userios.append(userio)
        userio.mappings.append(MappingElement(tag=function, deck_id=deck or None))
    return MidiConfig(controls=list(controls.values()), extra_attrs={"software": "djmap"})


def to_text(config: MidiConfig) -> str:
    """The model → .djmap text. Rebuilt from the model, so comments other
    than the header aren't kept (the contract check reports that as info;
    a real plugin should keep them when it can)."""
    lines = [HEADER]
    for control in config.controls:
        for userio in control.userios:
            for mapping in userio.mappings:
                fields = (control.channel, control.event_type, control.control, userio.event)
                lines.append(";".join((*fields, mapping.tag, mapping.deck_id or "")))
    return "\n".join(lines) + "\n"


def is_djmap(text: str) -> bool:
    """Recognizes the format from its content, whatever the file is called."""
    return text.lstrip().startswith(HEADER)


register(
    SoftwareDefinition(
        plugin_id="example.djmap",
        name="Example .djmap",
        extensions=(".djmap",),
        parser=parse_string,
        exporter=to_text,
        display_order=900,
        capabilities=("mapping.parse", "mapping.export", "mapping.validate"),
        permissions=("mapping.read", "mapping.write"),
        signature=is_djmap,
    )
)
