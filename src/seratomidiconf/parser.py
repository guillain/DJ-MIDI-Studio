from __future__ import annotations

import xml.etree.ElementTree as ET
from os import PathLike

from seratomidiconf.model import (
    Alias,
    Control,
    MappingElement,
    MidiConfig,
    Translation,
    UserIO,
)


def _pop_known(attrib: dict[str, str], known: tuple[str, ...]) -> tuple[dict[str, str | None], dict[str, str]]:
    """Split an element's attributes into known fields and leftover extra_attrs."""
    values = {key: attrib.get(key) for key in known}
    extra = {key: value for key, value in attrib.items() if key not in known}
    return values, extra


def _parse_alias(element: ET.Element) -> Alias:
    values, extra = _pop_known(element.attrib, ("name", "value"))
    return Alias(name=values["name"], value=values["value"], extra_attrs=extra)


def _parse_translation(element: ET.Element) -> Translation:
    values, extra = _pop_known(element.attrib, ("action_on", "behaviour"))
    aliases = [_parse_alias(child) for child in element if child.tag == "alias"]
    return Translation(
        action_on=values["action_on"],
        behaviour=values["behaviour"],
        aliases=aliases,
        extra_attrs=extra,
    )


def _parse_mapping(element: ET.Element) -> MappingElement:
    values, extra = _pop_known(element.attrib, ("deck_set", "deck_id", "slot_id"))
    translations = [_parse_translation(child) for child in element if child.tag == "translation"]
    return MappingElement(
        tag=element.tag,
        deck_set=values["deck_set"],
        deck_id=values["deck_id"],
        slot_id=values["slot_id"],
        translations=translations,
        extra_attrs=extra,
    )


def _parse_userio(element: ET.Element) -> UserIO:
    values, extra = _pop_known(element.attrib, ("event",))
    mappings = [_parse_mapping(child) for child in element]
    return UserIO(event=values["event"], mappings=mappings, extra_attrs=extra)


def _parse_control(element: ET.Element) -> Control:
    values, extra = _pop_known(element.attrib, ("channel", "event_type", "control"))
    userios = [_parse_userio(child) for child in element if child.tag == "userio"]
    return Control(
        channel=values["channel"],
        event_type=values["event_type"],
        control=values["control"],
        userios=userios,
        extra_attrs=extra,
    )


def parse_string(xml_text: str) -> MidiConfig:
    root = ET.fromstring(xml_text)
    if root.tag != "midi":
        raise ValueError(f"Expected root element <midi>, got <{root.tag}>")
    values, extra = _pop_known(root.attrib, ("app",))
    controls = [_parse_control(child) for child in root if child.tag == "control"]
    return MidiConfig(app_version=values["app"], controls=controls, extra_attrs=extra)


def parse_file(path: str | PathLike[str]) -> MidiConfig:
    with open(path, encoding="utf-8") as f:
        return parse_string(f.read())
