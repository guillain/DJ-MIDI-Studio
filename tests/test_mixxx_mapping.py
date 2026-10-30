"""Mixxx MIDI mapping (read-only plugin, issue #365). Synthetic file in the
shape Mixxx ships (see software/mixxx/README.md)."""

import pytest

from djmidi import software
from djmidi.integration_detection import detect_software_mapping
from djmidi.software.mixxx import (
    MixxxMappingError,
    is_mixxx_text,
    parse_string,
    to_xml_string,
)

MAPPING = """<?xml version='1.0' encoding='utf-8'?>
<MixxxControllerPreset schemaVersion="1" mixxxVersion="2.3.0+">
  <info><name>Test Controller</name><author>me</author></info>
  <controller id="Test">
    <scriptfiles><file functionprefix="Test" filename="Test.js"/></scriptfiles>
    <controls>
      <!-- deck 1 play -->
      <control>
        <group>[Channel1]</group>
        <key>play</key>
        <description>Play button</description>
        <status>0x90</status>
        <midino>0x0B</midino>
        <options><normal/></options>
      </control>
      <control>
        <group>[Channel2]</group>
        <key>Test.deck[1].play.input</key>
        <status>0x91</status>
        <midino>0x0B</midino>
        <options><script-binding/></options>
      </control>
      <control>
        <group>[Channel1]</group>
        <key>Test.deck[0].play.input</key>
        <status>0x80</status>
        <midino>0x0B</midino>
        <options><script-binding/></options>
      </control>
      <control>
        <group>[Master]</group>
        <key>crossfader</key>
        <status>0xB6</status>
        <midino>0x1F</midino>
        <options><soft-takeover/><invert/></options>
      </control>
      <control>
        <group>[Channel1]</group>
        <key>rate</key>
        <status>0xE0</status>
        <options><normal/></options>
      </control>
      <control><group>[Master]</group><key>ignored</key><status>0xC0</status><midino>0x01</midino></control>
      <control><group>[Master]</group><key>no_number</key><status>0x90</status></control>
    </controls>
    <outputs>
      <output>
        <group>[Channel1]</group>
        <key>play_indicator</key>
        <status>0x90</status>
        <midino>0x0B</midino>
        <on>0x7F</on>
        <off>0x00</off>
        <minimum>0.5</minimum>
      </output>
    </outputs>
  </controller>
</MixxxControllerPreset>
"""


def _controls(config):
    return {(c.channel, c.event_type, c.control): c for c in config.controls}


def test_controls_and_outputs_become_triggers():
    config = parse_string(MAPPING)
    controls = _controls(config)
    assert config.extra_attrs == {"software": "mixxx", "format": "MixxxControllerPreset", "device": "Test Controller"}
    assert config.app_version == "2.3.0+"
    play = controls[("1", "Note On", "11")]
    assert [u.event for u in play.userios] == ["click", "output"]
    mapping = play.userios[0].mappings[0]
    assert (mapping.tag, mapping.deck_id) == ("play", "1")
    assert mapping.extra_attrs == {
        "software": "mixxx",
        "kind": "input",
        "group": "[Channel1]",
        "description": "Play button",
        "options": "normal",
    }
    led = play.userios[1].mappings[0]
    assert led.extra_attrs["on"] == "0x7F" and led.extra_attrs["minimum"] == "0.5"
    assert controls[("2", "Note On", "11")].userios[0].mappings[0].tag == "Test.deck[1].play.input"
    assert ("1", "Note Off", "11") in controls
    fader = controls[("7", "Control Change", "31")].userios[0].mappings[0]
    assert fader.deck_id is None and fader.extra_attrs["options"] == "soft-takeover,invert"
    assert ("1", "Pitch Bend", "0") in controls
    assert len(controls) == 5  # program change and the binding without midino are skipped


def test_older_root_tag_reads_too():
    old = MAPPING.replace("MixxxControllerPreset", "MixxxMIDIPreset")
    assert parse_string(old).extra_attrs["format"] == "MixxxMIDIPreset"


def test_refusals():
    with pytest.raises(MixxxMappingError):
        parse_string("<midi app='Serato'/>")
    with pytest.raises(MixxxMappingError):
        parse_string("not xml")
    with pytest.raises(ValueError, match="isn't supported"):
        to_xml_string(parse_string(MAPPING))


def test_detected_by_content_even_with_a_plain_xml_suffix():
    assert is_mixxx_text(MAPPING)
    assert [d.plugin_id for d in software.detect_from_text(MAPPING, ".xml")] == ["mixxx"]
    best = detect_software_mapping(MAPPING, ".xml").best
    assert (best.plugin_id, best.score) == ("mixxx", 100)
    assert [d.plugin_id for d in software.detect_from_text("<midi/>", ".xml")] == ["serato"]


def test_validation_has_nothing_serato_specific_to_say():
    from djmidi import validator

    assert validator.validate(parse_string(MAPPING)) == []


def test_controller_setup_learns_triggers_from_a_mixxx_file(tmp_path):
    from djmidi.gui.controller_setup import ControllerSetupView, read_mapping_file

    path = tmp_path / "Test.midi.xml"
    path.write_text(MAPPING, encoding="utf-8")
    assert read_mapping_file(path).extra_attrs["software"] == "mixxx"
    view = ControllerSetupView()
    view._name_edit.setText("From Mixxx")
    view.load_file(path)
    assert {(row.channels[0], row.data1) for row in view._rows} >= {("1", "11"), ("2", "11"), ("7", "31")}
