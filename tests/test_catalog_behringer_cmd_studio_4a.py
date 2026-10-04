"""Behringer CMD Studio 4a catalog module, checked against a dictated capture
of the maintainer's real unit in all four deck layers (2026-10-04) and against
their real Traktor export committed as data/traktor/cmd-studio-4a.tsi.zip
(device "S4A_MAPPING").

The captured values below are copied verbatim from the capture log, not
derived from the module's own tables."""

import zipfile
from pathlib import Path

import pytest

from djmidi import catalog
from djmidi.software import _tsi

pytest.importorskip("djmidi.catalog.behringer_cmd_studio_4a")

STUDIO = "Behringer CMD Studio 4a"
TSI = Path(__file__).resolve().parents[1] / "data" / "traktor" / "cmd-studio-4a.tsi.zip"

# Same notes on both layers of a side; label -> note.
STUDIO_LEFT = {
    "FX 1 1": 16, "FX 1 2": 17, "FX 1 3": 18, "FX 1 4": 19, "SCRATCH": 22, "LOOP <": 23, "LOOP >": 24,
    "LOOP ON/OFF": 25, "LOCK": 27, "PITCH BEND -": 32, "PITCH BEND +": 33,
    "HOT CUE 1": 34, "HOT CUE 2": 35, "HOT CUE 3": 36, "HOT CUE 4": 37, "HOT CUE 5": 38, "HOT CUE 6": 39,
    "HOT CUE 7": 40, "HOT CUE 8": 41, "HOT CUE DEL": 42, "CUE": 43, "PLAY/PAUSE": 44, "SYNC": 45,
    "LOAD": 80, "FX ASSIGN 1": 82, "FX ASSIGN 2": 83, "KILL HIGH": 96, "KILL MID": 97, "KILL LOW": 98,
    "PHONES": 106,
}  # fmt: skip
STUDIO_RIGHT = {
    "FX 2 1": 48, "FX 2 2": 49, "FX 2 3": 50, "FX 2 4": 51, "SCRATCH": 54, "LOOP >": 55, "LOOP <": 56,
    "LOOP ON/OFF": 57, "LOCK": 59, "PITCH BEND -": 64, "PITCH BEND +": 65,
    "HOT CUE 1": 66, "HOT CUE 2": 67, "HOT CUE 3": 68, "HOT CUE 4": 69, "HOT CUE 5": 70, "HOT CUE 6": 71,
    "HOT CUE 7": 72, "HOT CUE 8": 73, "HOT CUE DEL": 74, "CUE": 75, "PLAY/PAUSE": 76, "SYNC": 77,
    "LOAD": 81, "FX ASSIGN 1": 84, "FX ASSIGN 2": 85, "KILL HIGH": 99, "KILL MID": 100, "KILL LOW": 101,
    "PHONES": 107,
}  # fmt: skip
STUDIO_GLOBAL = {("1", 1): "ENTER", ("1", 2): "<", ("1", 3): ">"}
STUDIO_DECK_SELECT = {("1", 20): "DECK A", ("3", 21): "DECK C", ("2", 52): "DECK B", ("4", 53): "DECK D"}


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
    assert [m.controller.name for m in catalog.detect_controller("Studio 4A")] == [STUDIO]


@pytest.mark.parametrize(
    ("labels", "decks", "channels"), [(STUDIO_LEFT, "A/C", ("1", "3")), (STUDIO_RIGHT, "B/D", ("2", "4"))]
)
def test_every_captured_studio_button_resolves_on_both_layers(labels, decks, channels):
    for label, note in labels.items():
        for channel in channels:
            assert _names(STUDIO, channel, note) == [f"{label} ({decks})"]


def test_studio_global_and_deck_select_buttons():
    for (channel, note), name in {**STUDIO_GLOBAL, **STUDIO_DECK_SELECT}.items():
        assert _names(STUDIO, channel, note) == [name]
    # A deck-select button only exists on its own layer's channel.
    assert _names(STUDIO, "3", 20) == []
    assert _names(STUDIO, "1", 21) == []


def test_every_traktor_studio_note_is_a_captured_button():
    for channel, note in _traktor_notes("S4A_MAPPING"):
        assert len(_names(STUDIO, channel, note)) == 1, (channel, note)


def test_studio_profile_has_exactly_the_captured_buttons():
    assert len(catalog.static_entries(STUDIO)) == len(STUDIO_LEFT) + len(STUDIO_RIGHT) + 7
