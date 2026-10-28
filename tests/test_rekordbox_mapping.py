"""rekordbox MIDI mapping CSV (read-only plugin).

The CSV is synthetic, in the shape of the mappings rekordbox 7 ships
(see `software/rekordbox/README.md`) -- those are AlphaTheta's files and are
never copied here.
"""

import pytest

from djmidi import software
from djmidi.integration_detection import detect_software_mapping
from djmidi.software.rekordbox import (
    RekordboxMappingError,
    is_rekordbox_text,
    parse_string,
    to_csv_string,
)

HEADER = "#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment"
ROWS = (
    ",,,,,,,,,,,,,,",
    "# Browser,,,,,,,,,,,,,,",
    "Browse,Browse,Rotary,B640,,,,,,,,,,,Browse",
    "Load,Load,Button,,9646,9647,,,,9646,9647,,,,Load to Deck",
    ",,,,,,,,,,,,,,",
    "# Deck,,,,,,,,,,,,,,",
    "Sync,Sync,Button,9058,0,1,2,3,9058,0,1,2,3,Blink=600,Sync On/Off",
    "Master,Sync+Shift,Button,905C,0,1,,,,,,,,,",
    "#,Mute+Shift,Button,9078,0,1,2,3,9078,0,1,2,3,,No function assigned here",
    "#MasterCue,MasterCue,Button,9063,,,,,,,,,,,",
    "JogTimestamp,JogTimestamp,JogTimestamp,E0,0,1,,,,,,,,,",
    "MidiOutInterval,MidiOutInterval,Parameter,FFF3,,,,,,,,,,Value=2,",
    "Pad1,Pad1,Pad,9700,0,2,,,,,,,,Fast",
)
CSV = "\n".join(("@file,1,Test Controller", HEADER, *ROWS))


def _triggers(config):
    return {(c.channel, c.event_type, c.control): c for c in config.controls}


def test_rows_decode_to_controls_per_deck():
    config = parse_string(CSV)
    controls = _triggers(config)
    assert config.extra_attrs == {"software": "rekordbox", "format": "csv", "device": "Test Controller"}

    # A row with no deck column is global, on the status's own channel.
    browse = controls[("7", "Control Change", "64")].userios[0].mappings[0]
    assert (browse.tag, browse.deck_id) == ("Browse", None)
    assert browse.extra_attrs["control_name"] == "Browse"
    assert browse.extra_attrs["type"] == "Rotary"

    # Decimal deck columns are 0-based channel offsets on the input's status.
    for deck in range(1, 5):
        sync = controls[(str(deck), "Note On", "88")]
        assert [u.event for u in sync.userios] == ["click", "output"]
        assert [(m.tag, m.deck_id) for m in sync.userios[0].mappings] == [("Sync", str(deck))]
        assert sync.userios[0].mappings[0].extra_attrs["option"] == "Blink=600"

    # Four-digit deck columns are full addresses, input left empty.
    assert controls[("7", "Note On", "70")].userios[0].mappings[0].deck_id == "1"
    assert controls[("7", "Note On", "71")].userios[0].mappings[0].deck_id == "2"

    # Column 1 is the command, column 2 the control (+Shift = SHIFT layer).
    master = controls[("1", "Note On", "92")].userios[0].mappings[0]
    assert (master.tag, master.extra_attrs["control_name"]) == ("Master", "Sync+Shift")
    assert ("3", "Note On", "92") not in controls

    # Pads: offsets 0 and 2 on channel 8.
    assert ("8", "Note On", "0") in controls and ("10", "Note On", "0") in controls


def test_disabled_rows_and_internal_parameters_are_skipped():
    config = parse_string(CSV)
    tags = {m.tag for c in config.controls for u in c.userios for m in u.mappings}
    assert "Mute" not in tags and "MasterCue" not in tags and "#" not in tags
    assert "MidiOutInterval" not in tags
    assert ("1", "Pitch Bend", "0") in _triggers(config)


def test_bom_and_short_rows_are_tolerated():
    config = parse_string("﻿@file,1,X\n" + HEADER + "\nPlay,Play,Button,900B,0\n")
    assert [(c.channel, c.event_type, c.control) for c in config.controls] == [("1", "Note On", "11")]


def test_non_rekordbox_text_is_refused():
    with pytest.raises(RekordboxMappingError):
        parse_string("<midi />")


def test_saving_is_refused_with_a_readable_message():
    with pytest.raises(ValueError, match="isn't supported"):
        to_csv_string(parse_string(CSV))


def test_detection_by_content_signature():
    assert is_rekordbox_text(CSV) and is_rekordbox_text("﻿" + CSV)
    assert [d.plugin_id for d in software.detect_from_text(CSV, ".csv")] == ["rekordbox"]
    assert [d.plugin_id for d in software.detect_from_text(CSV, ".txt")] == ["rekordbox"]
    best = detect_software_mapping(CSV, ".csv").best
    assert (best.plugin_id, best.score) == ("rekordbox", 100)
    # A CSV without the signature is only an extension guess.
    guess = detect_software_mapping("a,b,c\n", ".csv").best
    assert (guess.plugin_id, guess.score) == ("rekordbox", 70)


def test_validation_does_not_ask_rekordbox_for_serato_slots():
    from djmidi import validator

    assert validator.validate(parse_string(CSV)) == []


def test_validation_still_asks_serato_for_deck_and_slot():
    from djmidi import validator
    from djmidi.model import Control, MappingElement, MidiConfig, UserIO

    config = MidiConfig(
        controls=[Control("1", "Note On", "1", userios=[UserIO("click", mappings=[MappingElement(tag="x")])])]
    )
    assert any("deck_id or slot_id" in issue.message for issue in validator.validate(config))


def test_ready_for_live_reads_rekordbox_camel_case_commands():
    from djmidi.live_ready import check_live_ready, tag_words

    assert tag_words("PlayPause") == ["play", "pause"]
    assert tag_words("HotCue") == ["hot", "cue"]
    rows = [f"{command},{command},Button,{address},0,1,,,,,,,,," for command, address in (
        ("PlayPause", "900B"), ("Cue", "900C"), ("Sync", "9058"), ("Load", "9046"),
    )]
    config = parse_string("\n".join(["@file,1,X", HEADER, *rows]))
    assert [f for f in check_live_ready(config).findings if f.category == "essential"] == []


def test_main_window_opens_a_rekordbox_csv_and_refuses_to_save_it(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from djmidi.gui.main_window import MainWindow

    path = tmp_path / "Test.midi.csv"
    path.write_text(CSV, encoding="utf-8")
    window = MainWindow()
    window._load_mapping_from_path(path, software_id="rekordbox")
    assert window.software_id == "rekordbox"
    assert len(window.config.controls) == len(parse_string(CSV).controls)
    assert window.channel_splitter.count() > 0

    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[2]))
    window._on_save()
    assert errors and "isn't supported" in errors[0]
    assert path.read_text(encoding="utf-8") == CSV
    window.close()
