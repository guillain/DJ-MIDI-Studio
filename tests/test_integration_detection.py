from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
from djmidi.integration_detection import (
    ControllerEvidence,
    detect_controller_ports,
    detect_software_mapping,
)
from djmidi.midi_api import parse_midi_identity_reply


def test_controller_detection_reports_explainable_match():
    result = detect_controller_ports(["USB DDJ-XP2 MIDI 1"])
    assert result.status == "match"
    assert result.best is not None
    assert result.best.name == "DDJ-XP2"
    assert result.best.reasons


def test_controller_detection_has_safe_unknown_fallback():
    result = detect_controller_ports(["Unknown MIDI device"])
    assert result.status == "unknown"
    assert result.best is None


def test_software_detection_uses_mapping_signature():
    result = detect_software_mapping("<NML />", ".xml")
    assert result.status == "match"
    assert result.best is not None
    assert result.best.plugin_id == "traktor"
    assert result.best.score == 100


def test_controller_detection_uses_identity_and_capabilities():
    definition = ControllerDefinition(
        name="Identity Test Controller",
        plugin_id="test.identity-controller",
        manufacturer="Test MIDI",
        midi_capabilities=("midi.input", "sysex.identity"),
        midi_identity_ids=(bytes((0x09, 0x01, 0x02, 0x03, 0x04)),),
    )
    register(definition)
    try:
        identity = parse_midi_identity_reply(
            bytes((0xF0, 0x7E, 0x10, 0x06, 0x02, 0x09, 0x01, 0x02, 0x03, 0x04, 1, 2, 3, 4, 0xF7))
        )
        result = detect_controller_ports(
            ["Identity Test Controller MIDI"],
            [ControllerEvidence("Identity Test Controller MIDI", "Test MIDI", frozenset({"sysex.identity"}), identity)],
        )
        assert result.best is not None
        assert result.best.plugin_id == "test.identity-controller"
        assert result.best.score == 100
        assert "MIDI Identity Reply" in " ".join(result.best.reasons)
    finally:
        del catalog._registry._REGISTRY[definition.name]
