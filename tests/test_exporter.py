from pathlib import Path

from djmidi.exporter import to_xml_string
from djmidi.parser import parse_file, parse_string

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def test_roundtrip_preserves_structure():
    original = parse_file(FIXTURE)
    exported_xml = to_xml_string(original)
    reparsed = parse_string(exported_xml)
    assert reparsed == original


def test_roundtrip_twice_is_stable():
    original = parse_file(FIXTURE)
    first_pass = to_xml_string(original)
    second_pass = to_xml_string(parse_string(first_pass))
    assert first_pass == second_pass


def test_exported_xml_has_no_attribute_data_loss():
    config = parse_string(
        '<midi app="1.0"><control channel="1" event_type="Note On" control="1">'
        '<userio event="click"><foo deck_set="Default" deck_id="1" slot_id="0">'
        '<translation action_on="press"/></foo></userio></control></midi>'
    )
    xml_out = to_xml_string(config)
    assert 'app="1.0"' in xml_out
    assert 'deck_id="1"' in xml_out
    assert 'action_on="press"' in xml_out
