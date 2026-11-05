from __future__ import annotations

import pytest

from djmidi.library import set_prep
from djmidi.library.db import LibraryDB
from djmidi.library.metadata import TrackMetadata
from djmidi.library.set_prep import SetDraft, SetTrack
from djmidi.library.workspace import LibraryRow


def _track(path: str, bpm: float | None = None, key: str | None = None, energy: int | None = None) -> SetTrack:
    return SetTrack(path=path, bpm=bpm, camelot_key=key, energy=energy)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("6", 6), ("Energy 7", 7), ("10", 10), ("0", None), ("11", None), ("", None), (None, None), ("high", None)],
)
def test_parse_energy(text, expected):
    assert set_prep.parse_energy(text) == expected


def test_compatible_transition_is_ok():
    transition = set_prep.analyze_transition(0, _track("a", 140, "8A"), _track("b", 142, "9A"))
    assert transition.status == set_prep.STATUS_OK
    assert transition.issues == ()
    assert transition.bpm_change_pct == pytest.approx(100 * 2 / 140)


def test_bpm_jump_past_tolerance_is_incompatible():
    transition = set_prep.analyze_transition(0, _track("a", 140, "8A"), _track("b", 160, "8A"))
    assert transition.status == set_prep.STATUS_INCOMPATIBLE
    assert transition.bpm_ok is False and transition.key_ok is True
    assert transition.issues[0].startswith("BPM jump +14.3 %")
    # A wider tolerance accepts the same jump.
    assert set_prep.analyze_transition(0, _track("a", 140, "8A"), _track("b", 160, "8A"), 15).status == "ok"


def test_key_clash_is_incompatible():
    transition = set_prep.analyze_transition(0, _track("a", 140, "8A"), _track("b", 140, "3B"))
    assert transition.status == set_prep.STATUS_INCOMPATIBLE
    assert transition.issues == ("Key clash 8A → 3B",)


def test_missing_values_are_unknown_not_incompatible():
    transition = set_prep.analyze_transition(0, _track("a", None, "8A"), _track("b", 140, None))
    assert transition.status == set_prep.STATUS_UNKNOWN
    assert transition.issues == ("BPM unknown", "Key unknown")
    # A known clash still wins over a missing value.
    clash = set_prep.analyze_transition(0, _track("a", None, "8A"), _track("b", 140, "2B"))
    assert clash.status == set_prep.STATUS_INCOMPATIBLE


def test_analyze_set_and_summary():
    tracks = [_track("a", 140, "8A"), _track("b", 141, "8B"), _track("c", 175, "8B"), _track("d")]
    transitions = set_prep.analyze_set(tracks)
    assert [t.index for t in transitions] == [0, 1, 2]
    assert [t.status for t in transitions] == ["ok", "incompatible", "unknown"]
    summary = set_prep.summarize(tracks, transitions)
    assert (summary.tracks, summary.incompatible, summary.unknown) == (4, 1, 1)
    assert summary.text == "4 track(s) · 1 incompatible transition(s) · 1 unchecked (missing BPM/key)"
    assert set_prep.analyze_set([_track("a")]) == []
    assert set_prep.summarize([], []).text == "0 track(s)"


def test_resolve_set_tracks_reads_rows_and_flags_unknown_paths():
    row = LibraryRow(
        track_id=1,
        path="/m/a.mp3",
        missing=False,
        metadata=TrackMetadata(title="Alpha", artist="Zed", bpm=140.0, key="Am", energy="7"),
        camelot_key="8A",
        category=None,
    )
    known, unknown = set_prep.resolve_set_tracks(["/m/a.mp3", "/elsewhere/b.mp3"], {row.path: row})
    assert known == SetTrack("/m/a.mp3", "Alpha", "Zed", 140.0, "8A", 7, True)
    assert known.label == "Zed — Alpha"
    assert unknown == SetTrack("/elsewhere/b.mp3", indexed=False)
    assert unknown.label == "b.mp3"


