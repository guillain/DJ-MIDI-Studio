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


def test_macos_port_name_is_detected():
    # The OS names the port "CMD LC-1", without the manufacturer prefix.
    matches = catalog.detect_controller("CMD LC-1")
    assert [(m.controller.name, m.score) for m in matches] == [(CONTROLLER, 100)]


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
    assert [h for h in catalog.lookup("2", "Note On", "16") if h.controller == CONTROLLER] == []


TRAKTOR = Path(__file__).resolve().parents[1] / "data" / "traktor" / "traktor-settings-4.4.1.tsi.zip"


def _traktor_lc1_device():
    from djmidi.software import _tsi

    with zipfile.ZipFile(TRAKTOR) as archive:
        text = archive.read("Traktor Settings.tsi").decode("utf-8")
    return next(d for d in _tsi.parse_tsi(text).devices if d.comment == "CMD LC-1-CH1")


def test_real_traktor_settings_bind_the_same_notes_on_channel_1():
    """The maintainer's real Traktor 4.4.1 settings map the unit on MIDI
    channel 1: every button note it binds resolves to a CMD LC-1 control."""
    device = _traktor_lc1_device()
    notes = {m.trigger for m in device.mappings if m.direction == "in" and m.trigger and m.trigger.kind == "Note"}
    assert {t.channel for t in notes} == {1}
    assert len(notes) == 52
    for trigger in notes:
        hits = [h for h in catalog.lookup("1", "Note On", str(trigger.number)) if h.controller == CONTROLLER]
        assert len(hits) == 1, trigger


def test_channel_1_and_channel_8_name_the_same_control():
    for note in ("16", "32", "63", "75"):
        on_1 = [h.name for h in catalog.lookup("1", "Note On", note) if h.controller == CONTROLLER]
        assert on_1 == _lc1(note)


def test_supports_serato_and_traktor():
    from djmidi.catalog._registry import get_definition

    definition = get_definition(CONTROLLER)
    assert definition.supported_software == ("serato", "traktor")


def test_the_alternate_channel_adds_no_atelier_feature():
    from djmidi.atelier.features import features_for

    features = features_for(CONTROLLER)
    assert {f.input.channel for f in features} == {8}
    assert all(f.deck is None for f in features)
