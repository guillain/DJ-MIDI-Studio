"""Issue #451: categories, resume, SHIFT and multi-press judging in the guided
check; the captures store; the controller library and its audit."""

from djmidi.atelier import captures as cap
from djmidi.atelier import library as lib
from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register
from djmidi.gui.profile_check import (
    MISMATCH,
    ODD,
    OK,
    ProfileCheck,
    check_items,
    check_sections,
)

NAME = "Library Test"


def _register():
    entries = [
        ControlInfo(NAME, "Deck", "Sync", "NOTE", ("1", "2"), "88"),
        ControlInfo(NAME, "Deck", "Sync +SHIFT", "NOTE", ("1", "2"), "92"),
        ControlInfo(NAME, "Deck", "Cue", "NOTE", ("1", "2"), "12"),
        ControlInfo(NAME, "Deck", "Loop (long press)", "NOTE", ("1",), "40"),
        ControlInfo(NAME, "Browse", "SHIFT", "NOTE", ("7",), "64"),
        ControlInfo(NAME, "Browse", "Load", "NOTE", ("7",), "70"),
    ]
    register(
        ControllerDefinition(name=NAME, static_entries=entries, section_order=("Deck", "Browse")), replace=True
    )


def test_a_check_can_be_limited_to_categories_and_resumed():
    _register()
    assert check_sections(NAME) == ["Deck", "Browse"]
    assert {item.section for item in check_items(NAME, {"Browse"})} == {"Browse"}
    everything = check_items(NAME)
    keys = [item.key for item in everything]
    assert len(set(keys)) == len(keys) and "Deck/Sync/shift" in keys
    resumed = ProfileCheck.start(NAME, only={"Browse/Load/plain"})
    assert [item.title for item in resumed.items] == ["Load"]
    assert next(item for item in everything if "Loop" in item.label).long_press


def test_a_held_shift_is_never_the_control_asked():
    _register()
    check = ProfileCheck.start(NAME, only={"Deck/Sync/shift", "Browse/SHIFT/plain"})
    assert check.current.title == "SHIFT + Sync"
    assert check.judge([("7", "NOTE", "64")]) is None  # SHIFT alone: still waiting
    assert check.judge([("7", "NOTE", "64"), ("1", "NOTE", "92")]).status == OK
    assert check.current.label == "SHIFT"
    assert check.judge([("7", "NOTE", "64")]).status == OK  # asked for SHIFT itself


def test_any_press_of_one_attempt_can_be_the_right_one_and_odd_flags_it():
    _register()
    check = ProfileCheck.start(NAME, only={"Deck/Cue/plain", "Browse/Load/plain"})
    assert check.judge([("3", "NOTE", "114"), ("1", "NOTE", "12")]).got == ("1", "NOTE", "12")
    assert check.mark_odd() and check.results[0].status == ODD
    wrong = check.judge([("7", "NOTE", "71")])
    assert wrong.status == MISMATCH and check.counts()[ODD] == 1


def test_captures_round_trip_and_unknown_software_is_kept_as_other(tmp_path):
    record = cap.CaptureRecord(
        "Deck/Cue/plain", cap.OK, ("1", "NOTE", "12"), (("1", "NOTE", "12"),), "serato", "2026-11-11"
    )
    cap.record_capture(NAME, record, tmp_path)
    cap.record_capture(NAME, cap.CaptureRecord("Deck/Cue/plain", cap.MISMATCH, ("1", "NOTE", "13")), tmp_path)
    loaded = cap.load_captures(NAME, tmp_path)
    assert loaded.records["Deck/Cue/plain|serato"] == record and len(loaded.records) == 2  # one per software
    assert cap.checked_items(loaded, "serato") == {"Deck/Cue/plain": cap.OK}
    raw = cap.captures_file(NAME, tmp_path)
    raw.write_text(raw.read_text().replace('"serato"', '"virtualdj"'))
    assert cap.load_captures(NAME, tmp_path).records["Deck/Cue/plain|other"].software == "other"
    cap.forget_captures(NAME, {"Deck/Cue/plain"}, tmp_path)
    assert cap.load_captures(NAME, tmp_path).records == {}
    raw.write_text("{not json")
    assert cap.load_captures(NAME, tmp_path).records == {}


def test_the_library_maps_captures_onto_atelier_features_and_audits_them():
    _register()
    store = cap.CaptureStore(NAME)
    for record in (
        cap.CaptureRecord("Deck/Sync/plain", cap.OK, ("1", "NOTE", "88"), software="serato"),
        # without software the same button sent something else: not a profile error
        cap.CaptureRecord("Deck/Sync/plain", cap.MISMATCH, ("1", "NOTE", "86")),
        cap.CaptureRecord("Deck/Cue/plain", cap.MISMATCH, ("1", "NOTE", "13")),
    ):
        store.records[record.key] = record
    knowledge = lib.knowledge_for(NAME, store)
    by_id = {entry.feature.id: entry for entry in knowledge}
    assert by_id["deck.sync@1"].status == lib.VERIFIED and by_id["deck.sync@1"].software == "serato"
    assert dict(by_id["deck.sync@1"].per_software) == {"none": lib.MISMATCH, "serato": lib.VERIFIED}
    assert by_id["deck.sync@2"].status == lib.CONTROL_VERIFIED
    assert by_id["deck.cue@1"].status == lib.MISMATCH and by_id["deck.cue@1"].got == ("1", "NOTE", "13")
    assert by_id["browse.load@7"].status == lib.UNTESTED
    assert by_id["deck.sync@1"].source == "documented" and by_id["deck.sync@1"].led == lib.LED_ASSUMED
    rows = {row.item: row for row in lib.audit_controls(NAME, store)}
    assert rows["Deck/Cue/plain"].status == lib.MISMATCH and rows["Deck/Cue/plain"].messages == 2  # one control
    assert rows["Deck/Sync/plain"].status == lib.VERIFIED and rows["Browse/Load/plain"].status == lib.UNTESTED
    counts = lib.audit_counts(list(rows.values()))
    assert counts[lib.VERIFIED] == 1 and counts[lib.MISMATCH] == 1 and counts["total"] == len(rows)
    text = lib.audit_text(NAME, list(rows.values()), "1.2.3")
    assert "## Controller audit: Library Test" in text
    assert text.index("mismatch (got Note 13 ch 1)") < text.index("| Sync | Deck | verified |")
    assert "No DJ software running: mismatch · Serato DJ Pro: verified" in text


