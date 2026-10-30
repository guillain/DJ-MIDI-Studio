"""Mixxx MIDI mapping plugin (read-only, issue #365).

Mixxx is the one major DJ program whose controller mapping format is
publicly documented, and its repository ships ~140 real mappings
(``res/controllers/*.midi.xml``); the shape below was checked against all
of them (2.5 branch, read only -- nothing copied here, tests use a
synthetic file). See ``software/mixxx/README.md``.

- Root ``<MixxxControllerPreset>`` (current) or ``<MixxxMIDIPreset>``
  (older files), with ``<info><name>`` and one ``<controller>``.
- ``<controls><control>``: an input binding -- ``<group>`` (``[Channel1]``
  = deck 1, ``[Master]``, ``[Sampler2]``…), ``<key>`` (a Mixxx control, or
  a script function under ``<options><script-binding/>``), ``<status>``
  (hex status byte: message type + channel) and ``<midino>`` (hex data1),
  optional ``<description>``.
- ``<outputs><output>``: LED feedback, same addressing plus on/off values.

Each address becomes a `Control` with a ``click`` (input) and/or ``output``
`UserIO`; `MappingElement.tag` is the key, `deck_id` the deck number of a
``[ChannelN]`` group, and group/description/options go in `extra_attrs`.
Program Change and System messages (a handful of files) aren't MIDI
triggers this app models and are skipped.

Saving (``v0.48.159``) rewrites only what changed, like the Traktor ``.tsi``
writer: the text of the ``<status>`` / ``<midino>`` of each binding whose
MIDI address was edited, patched in place at byte offsets found with expat,
so comments, indentation and every other byte stay as they were (an
unedited export is byte-identical). Adding or removing bindings, giving a
binding with no ``<midino>`` a number, or using a message type Mixxx
bindings here never carry is refused rather than approximated.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.parsers import expat

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software._registry import SoftwareDefinition, register

_LOGGER = logging.getLogger(__name__)

ROOT_TAGS = ("MixxxControllerPreset", "MixxxMIDIPreset")
_SIGNATURE = re.compile(r"<\s*Mixxx(?:Controller|MIDI)Preset\b")
_EVENT_TYPES = {0x8: "Note Off", 0x9: "Note On", 0xB: "Control Change", 0xE: "Pitch Bend"}
_DECK_GROUP = re.compile(r"^\[Channel(\d+)\]$")
_NIBBLES = {event_type: nibble for nibble, event_type in _EVENT_TYPES.items()}
_PATHS = (("click", "control", ("controller", "controls", "control")), ("output", "output", ("controller", "outputs", "output")))
# Which source element a mapping element came from, e.g. "control:12".
ELEMENT_ATTR = "mixxx_element"
# The source text and the elements read from it, kept on the config object
# (not in extra_attrs, which is str -> str) so export can patch the text.
_SOURCE_ATTR = "_mixxx_source"


class MixxxMappingError(ValueError):
    """The text isn't a Mixxx MIDI mapping this plugin can read."""


def is_mixxx_text(text: str) -> bool:
    return _SIGNATURE.search(text[:4096]) is not None


def _number(text: str | None) -> int | None:
    value = (text or "").strip()
    if not value:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def _address(element: ET.Element) -> tuple[str, str, str] | None:
    status = _number(element.findtext("status"))
    if status is None:
        return None
    event_type = _EVENT_TYPES.get(status >> 4)
    if event_type is None:
        return None
    data1 = _number(element.findtext("midino"))
    if data1 is None:
        if event_type != "Pitch Bend":
            return None
        data1 = 0
    return str((status & 0x0F) + 1), event_type, str(data1)


def _attrs(element: ET.Element, kind: str) -> dict[str, str]:
    attrs = {"software": "mixxx", "kind": kind}
    group = (element.findtext("group") or "").strip()
    if group:
        attrs["group"] = group
    description = (element.findtext("description") or "").strip()
    if description:
        attrs["description"] = description
    options = element.find("options")
    if options is not None and len(options):
        attrs["options"] = ",".join(option.tag.lower() for option in options)
    for name in ("on", "off", "minimum", "maximum"):
        value = (element.findtext(name) or "").strip()
        if value:
            attrs[name] = value
    return attrs


