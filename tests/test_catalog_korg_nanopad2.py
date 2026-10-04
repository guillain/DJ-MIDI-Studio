"""Korg nanoPAD2 catalog module, checked against a live capture of the
maintainer's real unit (2026-10-04): each pad pressed once per scene, top row
then bottom row, left to right. The notes below are copied verbatim from that
capture, not derived from the module's own formula."""

import pytest

from djmidi import catalog

pytest.importorskip("djmidi.catalog.korg_nanopad2")

CONTROLLER = "Korg nanoPAD2"

# scene -> (top row notes, bottom row notes), as captured, on MIDI channel 1.
CAPTURED = {
    1: ((0, 1, 2, 3, 24, 25, 26, 27), (12, 13, 14, 15, 36, 37, 38, 39)),
    2: ((4, 5, 6, 7, 28, 29, 30, 31), (16, 17, 18, 19, 40, 41, 42, 43)),
    3: ((48, 49, 50, 51, 72, 73, 74, 75), (60, 61, 62, 63, 84, 85, 86, 87)),
    4: ((52, 53, 54, 55, 76, 77, 78, 79), (64, 65, 66, 67, 88, 89, 90, 91)),
}


def _nanopad_hits(channel: str, data1: int) -> list[catalog.ControlInfo]:
    return [h for h in catalog.lookup(channel, "Note On", str(data1)) if h.controller == CONTROLLER]


def test_controller_is_registered():
    assert CONTROLLER in catalog.CONTROLLER_NAMES


def test_macos_port_name_is_detected():
    # macOS names the port "nanoPAD2 PAD".
    matches = catalog.detect_controller("nanoPAD2 PAD")
    assert [m.controller.name for m in matches] == [CONTROLLER]


@pytest.mark.parametrize("scene", sorted(CAPTURED))
def test_every_captured_pad_resolves_to_its_position(scene):
    for row, notes in zip(("Top", "Bottom"), CAPTURED[scene], strict=True):
        for col, note in enumerate(notes, start=1):
            hits = _nanopad_hits("1", note)
            assert [(h.section, h.name) for h in hits] == [(f"SCENE {scene}", f"Scene {scene} {row} Pad {col}")]


def test_profile_has_exactly_the_captured_pads():
    captured = {note for rows in CAPTURED.values() for notes in rows for note in notes}
    assert len(captured) == 64
    for note in range(128):
        assert bool(_nanopad_hits("1", note)) == (note in captured)


def test_other_channels_do_not_resolve():
    assert _nanopad_hits("10", 36) == []
