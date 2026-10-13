"""The Qt-free command palette ranking (issue #222)."""

from pathlib import Path

from djmidi.command_palette import (
    KIND_ACTION,
    KIND_FUNCTION,
    KIND_TAB,
    KIND_TRACK,
    TRACK_MIN_QUERY,
    PaletteEntry,
    PaletteIndex,
    clean_menu_text,
    score_entry,
    tokenize,
    track_entry,
)
from djmidi.function_search import index_functions
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _actions() -> list[PaletteEntry]:
    return [
        PaletteEntry(KIND_ACTION, "Open Mapping", detail="File", keywords="File", payload="open"),
        PaletteEntry(KIND_ACTION, "Save Mapping", detail="File", keywords="File", payload="save"),
        PaletteEntry(KIND_ACTION, "Cheat Sheet (PDF)", detail="File › Export", keywords="File Export", payload="cs"),
        PaletteEntry(KIND_ACTION, "Validate", detail="Edit", keywords="Edit", payload="validate"),
        PaletteEntry(KIND_TAB, "Music Library", payload=6),
        PaletteEntry(KIND_TAB, "By Channel", payload=3),
    ]


def test_clean_menu_text_drops_mnemonics_and_ellipsis():
    assert clean_menu_text("&Open Mapping...") == "Open Mapping"
    assert clean_menu_text("New Controller Emulator…") == "New Controller Emulator"
    assert clean_menu_text("Rock && Roll") == "Rock & Roll"
    assert clean_menu_text("Co&mpare Mapping With...") == "Compare Mapping With"


def test_exact_word_beats_prefix_beats_substring_beats_subsequence():
    entry = PaletteEntry(KIND_ACTION, "Cheat Sheet")
    exact = score_entry(entry, ["sheet"])
    prefix = score_entry(entry, ["she"])
    substring = score_entry(entry, ["eet"])
    subsequence = score_entry(entry, ["cs"])
    assert exact > prefix > substring > subsequence > 0
    assert score_entry(entry, ["zz"]) is None
    assert score_entry(entry, ["cs"], subsequence=False) is None


def test_every_token_must_match():
    entry = PaletteEntry(KIND_ACTION, "Open Mapping")
    assert score_entry(entry, ["open", "map"]) is not None
    assert score_entry(entry, ["open", "banana"]) is None
    assert score_entry(entry, []) is None


def test_keywords_match_below_the_title():
    in_title = PaletteEntry(KIND_ACTION, "Export Log")
    in_keywords = PaletteEntry(KIND_ACTION, "Cheat Sheet", keywords="File Export")
    assert score_entry(in_title, ["export"]) > score_entry(in_keywords, ["export"]) > 0


def test_empty_query_lists_actions_and_tabs_in_order():
    index = PaletteIndex(_actions(), tracks=[track_entry("/m/a.mp3", "Save Me", "Someone")])
    results = index.search("")
    assert [entry.payload for entry in results] == ["open", "save", "cs", "validate", 6, 3]
    assert index.search("   ", limit=2) == results[:2]


def test_ranking_puts_the_best_match_first():
    index = PaletteIndex(_actions())
    assert index.search("save")[0].payload == "save"
    assert index.search("opmap")[0].payload == "open"
    assert index.search("cheat")[0].payload == "cs"
    assert index.search("music")[0].kind == KIND_TAB
    assert index.search("export")[0].payload == "cs"
    assert index.search("nothing here") == []


def test_actions_win_ties_over_tracks():
    track = track_entry("/m/save.mp3", "Save", None)
    index = PaletteIndex(_actions(), tracks=[track])
    results = index.search("save")
    assert [entry.kind for entry in results[:2]] == [KIND_ACTION, KIND_TRACK]


def test_tracks_need_a_minimum_query_length():
    index = PaletteIndex([], tracks=[track_entry("/m/x.mp3", "Xylophone", "X Artist")])
    assert index.search("x"[:TRACK_MIN_QUERY - 1]) == []
    assert index.search("xy")[0].kind == KIND_TRACK


def test_track_entry_titles_and_keywords():
    tagged = track_entry("/m/Tek/01 - tune.mp3", "Tune", "Artist", "Album", detail="140 BPM", payload=7)
    assert tagged.title == "Artist – Tune"
    assert tagged.detail == "140 BPM"
    assert tagged.payload == 7
    assert score_entry(tagged, ["album"]) is not None
    untagged = track_entry("/m/Tek/01 - tune.mp3", None, None)
    assert untagged.title == "01 - tune.mp3"
    assert untagged.payload == "/m/Tek/01 - tune.mp3"
    assert untagged.detail == "/m/Tek/01 - tune.mp3"


def test_functions_reuse_function_search():
    functions = index_functions(parse_file(FIXTURE))
    index = PaletteIndex(_actions(), functions)
    results = index.search("loop roll deck 2 slot 3")
    assert len(results) == 1
    entry = results[0]
    assert entry.kind == KIND_FUNCTION
    assert entry.title == "Loop roll"
    assert entry.payload.tag == "auto_loop_roll_specific_length"
    assert "Deck 2 · Slot 3" in entry.detail
    # The raw tag is searchable through the function search too.
    assert any(r.kind == KIND_FUNCTION for r in index.search("auto_loop_roll"))


def test_tokenize_is_case_and_punctuation_insensitive():
    assert tokenize("Cheat Sheet (PDF)…") == ["cheat", "sheet", "pdf"]
