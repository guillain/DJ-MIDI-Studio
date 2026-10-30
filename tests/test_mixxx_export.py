"""Generate a Mixxx mapping from a controller profile (phase 5 item 8)."""

import pytest

from djmidi.mixxx_export import (
    FUNCTIONS,
    Assignment,
    ProfileButton,
    build_mixxx_mapping,
    function_label,
    profile_buttons,
    suggest_function,
)
from djmidi.software.mixxx import parse_string


def _button(name, channel=1, data1=11, kind="NOTE", deck=1, section="DECK"):
    return ProfileButton(section, name, kind, channel, data1, deck)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("PLAY/PAUSE", "play"),
        ("CUE", "cue_default"),
        ("BEAT SYNC", "sync_enabled"),
        ("SYNC", "sync_enabled"),
        ("MASTER TEMPO", "keylock"),
        ("LOAD", "LoadSelectedTrack"),
        ("LOOP IN", "loop_in"),
        ("LOOP IN (long press)", None),
        ("RELOOP/EXIT", "reloop_toggle"),
        ("4 BEAT LOOP", "beatloop_4_toggle"),
        ("1/2X", "loop_halve"),
        ("LOOP DOUBLE", "loop_double"),
        ("Deck 2 Pad 3 (HOT CUE)", "hotcue_3_activate"),
        ("Deck 1 Performance Pad 8 (HOT CUE mode)", "hotcue_8_activate"),
        ("Deck 1 Pad 3 (PAD MODE 2)", None),
        ("KEY SYNC", None),
        ("CUE/LOOP CALL <", None),
    ],
)
def test_suggestions_come_from_control_names(name, key):
    assert suggest_function(_button(name)) == key


def test_every_function_is_attested_and_labelled():
    assert len({function.key for function in FUNCTIONS}) == len(FUNCTIONS)
    assert all(function.mappings >= 4 for function in FUNCTIONS)
    assert function_label(FUNCTIONS[0]) == "Play / pause (play)"


def test_profile_buttons_expand_channels_and_skip_shift():
    buttons = profile_buttons("DDJ-FLX4")
    play = [button for button in buttons if button.name == "PLAY/PAUSE"]
    assert [(button.channel, button.deck) for button in play] == [(1, 1), (2, 2)]
    # A KEY SHIFT pad mode stays; only SHIFT layers are left out.
    assert not any(button.name.upper().endswith("+SHIFT") for button in buttons)
    assert any("(KEY SHIFT)" in button.name for button in buttons)
    pads = [button for button in buttons if suggest_function(button) == "hotcue_1_activate"]
    assert sorted(button.deck for button in pads) == [1, 2]


def test_the_mapping_reads_back_through_the_mixxx_parser():
    assignments = [
        Assignment(_button("PLAY/PAUSE", channel=1, data1=11), "play", 1),
        Assignment(_button("PLAY/PAUSE", channel=2, data1=11), "play", 2),
        Assignment(_button("Pad 1", channel=8, data1=0, section="PAD"), "hotcue_1_activate", 1),
        Assignment(_button("FX", channel=5, data1=20, kind="CC"), "quantize", 3),
    ]
    text = build_mixxx_mapping("Acme <DJ>", assignments, note_off=True)
    assert "<name>Acme &lt;DJ&gt;</name>" in text and "<scriptfiles/>" in text
    config = parse_string(text)
    bindings = sorted(
        (control.channel, control.event_type, control.control, mapping.tag, mapping.deck_id)
        for control in config.controls
        for userio in control.userios
        for mapping in userio.mappings
    )
    assert bindings == [
        ("1", "Note Off", "11", "play", "1"),
        ("1", "Note On", "11", "play", "1"),
        ("2", "Note Off", "11", "play", "2"),
        ("2", "Note On", "11", "play", "2"),
        ("5", "Control Change", "20", "quantize", "3"),
        ("8", "Note Off", "0", "hotcue_1_activate", "1"),
        ("8", "Note On", "0", "hotcue_1_activate", "1"),
    ]
    assert text.count("<normal/>") == 7
    assert "Note Off" not in str(parse_string(build_mixxx_mapping("A", assignments[:1])).controls)


def test_unknown_functions_and_decks_are_refused():
    with pytest.raises(ValueError, match="Not a Mixxx function"):
        build_mixxx_mapping("A", [Assignment(_button("X"), "made_up_key", 1)])
    with pytest.raises(ValueError, match="out of range"):
        build_mixxx_mapping("A", [Assignment(_button("X"), "play", 5)])


def test_dialog_saves_only_rows_with_a_function(tmp_path):
    from djmidi.gui.mixxx_export_dialog import FUNCTION, MixxxExportDialog

    dialog = MixxxExportDialog(["DDJ-FLX4", "XDJ-XZ"], initial="DDJ-FLX4", save_dir=tmp_path)
    try:
        suggested = dialog.assignments()
        assert suggested and all(a.button.name for a in suggested)
        row = next(i for i, b in enumerate(dialog.buttons) if b.name == "PLAY/PAUSE")
        dialog.set_function(row, None)
        assert len(dialog.assignments()) == len(suggested) - 1
        dialog.mapped_only.setChecked(True)
        assert dialog.table.isRowHidden(row)
        assert dialog.table.item(row, FUNCTION).text() == ""
        saved = dialog.save(tmp_path / "flx4.xml")
        assert saved == tmp_path / "flx4.midi.xml" and "<key>cue_default</key>" in saved.read_text(encoding="utf-8")
        dialog.controller_combo.setCurrentText("XDJ-XZ")
        assert dialog.buttons[0].name and len(dialog.assignments()) > len(suggested)
    finally:
        dialog.close()


def test_main_window_opens_one_export_window():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        dialog = window.open_mixxx_export("DDJ-FLX4")
        assert window.open_mixxx_export() is dialog
        assert dialog.controller_combo.currentText() == "DDJ-FLX4"
        dialog.close()
    finally:
        window.close()
