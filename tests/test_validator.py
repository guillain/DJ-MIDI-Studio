from pathlib import Path

from djmidi.parser import parse_file, parse_string
from djmidi.validator import validate

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_sample_file_has_no_structural_errors():
    config = parse_file(FIXTURE)
    issues = validate(config)
    assert all(issue.severity != "error" for issue in issues)


def test_detects_duplicate_trigger():
    config = parse_string(
        "<midi app='1.0'>"
        "<control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='press'/></foo></userio></control>"
        "<control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><bar deck_set='Default' deck_id='2' slot_id='0'>"
        "<translation action_on='press'/></bar></userio></control>"
        "</midi>"
    )
    issues = validate(config)
    assert any(i.severity == "error" and "different mappings" in i.message for i in issues)


def test_identical_duplicate_trigger_is_only_informational():
    config = parse_string(
        "<midi app='1.0'>"
        "<control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='press'/></foo></userio></control>"
        "<control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='press'/></foo></userio></control>"
        "</midi>"
    )
    issues = validate(config)
    assert not any(i.severity == "error" for i in issues)
    assert any(i.severity == "info" and "do not deduplicate" in i.message for i in issues)


def test_detects_missing_required_field():
    config = parse_string(
        "<midi app='1.0'><control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='' slot_id='0'>"
        "<translation action_on='press'/></foo></userio></control></midi>"
    )
    issues = validate(config)
    assert any(i.severity == "error" and "deck_id" in i.message for i in issues)


def test_detects_inconsistent_click_targets():
    config = parse_string(
        "<midi app='1.0'>"
        "<control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='press' behaviour='toggle'/></foo></userio></control>"
        "<control channel='1' event_type='Note On' control='6'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='press' behaviour='explicit'/></foo></userio></control>"
        "</midi>"
    )
    issues = validate(config)
    assert any(i.severity == "warning" and "inconsistent behaviour" in i.message for i in issues)


def test_flags_unrecognized_action_on_as_info():
    config = parse_string(
        "<midi app='1.0'><control channel='1' event_type='Note On' control='5'>"
        "<userio event='click'><foo deck_set='Default' deck_id='1' slot_id='0'>"
        "<translation action_on='weird_value'/></foo></userio></control></midi>"
    )
    issues = validate(config)
    assert any(i.severity == "info" and "action_on" in i.message for i in issues)
