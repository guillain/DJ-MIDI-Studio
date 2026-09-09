"""gui/pad_mode.py -- pad-mode-select button table (Qt-free)."""

from djmidi.gui import pad_mode


def test_grid_side_reads_the_right_suffix():
    assert pad_mode.grid_side("Pad 3") == ""
    assert pad_mode.grid_side("Pad 3 (R)") == " (R)"
    assert pad_mode.grid_side("PAD MODE 2 (R)") == " (R)"


def test_ddj_xp2_pad_mode_buttons_map_to_variant_tokens():
    for n in range(1, 9):
        assert pad_mode.mode_token_for_button("DDJ-XP2", f"PAD MODE {n}") == f"(PAD MODE {n})"
    # right-grid label -> same token
    assert pad_mode.mode_token_for_button("DDJ-XP2", "PAD MODE 2 (R)") == "(PAD MODE 2)"


def test_xdj_xz_pad_mode_buttons_map_to_mode_tokens():
    assert pad_mode.mode_token_for_button("XDJ-XZ", "HOT CUE") == "(HOT CUE mode)"
    assert pad_mode.mode_token_for_button("XDJ-XZ", "BEAT LOOP") == "(BEAT LOOP mode)"
    assert pad_mode.mode_token_for_button("XDJ-XZ", "SLIP LOOP") == "(SLIP LOOP mode)"
    assert pad_mode.mode_token_for_button("XDJ-XZ", "BEAT JUMP") == "(BEAT JUMP mode)"


def test_non_pad_mode_labels_and_unmodelled_controllers_return_none():
    assert pad_mode.mode_token_for_button("DDJ-XP2", "Pad 1") is None
    assert pad_mode.mode_token_for_button("DDJ-XP2", "SHIFT") is None
    assert pad_mode.mode_token_for_button("XDJ-XZ", "PLAY/PAUSE") is None
    # DDJ-1000/FLX10/REV1/Numark have no pad-mode-select buttons modelled.
    assert pad_mode.mode_token_for_button("DDJ-1000", "HOT CUE") is None
    assert pad_mode.is_pad_mode_button("DDJ-1000", "HOT CUE") is False
    assert pad_mode.is_pad_mode_button("DDJ-XP2", "PAD MODE 4") is True
