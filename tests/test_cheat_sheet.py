"""Qt-free cheat-sheet resolution (issue #182), against the real fixture."""

from pathlib import Path

from djmidi.gui import cheat_sheet as cs
from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _config() -> MidiConfig:
    return parse_file(FIXTURE)


def test_function_text_and_deck_label():
    assert cs.function_text("auto_loop_specific_length", "8") == "Auto loop · slot 8"
    # Unknown tags print raw.
    assert cs.function_text("cue_set", "2") == "cue_set · slot 2"
    assert cs.function_text("play", "(none)") == "play"
    assert cs.function_text("play", "") == "play"
    assert cs.deck_label("0") == "D1"
    assert cs.deck_label("3") == "D4"
    assert cs.deck_label("(none)") == ""


def test_format_functions_groups_deck_layers():
    lines = [("D1", "play"), ("D3", "play"), ("D1", "cue"), ("", "browse")]
    assert cs.format_functions(lines) == ["play (D1, D3)", "cue (D1)", "browse"]
    assert cs.format_functions([("D2", "x")], "SHIFT: ") == ["SHIFT: x (D2)"]


def test_function_index_collapses_the_10x_duplicates():
    index = cs.build_function_index(_config())
    # 64 distinct triggers in the real file, each bound to one function.
    assert len(index) == 64
    assert all(len(lines) == 1 for lines in index.values())


def test_function_index_ignores_output_elements():
    output_only = Control(
        channel="1",
        event_type="Note On",
        control="5",
        userios=[UserIO(event="output", mappings=[MappingElement(tag="play", deck_id="0")])],
    )
    assert cs.build_function_index(MidiConfig(controls=[output_only])) == {}


def test_candidate_controllers_ranks_by_resolved_triggers():
    ranked = dict(cs.candidate_controllers(_config()))
    assert ranked["DDJ-XP2"] == 64
    assert ranked["XDJ-XZ"] == 16
    assert "Korg nanoPAD2" not in ranked
    restricted = cs.candidate_controllers(_config(), ["XDJ-XZ", "Korg nanoPAD2"])
    assert restricted == [("XDJ-XZ", 16)]


def test_pad_banks_follow_the_catalog_names():
    assert cs.pad_banks("DDJ-XP2")[:2] == ["(PAD MODE 1)", "(PAD MODE 2)"]
    assert "(EXTENSION1 mode)" in cs.pad_banks("XDJ-XZ")


def test_marker_variants_respect_the_physical_side():
    left = {v.name for v in cs.marker_variants("DDJ-XP2", "Pad 1", "(PAD MODE 5)")}
    right = {v.name for v in cs.marker_variants("DDJ-XP2", "Pad 1 (R)", "(PAD MODE 5)")}
    # Both deck layers of the side, plain and SHIFT.
    assert left == {f"Deck {d} Pad 1 (PAD MODE 5){s}" for d in (1, 3) for s in ("", " +SHIFT")}
    assert right == {f"Deck {d} Pad 1 (PAD MODE 5){s}" for d in (2, 4) for s in ("", " +SHIFT")}
    # A bundled DECK entry is narrowed to its own side's channels.
    beat_sync_right = cs.marker_variants("DDJ-XP2", "BEAT SYNC (R)")
    assert beat_sync_right and all(set(v.channels) <= {"2", "4"} for v in beat_sync_right)
    # A combined label answers for both of its triggers.
    pad_mode = {v.name for v in cs.marker_variants("DDJ-XP2", "PAD MODE 1/5")}
    assert any("PAD MODE 1" in name for name in pad_mode) and any("PAD MODE 5" in name for name in pad_mode)
    # Display-only markers have no trigger at all.
    assert cs.marker_variants("XDJ-XZ", "Jog wheel") == []


def test_build_sheets_on_the_real_fixture():
    sheets = cs.build_sheets(_config(), ["DDJ-XP2", "XDJ-XZ", "DDJ-800"])
    assert [(s.controller, s.kind) for s in sheets] == [
        ("DDJ-XP2", "photo"),
        ("XDJ-XZ", "photo"),
        ("DDJ-800", "table"),
        ("", "table"),
    ]
    xp2, xz, ddj800, glossary = sheets
    assert "PAD MODE 5" in xp2.title
    # Both pad grids, every pad mapped, deck layers merged on one label.
    assert len(xp2.entries) == 32
    pad1 = next(e for e in xp2.entries if e.control == "Pad 1")
    assert pad1.functions == ("Codfather ST · slot 0 (D1, D3)",)
    assert next(e for e in xp2.entries if e.control == "Pad 1 (R)").functions == ("Codfather ST · slot 0 (D2, D4)",)
    assert all(e.geometry is not None for e in xp2.entries)
    # The XDJ-XZ binds a SHIFT layer on the same pads.
    xz_pad1 = next(e for e in xz.entries if e.control == "Pad 1")
    assert xz_pad1.functions == ("Codfather ST · slot 0 (D1)", "SHIFT: Auto loop · slot 6 (D1)")
    # Unmapped markers stay drawable as outlines.
    assert xz.unmapped
    # No geometry: every mapped variant in a table (64 triggers).
    assert len(ddj800.entries) == 64
    assert all(e.geometry is None for e in ddj800.entries)
    # Paper has no tooltip: a last page maps each readable name to its tag.
    assert glossary.title == cs.GLOSSARY_TITLE
    assert ("Codfather ST", ("Serato tag: codfather_st",)) in [(e.control, e.functions) for e in glossary.entries]


def test_a_controller_with_nothing_mapped_still_gets_a_page():
    sheets = cs.build_sheets(_config(), ["Korg nanoPAD2", "Hercules DJControl Inpulse 500"])
    assert [s.kind for s in sheets] == ["photo", "table", "table"]
    assert all(not s.entries for s in sheets[:2])
    assert sheets[2].title == cs.GLOSSARY_TITLE


def test_one_page_per_mapped_pad_bank_and_a_table_for_unshown_controls():
    # Pad 1 of DDJ-XP2 deck 1 in PAD MODE 1 (note 0, ch 8) and PAD MODE 2
    # (note 16): two banks in use -> two photo pages, the second pads only.
    def control(note: str, tag: str) -> Control:
        return Control(
            channel="8",
            event_type="Note On",
            control=note,
            userios=[UserIO(event="click", mappings=[MappingElement(tag=tag, deck_id="0")])],
        )

    from djmidi import catalog

    hits = {h.name for h in catalog.lookup("8", "Note On", "0")} | {h.name for h in catalog.lookup("8", "Note On", "16")}
    assert {"Deck 1 Pad 1 (PAD MODE 1)", "Deck 1 Pad 1 (PAD MODE 2)"} <= hits
    config = MidiConfig(controls=[control("0", "cue_set"), control("16", "loop_roll")])
    sheets = cs.build_sheets(config, ["DDJ-XP2"])
    assert [s.title for s in sheets] == ["DDJ-XP2 — pads PAD MODE 1", "DDJ-XP2 — pads PAD MODE 2"]
    assert [e.functions for e in sheets[0].entries] == [("cue_set (D1)",)]
    assert [e.functions for e in sheets[1].entries] == [("loop_roll (D1)",)]
