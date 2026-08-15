from djmidi import software
from djmidi.software.traktor import parse_string, to_xml_string


def test_software_plugins_are_discovered():
    definitions = software.all_definitions()
    assert [definition.plugin_id for definition in definitions] == ["serato", "traktor"]
    assert ".nml" in software.get_definition("traktor").extensions


def test_traktor_plugin_imports_note_and_cc_mappings():
    nml = """
    <NML VERSION="4.0">
      <MAPPINGS>
        <MAPPING NAME="Play" DECK="1"><MIDI CHAN="0"><NOTE NOTE="60" /></MIDI></MAPPING>
        <MAPPING NAME="Filter" DECK="2"><MIDI CHAN="1"><CC CC="21" /></MIDI></MAPPING>
      </MAPPINGS>
    </NML>
    """
    config = parse_string(nml)
    assert [(control.channel, control.event_type, control.control) for control in config.controls] == [
        ("1", "Note On", "60"),
        ("2", "Control Change", "21"),
    ]
    assert config.controls[0].userios[0].mappings[0].tag == "Play"
    assert config.controls[1].userios[0].mappings[0].deck_id == "2"


def test_traktor_plugin_exports_nml():
    nml = "<NML VERSION=\"4.0\"><MAPPINGS><MAPPING NAME=\"Play\"><MIDI CHAN=\"0\"><NOTE NOTE=\"60\" /></MIDI></MAPPING></MAPPINGS></NML>"
    config = parse_string(nml)
    exported = to_xml_string(config)
    assert "<NML" in exported
    assert "<MAPPING NAME=\"Play\">" in exported
    assert "<NOTE NOTE=\"60\"" in exported
