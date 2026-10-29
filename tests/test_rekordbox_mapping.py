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


# ─── Controller Setup import: named, discrete profile rows ────────────────────

PROFILE_ROWS = (
    "# Browser,,,,,,,,,,,,,,",
    "Browse,Browse,Rotary,B640,,,,,,,,,,,",
    "Forward,Browse+Press,Button,9641,,,,,,,,,,,",
    "Load,Load,Button,,9646,9647,,,,,,,,,",
    "# Deck,,,,,,,,,,,,,,",
    "Sync,Sync,Button,9058,0,1,,,9058,0,1,,,,",
    "Master,Sync+Shift,Button,905C,0,1,,,,,,,,,",
    "TempoSlider,TempoSlider,KnobSliderHiRes,B000,0,1,,,,,,,,,",
    "SyncLed,SyncLed,Indicator,,,,,,9070,0,1,,,,",
    "# Performance,,,,,,,,,,,,,,",
    "PageLeft_PadMode3,PageLeft,Button,9026,0,1,,,,,,,,,",
    "Parameter1Left_Sampler,PageLeft,Button,9003,0,1,,,,,,,,,",
    "Forward2,Twice,Button,9050,0,,,,,,,,,,",
    "Forward2,Twice,Button,9051,0,,,,,,,,,,",
    "PAD1_PadMode1,PAD1_PadMode1,Pad,9700,0,2,,,,,,,,,",
)
PROFILE_CSV = "\n".join(("@file,1,Test Controller", HEADER, *PROFILE_ROWS))


def _rows():
    from djmidi.software.rekordbox import profile_rows

    return profile_rows(parse_string(PROFILE_CSV))


def test_profile_rows_keep_discrete_inputs_named_and_grouped():
    rows = _rows()
    by_trigger = {(r.channel, r.kind, r.data1): (r.section, r.name) for r in rows}
    assert by_trigger[("7", "NOTE", "65")] == ("Browser", "Browse+Press")
    assert by_trigger[("1", "NOTE", "88")] == ("Deck", "Sync")
    assert by_trigger[("2", "NOTE", "88")] == ("Deck", "Sync")
    assert by_trigger[("1", "NOTE", "92")] == ("Deck", "Sync +SHIFT")
    assert by_trigger[("8", "NOTE", "0")] == ("PAD", "Pad 1 (PadMode1)")
    # Rotary / fader inputs and LED-only rows are left out.
    assert ("7", "CC", "64") not in by_trigger
    assert ("1", "CC", "0") not in by_trigger
    assert ("1", "NOTE", "112") not in by_trigger


def test_profile_rows_disambiguate_reused_control_names():
    by_trigger = {(r.channel, r.data1): r.name for r in _rows()}
    # A per-deck note on one channel -> deck suffix.
    assert by_trigger[("7", "70")] == "Load (Deck 1)"
    assert by_trigger[("7", "71")] == "Load (Deck 2)"
    # One button, a note per pad mode -> command in brackets.
    assert by_trigger[("1", "38")] == "PageLeft [PageLeft_PadMode3]"
    assert by_trigger[("1", "3")] == "PageLeft [Parameter1Left_Sampler]"
    # Same control and command on two notes -> numbered.
    assert {by_trigger[("1", "80")], by_trigger[("1", "81")]} == {"Twice [Forward2] (Deck 1)", "Twice [Forward2] (Deck 1) #2"}


def test_profile_rows_fold_by_channel_without_conflicts():
    from djmidi.catalog._registry import ControlInfo
    from djmidi.catalog.codegen import find_trigger_conflicts, merge_by_channel

    entries = [ControlInfo("X", r.section, r.name, r.kind, (r.channel,), r.data1) for r in _rows()]
    assert find_trigger_conflicts(entries) == []
    merged = merge_by_channel(entries)
    names = [(m.section, m.name) for m in merged]
    assert len(names) == len(set(names))
    sync = next(m for m in merged if m.name == "Sync")
    assert sync.channels == ("1", "2")


def test_controller_setup_imports_a_rekordbox_csv_with_names(tmp_path):
    from djmidi.catalog.codegen import generate_module_source
    from djmidi.gui.controller_setup import ControllerSetupView

    path = tmp_path / "Test.midi.csv"
    path.write_text(PROFILE_CSV, encoding="utf-8")
    view = ControllerSetupView()
    view._name_edit.setText("Test Controller (rekordbox)")
    view.load_file(path)
    assert view._rows and all(row.name and row.section for row in view._rows)
    assert set(view._sources) == {"rekordbox-import"}
    assert all(device == path.name for device in view._devices)
    assert ("Deck", "Sync") in {(row.section, row.name) for row in view._rows}
    source = generate_module_source(view._controller_name, view._rows)
    assert "'Sync'" in source or '"Sync"' in source


def test_profile_names_follow_the_catalog_convention():
    from djmidi.software.rekordbox import profile_name

    assert profile_name("Deck", "Sync+Shift") == ("Deck", "Sync +SHIFT")
    assert profile_name("Performance", "PAD3_PadMode2+Shift") == ("PAD", "Pad 3 (PadMode2) +SHIFT")
    assert profile_name("Performance", "PAD12.HotCue.Call") == ("PAD", "Pad 12 (HotCue.Call)")
    assert profile_name("", "Load") == ("Other", "Load")
