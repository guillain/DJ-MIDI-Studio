"""Native Instruments Traktor mapping plugin.

Traktor mapping exports are NML XML files.  NML variants differ slightly
between Traktor versions, so the importer intentionally accepts the common
MIDI NOTE/CC attribute spellings and ignores unsupported continuous metadata.
The exporter writes a compact, portable NML mapping containing the controls
represented by DJ MIDI Studio's model.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software._registry import SoftwareDefinition, register


def _attribute(element: ET.Element, *names: str) -> str | None:
    for name in names:
        value = element.attrib.get(name)
        if value is not None and value != "":
            return value
    return None


def _channel(value: str | None) -> str:
    if value is None:
        return "1"
    try:
        number = int(value)
    except ValueError:
        return value
    # Traktor NML commonly stores MIDI channels zero-based.
    return str(number + 1) if 0 <= number <= 15 else str(number)


def _mapping_label(mapping: ET.Element, midi: ET.Element) -> str:
    raw = _attribute(mapping, "NAME", "ACTION", "TARGET", "ID") or _attribute(midi, "NAME", "ACTION") or "TRAKTOR_MAPPING"
    return re.sub(r"[^A-Za-z0-9_./ -]+", "", raw).strip() or "TRAKTOR_MAPPING"


def _midi_trigger(mapping: ET.Element) -> tuple[str, str, str] | None:
    current_channel = _channel(_attribute(mapping, "CHAN", "CHANNEL"))
    for midi in mapping.iter():
        channel = _attribute(midi, "CHAN", "CHANNEL")
        if channel is not None:
            current_channel = _channel(channel)
        note = _attribute(midi, "NOTE", "NOTE_NR", "NOTE_NUMBER")
        if note is not None:
            return current_channel, "Note On", note
        cc = _attribute(midi, "CC", "CC_NR", "CONTROLLER")
        if cc is not None:
            return current_channel, "Control Change", cc
    return None


def parse_string(xml_text: str) -> MidiConfig:
    root = ET.fromstring(xml_text)
    mappings = root.findall(".//MAPPING")
    controls: list[Control] = []
    for index, mapping in enumerate(mappings, start=1):
        trigger = _midi_trigger(mapping)
        if trigger is None:
            continue
        channel, event_type, data1 = trigger
        label = _mapping_label(mapping, next(iter(mapping.iter())))
        deck_id = _attribute(mapping, "DECK", "DECK_ID")
        controls.append(
            Control(
                channel=channel,
                event_type=event_type,
                control=data1,
                userios=[
                    UserIO(
                        event="click",
                        mappings=[
                            MappingElement(
                                tag=label,
                                deck_id=deck_id,
                                slot_id=str(index),
                                extra_attrs={"software": "traktor"},
                            )
                        ],
                    )
                ],
            )
        )
    return MidiConfig(app_version=root.attrib.get("VERSION"), controls=controls, extra_attrs={"software": "traktor"})


def to_xml_string(config: MidiConfig) -> str:
    root = ET.Element("NML", {"VERSION": config.app_version or "1.0"})
    ET.SubElement(root, "HEAD", {"COMPANY": "Native Instruments", "NAME": "Traktor"})
    mappings = ET.SubElement(root, "MAPPINGS")
    for index, control in enumerate(config.controls, start=1):
        mapping_element = control.userios[0].mappings[0] if control.userios and control.userios[0].mappings else None
        label = mapping_element.tag if mapping_element is not None else f"MAPPING_{index}"
        mapping = ET.SubElement(mappings, "MAPPING", {"NAME": label})
        midi = ET.SubElement(mapping, "MIDI", {"CHAN": str(max(int(control.channel) - 1, 0))})
        if "control" in control.event_type.lower():
            ET.SubElement(midi, "CC", {"CC": control.control})
        else:
            ET.SubElement(midi, "NOTE", {"NOTE": control.control})
    ET.indent(root, space="    ")
    return ET.tostring(root, encoding="unicode") + "\n"


register(
    SoftwareDefinition(
        plugin_id="traktor",
        name="Native Instruments Traktor",
        extensions=(".nml", ".tsi", ".xml"),
        parser=parse_string,
        exporter=to_xml_string,
        display_order=20,
    )
)


__all__ = ["parse_string", "to_xml_string"]