def parse_string(text: str) -> MidiConfig:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise MixxxMappingError(f"not a readable Mixxx mapping: {exc}") from exc
    if root.tag not in ROOT_TAGS:
        raise MixxxMappingError(f"not a Mixxx mapping (root <{root.tag}>)")
    controls: dict[tuple[str, str, str], Control] = {}
    skipped = 0
    read: dict[str, tuple[int, int | None, str, str | None]] = {}
    for event, tag, path in _PATHS:
        for index, element in enumerate(root.findall("/".join(path))):
            address = _address(element)
            key = (element.findtext("key") or "").strip()
            if address is None or not key:
                skipped += 1
                continue
            control = controls.setdefault(address, Control(*address))
            userio = next((item for item in control.userios if item.event == event), None)
            if userio is None:
                userio = UserIO(event=event)
                control.userios.append(userio)
            attrs = _attrs(element, "input" if event == "click" else "output")
            attrs[ELEMENT_ATTR] = f"{tag}:{index}"
            deck = _DECK_GROUP.match(attrs.get("group", ""))
            deck_id = deck.group(1) if deck else None
            # As read, so export patches only what really changed.
            read[attrs[ELEMENT_ATTR]] = (_number(element.findtext("status")), _number(element.findtext("midino")), key, deck_id)
            userio.mappings.append(MappingElement(tag=key, deck_id=deck_id, extra_attrs=attrs))
    name = (root.findtext("info/name") or "").strip()
    _LOGGER.info("Mixxx mapping %r: %d control(s), %d binding(s) skipped", name, len(controls), skipped)
    config = MidiConfig(
        app_version=root.attrib.get("mixxxVersion"),
        controls=list(controls.values()),
        extra_attrs={"software": "mixxx", "format": root.tag, "device": name},
    )
    setattr(config, _SOURCE_ATTR, (text, read))
    return config


# --- writing back -------------------------------------------------------------


@dataclass
class _Span:
    """Where one binding's <status> / <midino> text sits in the source bytes."""

    status: tuple[int, int] | None = None
    midino: tuple[int, int] | None = None


def _spans(data: bytes, root_tag: str) -> dict[str, _Span]:
    """Byte spans of every control/output's <status> and <midino> text,
    keyed like ELEMENT_ATTR, found with expat (document order = the order
    ElementTree's findall reads them in)."""
    parser = expat.ParserCreate()
    stack: list[str] = []
    counters = {"control": 0, "output": 0}
    spans: dict[str, _Span] = {}
    current: list[str | None] = [None]
    field: list = [None, None]  # [name, text start]

    def start(name, _attrs):
        stack.append(name)
        for _event, tag, path in _PATHS:
            if tuple(stack[1:]) == path and stack[0] == root_tag:
                current[0] = f"{tag}:{counters[tag]}"
                counters[tag] += 1
                spans[current[0]] = _Span()
        if current[0] is not None and name in ("status", "midino") and len(stack) == 5:
            field[0], field[1] = name, None

    def text(_data):
        if field[0] is not None and field[1] is None:
            field[1] = parser.CurrentByteIndex

    def end(name):
        if current[0] is not None and field[0] == name and field[1] is not None:
            setattr(spans[current[0]], name, (field[1], parser.CurrentByteIndex))
        if name == field[0]:
            field[0] = field[1] = None
        if name in ("control", "output") and len(stack) == 4:
            current[0] = None
        stack.pop()

    parser.StartElementHandler, parser.CharacterDataHandler, parser.EndElementHandler = start, text, end
    parser.Parse(data, True)
    return spans


