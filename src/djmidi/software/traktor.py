"""Native Instruments Traktor mapping plugin.

Real Traktor controller mappings are `.tsi` files: settings XML wrapping a
Base64 chunk blob, decoded by `software/_tsi.py` and verified against the
maintainer's real exports (issue #122). Each MIDI-bound Traktor mapping
becomes one `Control` (its channel/note-or-CC), whose single `UserIO` is
``click`` for an input command or ``output`` for LED feedback. Exporting a
config that came from a `.tsi` rewrites only the bindings whose MIDI trigger
was edited and carries every other byte over verbatim; adding or removing
bindings, or rewriting a compound (two-message) binding, is refused rather
than approximated.

The flat ``<NML><MAPPINGS><MAPPING>`` shape handled further down predates
that research and is **not** a format Traktor itself reads or writes
(`.nml` is Traktor's track collection, see `library/traktor_library.py`).
It is kept only so files previously produced by this app still open.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software import _tsi
from djmidi.software._registry import SoftwareDefinition, register

_EVENT_TYPES = {"Note": "Note On", "CC": "Control Change", "PitchBend": "Pitch Bend"}
_KINDS = {event_type: kind for kind, event_type in _EVENT_TYPES.items()}
# The parsed .tsi a config came from, kept on the config object itself so
# export can re-emit every byte it doesn't model.
_TSI_DOCUMENT_ATTR = "_tsi_document"


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
    if _tsi.is_tsi_text(xml_text):
        return _parse_tsi(xml_text)
    return _parse_legacy_nml(xml_text)


def to_xml_string(config: MidiConfig) -> str:
    document = getattr(config, _TSI_DOCUMENT_ATTR, None)
    if document is not None:
        return _export_tsi(config, document)
    return _export_legacy_nml(config)


def _tsi_control(mapping: _tsi.TsiMapping, device: _tsi.TsiDevice) -> Control | None:
    trigger = mapping.trigger
    if trigger is None:
        return None  # a command never MIDI-learned: kept in the file, not shown
    attrs = {
        "software": "traktor",
        "command_id": str(mapping.command_id),
        "controller_type": _tsi.CONTROLLER_TYPES.get(mapping.controller_type, str(mapping.controller_type)),
        "interaction_mode": _tsi.INTERACTION_MODES.get(mapping.interaction_mode, str(mapping.interaction_mode)),
        "device": device.comment or device.name,
    }
    if mapping.comment:
        attrs["comment"] = mapping.comment
    return Control(
        channel=str(trigger.channel),
        event_type=_EVENT_TYPES[trigger.kind],
        control=str(trigger.number if trigger.number is not None else 0),
        userios=[
            UserIO(
                event="output" if mapping.direction == "out" else "click",
                mappings=[
                    MappingElement(
                        tag=mapping.command_name,
                        deck_id=str(mapping.target_deck + 1) if mapping.target_deck >= 0 else None,
                        extra_attrs=attrs,
                    )
                ],
            )
        ],
        extra_attrs={
            "tsi_device": str(mapping.device_index),
            "tsi_binding": str(mapping.binding_id),
            "tsi_label": mapping.label,
        },
    )


def _parse_tsi(text: str) -> MidiConfig:
    document = _tsi.parse_tsi(text)
    controls = [
        control
        for device in document.devices
        for mapping in device.mappings
        if (control := _tsi_control(mapping, device)) is not None
    ]
    config = MidiConfig(
        app_version=document.devices[0].version.split("|", 1)[0] if document.devices else None,
        controls=controls,
        extra_attrs={"software": "traktor", "format": "tsi"},
    )
    setattr(config, _TSI_DOCUMENT_ATTR, document)
    return config


def _control_label(control: Control, original: str) -> str:
    kind = _KINDS.get(control.event_type)
    if kind is None:
        raise _tsi.TsiError(f"a .tsi binding can't use event type {control.event_type!r}")
    try:
        channel, number = int(control.channel), int(control.control)
    except ValueError as exc:
        raise _tsi.TsiError(f"invalid MIDI channel/number {control.channel!r}/{control.control!r}") from exc
    trigger = _tsi.MidiTrigger(channel, kind, None if kind == "PitchBend" else number)
    if _tsi.is_compound_label(original):
        if trigger != _tsi.parse_label(original):
            raise _tsi.TsiError(f"can't re-assign the two-message binding {original!r} to a single trigger")
        return original
    return _tsi.format_label(trigger)


def _export_tsi(config: MidiConfig, document: _tsi.TsiDocument) -> str:
    expected = {(m.device_index, m.binding_id): m.label for m in document.mappings if m.label}
    relabel: dict[tuple[int, int], str] = {}
    seen: set[tuple[int, int]] = set()
    for control in config.controls:
        if "tsi_binding" not in control.extra_attrs:
            raise _tsi.TsiError("adding a new binding to a .tsi isn't supported -- map it in Traktor itself")
        key = (int(control.extra_attrs["tsi_device"]), int(control.extra_attrs["tsi_binding"]))
        original = expected.get(key)
        if original is None:
            raise _tsi.TsiError(f"device #{key[0]} has no binding {key[1]} in the source .tsi")
        seen.add(key)
        label = _control_label(control, original)
        if label != original:
            relabel[key] = label
    missing = set(expected) - seen
    if missing:
        raise _tsi.TsiError(f"removing bindings from a .tsi isn't supported ({len(missing)} missing)")
    return document.to_text(relabel)


def _parse_legacy_nml(xml_text: str) -> MidiConfig:
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


def _export_legacy_nml(config: MidiConfig) -> str:
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
        extensions=(".tsi", ".nml", ".xml"),
        parser=parse_string,
        exporter=to_xml_string,
        display_order=20,
        capabilities=("mapping.parse", "mapping.export", "mapping.validate"),
        permissions=("mapping.read", "mapping.write"),
        change_summary=_tsi.describe_changes,
    )
)


__all__ = ["parse_string", "to_xml_string"]
