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
triggers this app models and are skipped. Saving is refused: a faithful
write must keep the file's comments and layout, which isn't implemented.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software._registry import SoftwareDefinition, register

_LOGGER = logging.getLogger(__name__)

ROOT_TAGS = ("MixxxControllerPreset", "MixxxMIDIPreset")
_SIGNATURE = re.compile(r"<\s*Mixxx(?:Controller|MIDI)Preset\b")
_EVENT_TYPES = {0x8: "Note Off", 0x9: "Note On", 0xB: "Control Change", 0xE: "Pitch Bend"}
_DECK_GROUP = re.compile(r"^\[Channel(\d+)\]$")


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
    for event, path in (("click", "controller/controls/control"), ("output", "controller/outputs/output")):
        for element in root.findall(path):
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
            deck = _DECK_GROUP.match(attrs.get("group", ""))
            userio.mappings.append(MappingElement(tag=key, deck_id=deck.group(1) if deck else None, extra_attrs=attrs))
    name = (root.findtext("info/name") or "").strip()
    _LOGGER.info("Mixxx mapping %r: %d control(s), %d binding(s) skipped", name, len(controls), skipped)
    return MidiConfig(
        app_version=root.attrib.get("mixxxVersion"),
        controls=list(controls.values()),
        extra_attrs={"software": "mixxx", "format": root.tag, "device": name},
    )


def to_xml_string(config: MidiConfig) -> str:
    raise MixxxMappingError("Saving a Mixxx mapping isn't supported yet: edit it in Mixxx's controller preferences.")


register(
    SoftwareDefinition(
        plugin_id="mixxx",
        name="Mixxx",
        extensions=(".midi.xml",),
        parser=parse_string,
        exporter=to_xml_string,
        display_order=40,
        capabilities=("mapping.parse", "mapping.validate"),
        permissions=("mapping.read",),
        signature=is_mixxx_text,
    )
)


__all__ = ["MixxxMappingError", "is_mixxx_text", "parse_string", "to_xml_string"]
