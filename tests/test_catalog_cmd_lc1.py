"""Behringer CMD LC-1 catalog module, checked against the maintainer's real
Serato export committed as data/serato/cmd-lc1.xml.zip -- not synthetic XML.

No official MIDI message list exists for this controller: the module was
built with Controller Setup (XML import + live learning on the real
hardware), so the real export is the only external evidence to test against."""

import zipfile
from collections import Counter
from pathlib import Path

import pytest

from djmidi import catalog
from djmidi.parser import parse_string

pytest.importorskip("djmidi.catalog.behringer_cmd_lc_1")

CONTROLLER = "Behringer CMD LC-1"
DATA = Path(__file__).resolve().parents[1] / "data" / "serato" / "cmd-lc1.xml.zip"


def _real_triggers() -> Counter[tuple[str | None, str | None, str | None]]:
    with zipfile.ZipFile(DATA) as archive:
        xml_text = archive.read("cmd-lc1.xml").decode("utf-8")
    config = parse_string(xml_text)
    return Counter((c.channel, c.event_type, c.control) for c in config.controls)


def test_controller_is_registered():
    assert CONTROLLER in catalog.CONTROLLER_NAMES


def test_real_export_shape():
    triggers = _real_triggers()
    assert len(triggers) == 30
    # Each trigger repeats 9 times here, not 10 as in the XDJ-XZ/DDJ-XP2
    # export: the duplication count is not a Serato-wide constant.
    assert set(triggers.values()) == {9}


def test_every_real_trigger_resolves_to_exactly_one_cmd_lc1_control():
    for channel, event_type, data1 in _real_triggers():
        hits = [h for h in catalog.lookup(channel, event_type, data1) if h.controller == CONTROLLER]
        assert len(hits) == 1, (channel, event_type, data1, hits)
        assert hits[0].name



def _lc1(data1: str, event_type: str = "Note On") -> list[str]:
    return [h.name for h in catalog.lookup("8", event_type, data1) if h.controller == CONTROLLER]


def test_layout_captured_from_hardware():
    assert _lc1("16") == ["Button 1"]
    assert _lc1("17") == ["Button 2"]
    assert _lc1("21") == ["Button 6"]
    assert _lc1("32") == ["Row 1 Button 1"]
    assert _lc1("63") == ["Row 8 Button 4"]
    assert _lc1("64") == ["MUTE 1"]
    assert _lc1("71") == ["SOLO 4"]
    assert _lc1("75") == ["RECORD 4"]


def test_gaps_and_encoders_do_not_resolve():
    for note in range(24, 32):
        assert _lc1(str(note)) == []
    assert _lc1("16", "Control Change") == []
    assert _lc1("16") != []
    assert [h for h in catalog.lookup("1", "Note On", "16") if h.controller == CONTROLLER] == []