def _press(data1, channel="1", data2="127"):
    from djmidi.midi_io import MidiEvent

    return MidiEvent("in", channel, "Note On", str(data1), data2, 0.0, "TEST")


def test_the_dialog_checks_by_category_keeps_verdicts_and_resumes():
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    _register()
    dialog = ProfileCheckDialog([NAME], ["TEST"], ensure_listening=lambda: True, initial=NAME)
    dialog.software_combo.setCurrentIndex(dialog.software_combo.findData("serato"))
    for section, box in dialog.section_checks.items():
        box.setChecked(section == "Browse")
    assert dialog.start() and dialog.prompt.text().startswith("Press SHIFT")
    assert dialog.feed_event(_press(64, "7"))
    assert dialog.check.current.label == "Load"
    assert dialog.feed_event(_press(71, "7"))  # wrong one
    assert dialog.check.done and "Done!" in dialog.prompt.text()
    store = cap.load_captures(NAME)
    assert store.records["Browse/Load/plain|serato"].status == cap.MISMATCH
    assert store.records["Browse/SHIFT/plain|serato"].software == "serato"
    dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("to-redo"))
    assert dialog.start() and [item.label for item in dialog.check.items] == ["Load"]
    dialog.feed_event(_press(70, "7"))
    assert "Bravo" in dialog.prompt.text()
    dialog.tabs.setCurrentIndex(2)
    assert "0 to look at" in dialog.audit_summary.text() and "2 verified" in dialog.audit_summary.text()
    dialog.close()


def test_a_held_shift_waits_and_a_double_press_is_judged_on_the_window():
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    _register()
    dialog = ProfileCheckDialog([NAME], ["TEST"], ensure_listening=lambda: True, initial=NAME, judge_delay_ms=500)
    dialog.start()
    assert dialog.check.current.title == "Sync"
    dialog.feed_event(_press(12))  # Cue's note first...
    dialog.feed_event(_press(88))  # ...then Sync's, in the same attempt
    assert dialog.check.index == 0  # still waiting for the window to close
    dialog.judge_now()
    assert dialog.check.results[0].status == OK
    dialog.feed_event(_press(64, "7"))  # SHIFT held for SHIFT + Sync: ignored
    dialog.judge_now()
    assert dialog.check.index == 1
    dialog.close()


def test_the_lights_tab_records_what_lit_and_plays_the_show():
    from djmidi.atelier.led_data import load_led_data
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    _register()
    sent = []
    dialog = ProfileCheckDialog(
        [NAME], ["TEST"], initial=NAME, output_ports=["OUT"], sender=lambda **message: sent.append(message)
    )
    assert dialog.light_next() and sent[-1]["data2"] == 127
    first = dialog._light_features[0]
    dialog.lit_here()
    assert load_led_data(NAME)[first.id].note == first.led.note
    other_index = dialog.lit_other_combo.findData("browse.load@7")
    dialog.lit_other_combo.setCurrentIndex(other_index)
    second = dialog._light_features[1]
    dialog.lit_other()  # the second LED lit Load instead
    assert load_led_data(NAME)["browse.load@7"].note == second.led.note
    dialog.play_light_show()
    for _ in range(len(dialog._light_features) + 1):
        dialog._light_show_step()
    assert dialog.show_yes_button.isEnabled()
    dialog._light_show_answer(True)
    assert "Bravo" in dialog.light_prompt.text()
    dialog.close()


def test_lights_skip_shift_layers_other_pad_banks_and_upper_decks():
    from djmidi.atelier.features import Feature, FeatureInput, LedOutput
    from djmidi.gui.profile_check_dialog import light_candidates

    def feature(name, deck, channel, note, shift=False, bank=None):
        return Feature(name, NAME, "PAD" if bank else "Deck", name, "pad", deck, shift, bank,
                       FeatureInput("NOTE", channel, note), LedOutput(channel, note))

    features = [
        feature("a", 1, 1, 10), feature("a shift", 1, 1, 70, shift=True), feature("a deck 3", 3, 3, 10),
        feature("pad", 1, 8, 0, bank="PAD MODE 1"), feature("pad m2", 1, 8, 16, bank="PAD MODE 2"),
        feature("same lamp", 1, 1, 10),
    ]
    assert [f.name for f in light_candidates(features)] == ["a", "pad"]
    assert [f.name for f in light_candidates(features, upper_decks=True)] == ["a", "a deck 3", "pad"]


def test_captures_and_led_files_are_not_taken_for_profiles(tmp_path):
    from djmidi.catalog.profile import load_user_profiles

    cap.record_capture(NAME, cap.CaptureRecord("Deck/Cue/plain", cap.OK, ("1", "NOTE", "12")), tmp_path)
    (tmp_path / "library-test.leds.json").write_text('{"format": "djmidi-leds/1", "leds": []}')
    assert load_user_profiles(tmp_path) == ([], {})
