"""Extended layout.py tests covering branch edge-cases missed previously."""
from __future__ import annotations

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.layout import _base_name, build_layout, cell_key

# ─── _base_name ───────────────────────────────────────────────────────────────

def test_base_name_strips_shift_press_suffix():
    assert _base_name("Cue 1 (+SHIFT press)") == "Cue 1"


def test_base_name_strips_shift_suffix():
    assert _base_name("Loop In (+SHIFT)") == "Loop In"


def test_base_name_strips_plus_shift():
    assert _base_name("Play +SHIFT") == "Play"


def test_base_name_strips_long_press():
    assert _base_name("Sync (long press)") == "Sync"


def test_base_name_strips_direct_button_shift():
    assert _base_name("Hot Cue 1 (direct button, +SHIFT)") == "Hot Cue 1"


def test_base_name_strips_direct_button():
    assert _base_name("Hot Cue 1 (direct button)") == "Hot Cue 1"


def test_base_name_strips_press_twice():
    assert _base_name("Loop Active (press twice)") == "Loop Active"


def test_base_name_returns_unchanged_when_no_suffix():
    assert _base_name("Play/Pause") == "Play/Pause"


# ─── cell_key ─────────────────────────────────────────────────────────────────

def test_cell_key_pad_section_collapses_to_pad_number():
    hit = ControlInfo(
        controller="DDJ-XP2",
        section="PAD",
        name="Deck 1 Pad 5 (PAD MODE 2)",
        note_or_cc="NOTE",
        channels=("8",),
        data1="64",
    )
    key = cell_key(hit)
    assert key == ("DDJ-XP2", "PAD", "Pad 5")


def test_cell_key_non_pad_section_uses_base_name():
    hit = ControlInfo(
        controller="DDJ-XP2",
        section="DECK",
        name="Play (+SHIFT)",
        note_or_cc="NOTE",
        channels=("1",),
        data1="10",
    )
    key = cell_key(hit)
    assert key == ("DDJ-XP2", "DECK", "Play")


def test_cell_key_pad_without_number_uses_full_name():
    hit = ControlInfo(
        controller="DDJ-XP2",
        section="PAD",
        name="Special Pad",
        note_or_cc="NOTE",
        channels=("1",),
        data1="0",
    )
    key = cell_key(hit)
    assert key == ("DDJ-XP2", "PAD", "Special Pad")


# ─── build_layout ─────────────────────────────────────────────────────────────

def test_build_layout_ddj_xp2_has_pads_first():
    cells = build_layout("DDJ-XP2")
    pad_cells = [c for c in cells if c.section == "PAD"]
    assert len(pad_cells) > 0
    # The pad grid leads the layout: no other zone starts above it. (Pad-mode
    # buttons sit beside the pads at the same top row, which is faithful to the
    # real DDJ-XP2, so this is a "starts no lower", not "ends above", check.)
    non_pad_cells = [c for c in cells if c.section != "PAD"]
    if non_pad_cells:
        assert min(c.row for c in pad_cells) <= min(c.row for c in non_pad_cells)


def test_build_layout_returns_unique_keys():
    cells = build_layout("DDJ-XP2")
    keys = [c.key for c in cells]
    assert len(keys) == len(set(keys))


def test_build_layout_unknown_section_does_not_crash():
    cells = build_layout("XDJ-XZ")
    assert len(cells) > 0