def test_resolve_set_tracks_carries_duration_from_the_row():
    row = LibraryRow(
        track_id=1, path="/m/a.mp3", missing=False,
        metadata=TrackMetadata(title="Alpha", duration=185.0), camelot_key=None, category=None,
    )  # fmt: skip
    known, = set_prep.resolve_set_tracks(["/m/a.mp3"], {row.path: row})
    assert known.duration == pytest.approx(185.0)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00"), (59, "0:59"), (60, "1:00"), (185, "3:05"), (3599, "59:59"), (3600, "1:00:00"), (3725, "1:02:05")],
)
def test_format_duration(seconds, expected):
    assert set_prep.format_duration(seconds) == expected


def test_total_duration_known_partial_and_none():
    assert set_prep.total_duration([_track("a")]) == (0, False)
    assert set_prep.total_duration([]) == (0, False)
    known = SetTrack("a", duration=100.0)
    also_known = SetTrack("b", duration=50.0)
    unknown = SetTrack("c")
    assert set_prep.total_duration([known, also_known]) == (150.0, True)
    assert set_prep.total_duration([known, unknown]) == (100.0, False)


def test_summary_describes_total_duration():
    known = SetTrack("a", duration=65.0)
    also_known = SetTrack("b", duration=55.0)
    unknown = SetTrack("c")
    summary = set_prep.summarize([known, also_known], set_prep.analyze_set([known, also_known]))
    assert summary.text.endswith("2:00 total")
    approx = set_prep.summarize([known, unknown], set_prep.analyze_set([known, unknown]))
    assert approx.text.endswith("1:05+ total (some durations unknown)")
    assert set_prep.summarize([], []).text == "0 track(s)"


def test_insert_paths_skips_duplicates_and_clamps_index():
    assert set_prep.insert_paths(["a", "b"], ["c", "a", "c", "d"], 1) == ["a", "c", "d", "b"]
    assert set_prep.insert_paths(["a"], ["b"]) == ["a", "b"]
    assert set_prep.insert_paths(["a"], ["b"], 99) == ["a", "b"]
    assert set_prep.insert_paths(["a"], ["b"], -3) == ["b", "a"]


def test_move_rows_moves_a_block_and_clamps():
    order = ["a", "b", "c", "d", "e"]
    assert set_prep.move_rows(order, [1, 2], 1) == (["a", "d", "b", "c", "e"], [2, 3])
    assert set_prep.move_rows(order, [1, 2], -1) == (["b", "c", "a", "d", "e"], [0, 1])
    assert set_prep.move_rows(order, [0], -1) == (order, [0])
    assert set_prep.move_rows(order, [4], 1) == (order, [4])
    assert set_prep.move_rows(order, [], 1) == (order, [])
    assert set_prep.remove_rows(order, [0, 3]) == ["b", "c", "e"]


def test_draft_roundtrip_and_bad_values():
    with LibraryDB() as db:
        assert set_prep.load_set_draft(db) == SetDraft()
        set_prep.save_set_draft(db, SetDraft(("/a", "/b"), 8.0))
        assert set_prep.load_set_draft(db) == SetDraft(("/a", "/b"), 8.0)
        db.set_setting("set_draft", {"paths": ["/a", 3, "", "/a"], "bpm_tolerance_pct": "x"})
        assert set_prep.load_set_draft(db) == SetDraft(("/a",), set_prep.DEFAULT_BPM_TOLERANCE_PCT)
        db.set_setting("set_draft", {"paths": "nope", "bpm_tolerance_pct": 500})
        assert set_prep.load_set_draft(db) == SetDraft((), 20.0)
        db.set_setting("set_draft", ["junk"])
        assert set_prep.load_set_draft(db) == SetDraft()


