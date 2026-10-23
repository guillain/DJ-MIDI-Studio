"""Reverse function search (issue #185), on the user's real config."""

from pathlib import Path

import pytest

from djmidi.function_search import (
    Trigger,
    index_functions,
    physical_names,
    readable_label,
    search_functions,
    tokenize,
)
from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.parser import parse_file

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


@pytest.fixture(scope="module")
def config():
    return parse_file(SAMPLE)


def test_readable_label_and_tokenize():
    assert readable_label("auto_loop_roll_specific_length") == "auto loop roll specific length"
    assert tokenize("Deck-2  Loop_Roll") == ["deck", "2", "loop", "roll"]


def test_index_collapses_the_10x_duplicates_into_one_trigger(config):
    index = index_functions(config)
    roll = [r for r in index if r.tag == "auto_loop_roll_specific_length" and r.deck_id == "2" and r.slot_id == "3"]
    assert len(roll) == 1
    (result,) = roll
    # Ten verbatim duplicates in the file, one trigger in the result.
    assert len(result.mappings) == 10
    assert len(result.triggers) == len(result.controls) == 1
    control = result.controls[0]
    assert result.triggers[0] == Trigger(control.channel, control.event_type, control.control)


def test_empty_or_blank_query_returns_nothing(config):
    assert search_functions(config, "") == []
    assert search_functions(config, "  -_ ") == []


def test_words_match_case_insensitively_with_underscores_as_spaces(config):
    results = search_functions(config, "LOOP Roll")
    assert results
    assert {r.tag for r in results} == {"auto_loop_roll_specific_length"}
    # 4 decks x 4 slots, click only in this file.
    assert len(results) == 16


def test_deck_and_slot_pin_the_ids(config):
    results = search_functions(config, "deck 2 loop roll")
    assert {r.deck_id for r in results} == {"2"}
    assert len(results) == 4
    (only,) = search_functions(config, "loop roll deck 1 slot 5")
    assert (only.deck_id, only.slot_id) == ("1", "5")


def test_event_word_filters_click_or_output(config):
    outputs = search_functions(config, "codfather fx output")
    assert outputs and {r.event for r in outputs} == {"output"}
    assert search_functions(config, "loop roll led") == []


def test_results_carry_the_readable_name(config):
    (result,) = search_functions(config, "loop roll deck 2 slot 3")
    assert result.label == "Loop roll"
    assert result.tag == "auto_loop_roll_specific_length"


def test_readable_name_words_match_too(monkeypatch):
    from djmidi import function_names

    monkeypatch.setitem(function_names.FUNCTION_NAMES, "xfn_42", "Beat jump")
    config = MidiConfig(
        controls=[Control("1", "Note On", "1", [UserIO("click", [MappingElement("xfn_42", deck_id="0")])])]
    )
    (result,) = search_functions(config, "beat jump")
    assert result.label == "Beat jump"
    assert [r.tag for r in search_functions(config, "xfn")] == ["xfn_42"]


def test_ranking_prefers_whole_words_then_click(config):
    results = search_functions(config, "loop")
    tags = [r.tag for r in results]
    assert set(tags) == {"auto_loop_roll_specific_length", "auto_loop_specific_length"}
    # Equal word score: clicks come before LED outputs.
    events = [r.event for r in results]
    assert events == sorted(events, key=lambda e: e != "click")
    # A prefix ("rol") still matches, but scores below an exact word.
    exact = search_functions(config, "roll")[0].score
    prefix = search_functions(config, "rol")[0].score
    assert prefix < exact


def test_unknown_word_matches_nothing(config):
    assert search_functions(config, "loop banana") == []


def test_reusing_an_index_gives_the_same_results(config):
    index = index_functions(config)
    assert [id(r) for r in search_functions(index, "codfather st")] == [
        id(r) for r in search_functions(index, "codfather st")
    ]
    assert len(search_functions(index, "codfather st")) == len(search_functions(config, "codfather st"))


def test_bare_number_matches_deck_or_slot():
    def mapping_control(note: str, deck: str, slot: str) -> Control:
        return Control(
            channel="1",
            event_type="Note On",
            control=note,
            userios=[UserIO("click", [MappingElement("hot_cue", deck_id=deck, slot_id=slot)])],
        )

    config = MidiConfig(controls=[mapping_control("1", "0", "3"), mapping_control("2", "3", "0"), mapping_control("3", "1", "1")])
    results = search_functions(config, "hot cue 3")
    assert {(r.deck_id, r.slot_id) for r in results} == {("0", "3"), ("3", "0")}
    (pinned,) = search_functions(config, "hot cue slot 3")
    assert pinned.location() == "Deck 0 · Slot 3"


def test_physical_names_come_from_the_catalog(config):
    (result,) = search_functions(config, "loop roll deck 2 slot 3")
    names = physical_names(result.triggers[0])
    assert any(name.startswith("DDJ-XP2: ") for name in names)


def test_french_keywords_work_alongside_the_english_ones(config):
    """Issue #326: `platine N` / `emplacement N` pin like `deck N` / `slot N`,
    and the French event words filter like `click` / `output`."""
    english = search_functions(config, "loop roll deck 1 slot 5")
    french = search_functions(config, "loop roll platine 1 emplacement 5")
    assert [(r.tag, r.deck_id, r.slot_id) for r in french] == [(r.tag, r.deck_id, r.slot_id) for r in english]
    assert len(french) == 1
    assert {r.deck_id for r in search_functions(config, "platine 2 loop roll")} == {"2"}
    assert {r.slot_id for r in search_functions(config, "loop roll emplacement 3")} == {"3"}
    # Both languages mix in one query.
    assert len(search_functions(config, "loop roll platine 1 slot 5")) == 1
    outputs = search_functions(config, "codfather fx sortie")
    assert outputs and {r.event for r in outputs} == {"output"}
    assert [r.event for r in search_functions(config, "codfather fx voyant")] == [r.event for r in outputs]
    clicks = search_functions(config, "loop roll clic")
    assert clicks and {r.event for r in clicks} == {"click"}
    assert len(search_functions(config, "loop roll appui")) == len(clicks)
