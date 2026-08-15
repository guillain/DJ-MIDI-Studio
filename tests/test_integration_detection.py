from djmidi.integration_detection import (
    detect_controller_ports,
    detect_software_mapping,
)


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
