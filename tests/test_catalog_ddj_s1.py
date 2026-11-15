"""Pioneer DDJ-S1 catalog module, checked against the real Controller Setup
capture of a real unit (data/controllers/ddj_s1.json) -- Pioneer's MIDI
message list for this controller is no longer published."""

import json
from pathlib import Path

from djmidi import catalog
from djmidi.gui.geometry import CONTROL_GEOMETRY, resolve_geometry_label

CONTROLLER = "DDJ-S1"
CAPTURE = Path(__file__).resolve().parents[1] / "data" / "controllers" / "ddj_s1.json"
EVENT = {"NOTE": "Note On", "CC": "Control Change"}


def _capture():
    return json.loads(CAPTURE.read_text(encoding="utf-8"))


def _hits(channel: str, event_type: str, data1: str):
    return [h for h in catalog.lookup(channel, event_type, data1) if h.controller == CONTROLLER]


def test_every_capture_row_is_backed_by_recorded_events():
    data = _capture()
    events = {(e["channel"], e["event_type"], e["data1"]) for e in data["recorded_events"]}
    for row in data["rows"]:
        assert (row["channels"][0], EVENT[row["note_or_cc"]], row["data1"]) in events, row


def test_every_captured_button_resolves_to_one_control_except_the_jog_touch():
    for row in _capture()["rows"]:
        if row["note_or_cc"] != "NOTE" or row["name"].endswith("JogPushBt"):
            continue
        hits = _hits(row["channels"][0], "Note On", row["data1"])
        assert len(hits) == 1, row


def test_continuous_controls_stay_out_of_the_catalog():
    for row in _capture()["rows"]:
        if row["note_or_cc"] == "CC":
            assert _hits(row["channels"][0], "Control Change", row["data1"]) == [], row


def test_deck_b_and_fx2_reuse_the_deck_a_and_fx1_notes():
    assert [h.name for h in _hits("2", "Note On", "11")] == ["PLAY/PAUSE"]
    assert [h.name for h in _hits("4", "Note On", "64")] == ["FX ON/OFF"]
    assert [h.name for h in _hits("5", "Note On", "47")] == []


def test_port_is_detected():
    matches = catalog.detect_controller("PIONEER DDJ-S1")
    assert matches and matches[0].controller.name == CONTROLLER and matches[0].score == 100


def test_every_entry_has_a_marker_on_both_sides():
    geometry = CONTROL_GEOMETRY[CONTROLLER]
    for entry in catalog.static_entries(CONTROLLER):
        assert resolve_geometry_label(CONTROLLER, entry.name) in geometry, entry.name
        if entry.section != "BROWSE":
            assert f"{entry.name} (R)" in geometry, entry.name
