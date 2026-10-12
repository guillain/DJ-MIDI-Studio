"""Live conflict detection (issue #223): validator.find_deck_conflicts plus the
Live Monitor's row flag and counter."""

from pathlib import Path

from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.midi_io import MidiEvent
from djmidi.parser import parse_file, parse_string
from djmidi.validator import DeckConflict, find_deck_conflicts

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _control(tag: str, deck: str, slot: str = "0", event: str = "click", note: str = "5") -> str:
    return (
        f"<control channel='1' event_type='Note On' control='{note}'>"
        f"<userio event='{event}'><{tag} deck_set='Default' deck_id='{deck}' slot_id='{slot}'>"
        f"<translation action_on='press'/></{tag}></userio></control>"
    )


def _config(*controls: str):
    return parse_string("<midi app='1.0'>" + "".join(controls) + "</midi>")


def _event(note: str = "5", data2: str = "127", direction: str = "in") -> MidiEvent:
    return MidiEvent(
        direction=direction, channel="1", event_type="Note On", data1=note, data2=data2, timestamp=0.0
    )


def test_real_file_has_no_live_conflicts_despite_10x_duplication():
    assert find_deck_conflicts(parse_file(FIXTURE)) == {}


def test_identical_duplicates_are_not_a_conflict():
    assert find_deck_conflicts(_config(*[_control("play", "1")] * 10)) == {}


def test_two_functions_on_same_deck_conflict():
    conflicts = find_deck_conflicts(_config(_control("play", "1"), _control("cue", "1")))
    assert conflicts == {("1", "Note On", "5"): [DeckConflict("1", (("cue", "0"), ("play", "0")))]}


def test_same_tag_different_slot_is_two_functions():
    conflicts = find_deck_conflicts(_config(_control("hot_cue", "1", "1"), _control("hot_cue", "1", "2")))
    assert conflicts[("1", "Note On", "5")][0].functions == (("hot_cue", "1"), ("hot_cue", "2"))


def test_functions_on_different_decks_do_not_conflict():
    assert find_deck_conflicts(_config(_control("play", "1"), _control("play", "2"))) == {}


def test_output_mappings_are_ignored():
    assert find_deck_conflicts(_config(_control("play", "1"), _control("cue", "1", event="output"))) == {}


def test_describe_lists_deck_and_functions():
    text = DeckConflict("2", (("cue", "0"), ("play", "0"))).describe()
    assert text == "deck 2: cue (slot 0), play (slot 0)"


def _conflicting_view() -> LiveMonitorView:
    view = LiveMonitorView()
    view.set_config(_config(_control("play", "1"), _control("cue", "1"), _control("play", "1", note="6")))
    return view


def test_live_monitor_flags_conflicting_input_row_and_counts_it():
    view = _conflicting_view()
    view._append_event(_event())
    detail = view._log.item(0, 7).text()
    assert detail.startswith("CONFLICT deck 1: cue (slot 0), play (slot 0)")
    assert view._log.item(0, 0).background().color().alpha() > 0
    assert view.conflict_counts() == (1, 1)
    assert "1 live hit(s) on 1 trigger(s)" in view._conflict_label.text()


def test_live_monitor_does_not_flag_clean_trigger_or_output():
    view = _conflicting_view()
    view._append_event(_event(note="6"))
    view._append_event(_event(direction="out"))
    assert "CONFLICT" not in view._log.item(0, 7).text()
    assert "CONFLICT" not in view._log.item(1, 7).text()
    assert view.conflict_counts() == (0, 0)


def test_release_is_flagged_but_not_counted_again():
    view = _conflicting_view()
    view._append_event(_event())
    view._append_event(_event(data2="0"))
    assert "CONFLICT" in view._log.item(1, 7).text()
    assert view.conflict_counts() == (1, 1)


def test_clear_log_and_new_mapping_reset_counter():
    view = _conflicting_view()
    view._append_event(_event())
    view._clear_log()
    assert view.conflict_counts() == (0, 0)
    view._append_event(_event())
    view.set_config(None)
    assert view.conflict_counts() == (0, 0)
    assert "none in the loaded mapping" in view._conflict_label.text()
