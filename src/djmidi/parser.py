from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from os import PathLike

from djmidi.model import (
    Alias,
    Case,
    Condition,
    Control,
    MappingElement,
    MidiConfig,
    Translation,
    UserIO,
)

_LOGGER = logging.getLogger(__name__)


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


def _parse_case(element: ET.Element, where: str) -> Case:
    conditions: list[Condition] = []
    condition_attrs: dict[str, str] = {}
    userios: list[UserIO] = []
    has_condition = False
    for child in element:
        if child.tag == "condition":
            has_condition = True
            condition_attrs.update(child.attrib)
            for test in child:
                if len(test):
                    _LOGGER.warning("Nested content under <%s> in a <condition> at %s is not kept", test.tag, where)
                conditions.append(Condition(tag=test.tag, attrs=dict(test.attrib)))
        elif child.tag == "userio":
            userios.append(_parse_userio(child))
        else:
            _LOGGER.warning("Unexpected <%s> inside a <case> at %s is not kept", child.tag, where)
    return Case(
        conditions=conditions,
        userios=userios,
        extra_attrs=dict(element.attrib),
        condition_attrs=condition_attrs,
        has_condition=has_condition,
    )


def _parse_control(element: ET.Element) -> Control:
    values, extra = _pop_known(element.attrib, ("channel", "event_type", "control"))
    where = f"control channel={values['channel']} control={values['control']}"
    userios: list[UserIO] = []
    cases: list[Case] = []
    for child in element:
        if child.tag == "userio":
            userios.append(_parse_userio(child))
        elif child.tag == "case":
            case = _parse_case(child, where)
            case.position = len(userios)
            cases.append(case)
        else:
            _LOGGER.warning("Unexpected <%s> inside a <control> at %s is not kept", child.tag, where)
    return Control(
        channel=values["channel"],
        event_type=values["event_type"],
        control=values["control"],
        userios=userios,
        extra_attrs=extra,
        cases=cases,
    )


def parse_string(xml_text: str) -> MidiConfig:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        _LOGGER.exception("Failed to parse Serato MIDI config XML (%d bytes)", len(xml_text))
        raise
    if root.tag != "midi":
        _LOGGER.error("Rejecting XML: expected root element <midi>, got <%s>", root.tag)
        raise ValueError(f"Expected root element <midi>, got <{root.tag}>")
    values, extra = _pop_known(root.attrib, ("app",))
    controls = [_parse_control(child) for child in root if child.tag == "control"]
    _LOGGER.info("Parsed Serato MIDI config: app=%s, %d <control> element(s)", values["app"], len(controls))
    return MidiConfig(app_version=values["app"], controls=controls, extra_attrs=extra)


def parse_file(path: str | PathLike[str]) -> MidiConfig:
    _LOGGER.info("Loading Serato MIDI config from %s", path)
    with open(path, encoding="utf-8") as f:
        return parse_string(f.read())
