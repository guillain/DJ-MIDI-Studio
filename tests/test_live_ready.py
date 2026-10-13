"""Issue #254: the Qt-free "Ready for live" check."""

from copy import deepcopy
from pathlib import Path

from djmidi.live_ready import (
    ESSENTIAL_FUNCTIONS,
    check_live_ready,
    mapped_decks,
    report_text,
    tag_words,
)
from djmidi.parser import parse_file, parse_string

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _control(channel, note, *userios):
    return f"<control channel='{channel}' event_type='Note On' control='{note}'>{''.join(userios)}</control>"


def _userio(event, tag, deck, slot="0"):
    return (
        f"<userio event='{event}'><{tag} deck_set='Default' deck_id='{deck}' slot_id='{slot}'>"
        f"<translation action_on='press'/></{tag}></userio>"
    )


def _config(*controls):
    return parse_string(f"<midi app='1.0'>{''.join(controls)}</midi>")


def _full_deck(deck, channel):
    return [
        _control(channel, 0, _userio("click", "play", deck)),
        _control(channel, 1, _userio("click", "cue", deck)),
        _control(channel, 2, _userio("click", "sync", deck)),
        _control(channel, 3, _userio("click", "load_track", deck)),
    ]


def test_essential_list_is_play_cue_sync_load():
    assert [essential.key for essential in ESSENTIAL_FUNCTIONS] == ["play", "cue", "sync", "load"]


def test_tag_words_splits_serato_and_traktor_names():
    assert tag_words("Play/Pause") == ["play", "pause"]
    assert tag_words("auto_loop_roll_specific_length") == ["auto", "loop", "roll", "specific", "length"]
    assert tag_words("Sync On") == ["sync", "on"]


def test_complete_decks_are_ready():
    report = check_live_ready(_config(*_full_deck("1", 1), *_full_deck("2", 2)))
    assert report.findings == []
    assert report.decks == ("1", "2")
    assert report.verdict == "Ready for live."


def test_missing_essentials_are_reported_per_deck_as_warnings():
    controls = _full_deck("1", 1) + [_control(2, 0, _userio("click", "play", "2"))]
    report = check_live_ready(_config(*controls))
    missing = [(f.deck_id, f.message) for f in report.findings if f.category == "essential"]
    assert missing == [
        ("2", "Deck 2 has no Cue mapping."),
        ("2", "Deck 2 has no Sync mapping."),
        ("2", "Deck 2 has no Load mapping."),
    ]
    assert all(f.severity == "warning" and "built-in" in f.hint for f in report.findings)
    assert report.verdict.startswith("Check before playing")


def test_hot_cue_does_not_count_as_cue():
    controls = [c for c in _full_deck("1", 1) if "cue" not in c]
    controls.append(_control(1, 9, _userio("click", "hot_cue", "1")))
    report = check_live_ready(_config(*controls))
    assert [f.message for f in report.findings] == ["Deck 1 has no Cue mapping."]


def test_output_mapping_never_satisfies_an_essential():
    controls = [c for c in _full_deck("1", 1) if "sync" not in c]
    controls.append(_control(1, 9, _userio("output", "sync", "1")))
    report = check_live_ready(_config(*controls))
    assert "Deck 1 has no Sync mapping." in [f.message for f in report.findings]


def test_no_deck_at_all_is_one_warning():
    report = check_live_ready(_config())
    assert len(report.findings) == 1
    assert report.findings[0].severity == "warning"
    assert report.decks == ()


def test_deck_conflict_is_an_error_with_its_control():
    controls = _full_deck("1", 1) + [
        _control(1, 9, _userio("click", "codfather_st", "1"), _userio("click", "codfather_fx", "1")),
    ]
    report = check_live_ready(_config(*controls))
    errors = [f for f in report.findings if f.severity == "error"]
    assert len(errors) == 1
    assert errors[0].category == "conflict"
    assert "Codfather FX" in errors[0].message and "Codfather ST" in errors[0].message
    assert errors[0].control is not None and errors[0].control.control == "9"
    assert report.findings[0] is errors[0]  # errors sort first
    assert report.verdict.startswith("Not ready")


def test_disagreeing_copies_are_an_error_but_identical_copies_are_not():
    same = _control(1, 9, _userio("click", "codfather_st", "1"), _userio("output", "codfather_st", "1"))
    clean = check_live_ready(_config(*_full_deck("1", 1), *_full_deck("2", 2), same, same, same))
    assert clean.findings == []

    other = _control(1, 9, _userio("click", "codfather_st", "2"), _userio("output", "codfather_st", "2"))
    report = check_live_ready(_config(*_full_deck("1", 1), *_full_deck("2", 2), same, other))
    assert [f.category for f in report.findings] == ["conflict"]
    assert "disagree" in report.findings[0].message


def test_input_without_led_feedback_is_info_for_known_output_functions():
    controls = _full_deck("1", 1) + [_control(1, 9, _userio("click", "auto_loop_specific_length", "1", "3"))]
    report = check_live_ready(_config(*controls))
    assert [(f.severity, f.category) for f in report.findings] == [("info", "led")]
    assert "Auto loop · slot 3" in report.findings[0].message
    assert report.verdict == "Ready for live."


def test_led_counterpart_learned_from_the_file_itself():
    controls = _full_deck("1", 1) + [
        _control(1, 9, _userio("click", "censor", "1")),
        _control(1, 10, _userio("click", "censor", "1"), _userio("output", "censor", "1")),
    ]
    report = check_live_ready(_config(*controls))
    led = [f for f in report.findings if f.category == "led"]
    assert len(led) == 1 and led[0].control.control == "9"


def test_function_never_seen_as_output_is_not_flagged():
    controls = _full_deck("1", 1) + [_control(1, 9, _userio("click", "auto_loop_roll_specific_length", "1"))]
    assert check_live_ready(_config(*controls)).findings == []


def test_check_never_changes_the_config():
    config = parse_file(FIXTURE)
    before = deepcopy(config)
    check_live_ready(config)
    assert config == before


def test_real_file_has_no_conflict_or_missing_led():
    report = check_live_ready(parse_file(FIXTURE))
    assert report.decks == mapped_decks(parse_file(FIXTURE))
    # Serato's deck_id is 0-based; the report uses the ids By Deck shows.
    assert report.decks == ("0", "1", "2", "3")
    # The real file only remaps loops/codfather, so the essentials are left to
    # Serato's built-in mapping: warnings, never errors.
    assert {f.category for f in report.findings} == {"essential"}
    assert len(report.findings) == 16


def test_report_text_lists_every_finding_with_its_hint():
    report = check_live_ready(_config(_control(1, 0, _userio("click", "play", "1"))))
    text = report_text(report)
    assert text.splitlines()[0] == report.verdict
    for finding in report.findings:
        assert finding.message in text and finding.hint in text
