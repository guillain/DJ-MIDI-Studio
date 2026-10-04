"""Behringer CMD Micro catalog module, checked against a dictated capture of
the maintainer's real unit (2026-10-04) and against their real Traktor export
committed as data/traktor/cmd-studio-4a.tsi.zip (device "CMD MICRO Mixer").

The captured values below are copied verbatim from the capture log, not
derived from the module's own table."""

import zipfile
from pathlib import Path

import pytest

from djmidi import catalog
from djmidi.software import _tsi

pytest.importorskip("djmidi.catalog.behringer_cmd_micro")

MICRO = "Behringer CMD Micro"
TSI = Path(__file__).resolve().parents[1] / "data" / "traktor" / "cmd-studio-4a.tsi.zip"

# Printed label -> note, all on channel 1.
MICRO_CAPTURE = {
    "Deck A PITCHBEND -": 16, "Deck A PITCHBEND +": 17, "Deck A 1": 18, "Deck A 2": 19, "LOAD A": 20,
    "Deck A SYNC": 22, "Deck A PLAY/PAUSE": 23, "Deck A CUE": 24, "CUE A": 25,
    "Deck B PITCHBEND -": 32, "Deck B PITCHBEND +": 33, "Deck B 1": 34, "Deck B 2": 36, "LOAD B": 37,
    "Deck B SYNC": 38, "Deck B PLAY/PAUSE": 39, "Deck B CUE": 40, "CUE B": 41,
    "LEFT": 48, "RIGHT": 49,
}  # fmt: skip


def _names(controller: str, channel: str, note: int) -> list[str]:
    return [h.name for h in catalog.lookup(channel, "Note On", str(note)) if h.controller == controller]


def _traktor_notes(device_name: str) -> set[tuple[str, int]]:
    with zipfile.ZipFile(TSI) as archive:
        document = _tsi.parse_tsi(archive.read(archive.namelist()[0]).decode("utf-8"))
    (device,) = [d for d in document.devices if (d.comment or d.name) == device_name]
    return {
        (str(m.trigger.channel), m.trigger.number)
        for m in device.mappings
        if m.trigger and m.direction == "in" and m.trigger.kind == "Note"
    }


def test_macos_port_name_is_detected():
    assert [m.controller.name for m in catalog.detect_controller("CMD Micro")] == [MICRO]


def test_every_captured_micro_button_resolves_to_its_label():
    for name, note in MICRO_CAPTURE.items():
        assert _names(MICRO, "1", note) == [name]


def test_micro_profile_has_exactly_the_captured_buttons():
    assert len(catalog.static_entries(MICRO)) == len(MICRO_CAPTURE)


def test_micro_matches_the_real_traktor_export():
    # The export also maps notes 1 and 2, which no button sent on the unit.
    traktor = _traktor_notes("CMD MICRO Mixer") - {("1", 1), ("1", 2)}
    assert traktor == {("1", note) for note in MICRO_CAPTURE.values()}
