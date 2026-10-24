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


def test_inpulse_500_pad_mode_buttons_map_to_variant_tokens():
    for n in range(1, 9):
        assert pad_mode.mode_token_for_button("Hercules DJControl Inpulse 500", f"PAD MODE {n}") == f"(PAD MODE {n})"


# ---- issue #350: DDJ-FLX4 / DDJ-800 / DDJ-REV5 ------------------------------


def _pad_names(controller: str) -> list[str]:
    from djmidi.gui import layout

    return [v.name for v in layout.reverse_lookup(controller)[(controller, "PAD", "Pad 1")]]


def test_issue_350_every_mode_button_is_a_catalog_cell_and_its_token_a_pad_bank():
    from djmidi import catalog

    for controller in ("DDJ-FLX4", "DDJ-800", "DDJ-REV5"):
        names = {entry.name for entry in catalog.static_entries(controller)}
        pads = _pad_names(controller)
        tables = (pad_mode._PAD_MODE_TOKENS[controller], pad_mode._SHIFT_PAD_MODE_TOKENS.get(controller, {}))
        for table in tables:
            for button, token in table.items():
                assert button in names, (controller, button)
                assert any(token.casefold() in name.casefold() for name in pads), (controller, token)


def test_issue_350_shift_selects_the_shift_layer_mode_where_named():
    assert pad_mode.mode_token_for_button("DDJ-FLX4", "HOT CUE MODE") == "(HOT CUE)"
    assert pad_mode.mode_token_for_button("DDJ-FLX4", "HOT CUE MODE", shift=True) == "(KEYBOARD)"
    assert pad_mode.mode_token_for_button("DDJ-FLX4", "SAMPLER MODE (R)", shift=True) == "(KEY SHIFT)"
    assert pad_mode.mode_token_for_button("DDJ-REV5", "SAVED LOOP MODE", shift=True) == "(STEMS MODE)"
    # DDJ-800's PDF never names its SHIFT-layer modes: SHIFT keeps the plain one.
    assert pad_mode.mode_token_for_button("DDJ-800", "PAD FX MODE", shift=True) == "(PAD FX 1 PAGE "
    # Controllers without a SHIFT layer are unchanged.
    assert pad_mode.mode_token_for_button("DDJ-XP2", "PAD MODE 2", shift=True) == "(PAD MODE 2)"
    assert pad_mode.mode_token_for_button("DDJ-FLX4", "PLAY/PAUSE", shift=True) is None