def test_propose_order_chains_compatible_tracks_and_keeps_the_rest():
    from djmidi.library.set_prep import propose_order

    tracks = [
        SetTrack("/c", bpm=128.0, camelot_key="9A"),
        SetTrack("/a", bpm=124.0, camelot_key="8A"),
        SetTrack("/x"),  # no BPM/key: goes last, kept
        SetTrack("/b", bpm=126.0, camelot_key="8A"),
        SetTrack("/z", bpm=170.0, camelot_key="2B"),  # unreachable
    ]
    proposal = propose_order(tracks, 6.0, "up", keep_opener=False)
    assert proposal.order == ("/a", "/b", "/c", "/x", "/z") and proposal.chained == 3
    assert sorted(proposal.order) == sorted(track.path for track in tracks)
    assert proposal.improves()
    kept = propose_order(tracks, 6.0, "flat", keep_opener=True)
    assert kept.order[0] == "/c" and kept.order[-2:] == ("/x", "/z")
    nothing = propose_order([SetTrack("/x"), SetTrack("/y")])
    assert nothing.order == ("/x", "/y") and nothing.chained == 0 and not nothing.improves()


def test_generate_set_from_library_stops_at_the_target_duration():
    from djmidi.library.set_prep import generate_set_from_library

    library = [
        SetTrack("/a", bpm=124.0, camelot_key="8A", duration=60.0),
        SetTrack("/b", bpm=126.0, camelot_key="8A", duration=60.0),
        SetTrack("/c", bpm=128.0, camelot_key="9A", duration=60.0),
        SetTrack("/d", bpm=130.0, camelot_key="9A", duration=60.0),
    ]
    generated = generate_set_from_library(library, target_duration_seconds=125.0, direction="up")
    # Stops as soon as the running total reaches the target -- 3 tracks (180s), not 2 (120s) or all 4.
    assert generated.tracks == ("/a", "/b", "/c")
    assert generated.duration_seconds == pytest.approx(180.0)
    assert generated.duration_known is True
    assert generated.reached_target is True


def test_generate_set_from_library_with_no_target_chains_everything_reachable():
    from djmidi.library.set_prep import generate_set_from_library

    library = [
        SetTrack("/a", bpm=124.0, camelot_key="8A"),
        SetTrack("/b", bpm=126.0, camelot_key="8A"),
        SetTrack("/unreachable", bpm=170.0, camelot_key="2B"),
        SetTrack("/no_tags"),
    ]
    generated = generate_set_from_library(library, target_duration_seconds=None, direction="up")
    assert generated.tracks == ("/a", "/b")
    assert generated.duration_seconds == 0 and generated.duration_known is False
    assert generated.reached_target is False


def test_generate_set_from_library_excludes_paths_and_respects_start():
    from djmidi.library.set_prep import generate_set_from_library

    library = [
        SetTrack("/a", bpm=124.0, camelot_key="8A", duration=60.0),
        SetTrack("/b", bpm=126.0, camelot_key="8A", duration=60.0),
        SetTrack("/c", bpm=128.0, camelot_key="9A", duration=60.0),
    ]
    generated = generate_set_from_library(library, exclude={"/a"}, direction="up")
    assert "/a" not in generated.tracks
    started = generate_set_from_library(library, start="/c", direction="flat")
    assert started.tracks[0] == "/c"


def test_generate_set_from_library_skips_an_isolated_default_opener():
    """The engine starts on the slowest track by default; when that one has
    no compatible neighbour, the set must still come from the long chain the
    library holds, not stop at one track (found checking #404 in the app)."""
    from djmidi.library.set_prep import generate_set_from_library

    library = [
        SetTrack("/dub", bpm=140.0, camelot_key="10B", duration=360.0),
        SetTrack("/a", bpm=174.0, camelot_key="8A", duration=300.0),
        SetTrack("/b", bpm=172.0, camelot_key="9A", duration=300.0),
        SetTrack("/c", bpm=174.0, camelot_key="10A", duration=300.0),
        SetTrack("/d", bpm=174.0, camelot_key="10A", duration=300.0),
    ]
    generated = generate_set_from_library(library, target_duration_seconds=1200.0, direction="flat")
    assert len(generated.tracks) == 4 and "/dub" not in generated.tracks
    assert generated.reached_target is True
    # No target: the longest chain still wins over the isolated default.
    assert len(generate_set_from_library(library, direction="flat").tracks) == 4


def test_generate_set_from_library_empty_pool_is_an_empty_set():
    from djmidi.library.set_prep import generate_set_from_library

    assert generate_set_from_library([SetTrack("/x")]).tracks == ()
