from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from os import PathLike

from djmidi.model import (
    Alias,
    Control,
    MappingElement,
    MidiConfig,
    Translation,
    UserIO,
)

_LOGGER = logging.getLogger(__name__)


def _build_attrib(known: list[tuple[str, str | None]], extra: dict[str, str]) -> dict[str, str]:
    attrib = {key: value for key, value in known if value is not None}
    attrib.update(extra)
    return attrib


def _build_alias(alias: Alias) -> ET.Element:
    element = ET.Element("alias", _build_attrib([("name", alias.name), ("value", alias.value)], alias.extra_attrs))
    return element


def _build_translation(translation: Translation) -> ET.Element:
    element = ET.Element(
        "translation",
        _build_attrib(
            [("action_on", translation.action_on), ("behaviour", translation.behaviour)],
            translation.extra_attrs,
        ),
    )
    for alias in translation.aliases:
        element.append(_build_alias(alias))
    return element


def _build_mapping(mapping: MappingElement) -> ET.Element:
    element = ET.Element(
        mapping.tag,
        _build_attrib(
            [("deck_set", mapping.deck_set), ("deck_id", mapping.deck_id), ("slot_id", mapping.slot_id)],
            mapping.extra_attrs,
        ),
    )
    for translation in mapping.translations:
        element.append(_build_translation(translation))
    return element


def _build_userio(userio: UserIO) -> ET.Element:
    element = ET.Element("userio", _build_attrib([("event", userio.event)], userio.extra_attrs))
    for mapping in userio.mappings:
        element.append(_build_mapping(mapping))
    return element


def _build_control(control: Control) -> ET.Element:
    element = ET.Element(
        "control",
        _build_attrib(
            [("channel", control.channel), ("event_type", control.event_type), ("control", control.control)],
            control.extra_attrs,
        ),
    )
    for userio in control.userios:
        element.append(_build_userio(userio))
    return element


def to_element(config: MidiConfig) -> ET.Element:
    root = ET.Element("midi", _build_attrib([("app", config.app_version)], config.extra_attrs))
    for control in config.controls:
        root.append(_build_control(control))
    return root


def to_xml_string(config: MidiConfig) -> str:
    root = to_element(config)
    ET.indent(root, space="    ")
    xml_text = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    # ElementTree renders empty elements as "<tag />"; Serato's own exports use "<tag/>".
    xml_text = xml_text.replace(" />", "/>")
    return xml_text + "\n"


def write_file(config: MidiConfig, path: str | PathLike[str]) -> None:
    _LOGGER.info("Exporting Serato MIDI config to %s (%d <control> element(s))", path, len(config.controls))
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_xml_string(config))
    _LOGGER.debug("Export to %s complete", path)