def _patched(data: bytes, span: tuple[int, int], value: str) -> tuple[int, int, bytes]:
    """The replacement for a field's text, keeping its surrounding whitespace."""
    original = data[span[0] : span[1]].decode("utf-8")
    stripped = original.strip()
    lead = original[: len(original) - len(original.lstrip())]
    trail = original[len(original.rstrip()) :]
    if stripped.lower().startswith("0x"):
        # Same prefix, width and letter case as the file already uses.
        case = "x" if any(char.islower() for char in stripped[2:]) else "X"
        formatted = f"{stripped[:2]}{int(value):0{len(stripped) - 2}{case}}"
    else:
        formatted = value
    return span[0], span[1], (lead + formatted + trail).encode("utf-8")


def _patch(data: bytes, span: tuple[int, int] | None, value: int, element: str) -> tuple[int, int, bytes]:
    if span is None:
        raise MixxxMappingError(f"binding {element} has no field to write that number into")
    if _number(data[span[0] : span[1]].decode("utf-8")) is None:
        # e.g. an XML entity (&CC;) that only the file's DTD resolves
        raise MixxxMappingError(f"binding {element} doesn't spell its value as a number; change it in Mixxx")
    return _patched(data, span, str(value))


def to_xml_string(config: MidiConfig) -> str:
    source = getattr(config, _SOURCE_ATTR, None)
    if source is None:
        raise MixxxMappingError("only a mapping opened from a Mixxx file can be saved as one")
    text, read = source
    data = text.encode("utf-8")
    spans = _spans(data, ET.fromstring(text).tag)
    seen: set[str] = set()
    edits: set[tuple[int, int, bytes]] = set()
    for control in config.controls:
        nibble = _NIBBLES.get(control.event_type)
        for userio in control.userios:
            for mapping in userio.mappings:
                element = mapping.extra_attrs.get(ELEMENT_ATTR)
                if element not in read:
                    raise MixxxMappingError("adding a binding to a Mixxx mapping isn't supported -- map it in Mixxx")
                seen.add(element)
                old_status, old_number, old_key, old_deck = read[element]
                if (mapping.tag, mapping.deck_id) != (old_key, old_deck):
                    raise MixxxMappingError(
                        f"only a binding's MIDI message can be changed here, not its Mixxx key or deck ({element})"
                    )
                old_shown = 0 if old_number is None else old_number
                as_read = (str((old_status & 0x0F) + 1), _EVENT_TYPES[old_status >> 4], str(old_shown))
                if (control.channel, control.event_type, control.control) == as_read:
                    continue  # untouched: even an odd value in the file stays as is
                address = _address_values(control)
                if address is None or nibble is None:
                    raise MixxxMappingError(
                        f"a Mixxx binding can't be {control.event_type!r} {control.channel!r}/{control.control!r}"
                    )
                channel, number = address
                status = (nibble << 4) | (channel - 1)
                if (old_status >> 4, (old_status & 0x0F) + 1) != (nibble, channel):
                    edits.add(_patch(data, spans[element].status, status, element))
                if number != old_shown:
                    edits.add(_patch(data, spans[element].midino, number, element))
    missing = set(read) - seen
    if missing:
        raise MixxxMappingError(f"removing bindings from a Mixxx mapping isn't supported ({len(missing)} missing)")
    for start, end, replacement in sorted(edits, reverse=True):
        data = data[:start] + replacement + data[end:]
    return data.decode("utf-8")


def _address_values(control: Control) -> tuple[int, int] | None:
    """(channel, number) of an edited control, None when out of range."""
    try:
        channel, number = int(control.channel), int(control.control)
    except ValueError:
        return None
    return (channel, number) if 1 <= channel <= 16 and 0 <= number <= 127 else None



register(
    SoftwareDefinition(
        plugin_id="mixxx",
        name="Mixxx",
        extensions=(".midi.xml",),
        parser=parse_string,
        exporter=to_xml_string,
        display_order=40,
        capabilities=("mapping.parse", "mapping.export", "mapping.validate"),
        permissions=("mapping.read", "mapping.write"),
        signature=is_mixxx_text,
    )
)


__all__ = ["MixxxMappingError", "is_mixxx_text", "parse_string", "to_xml_string"]
