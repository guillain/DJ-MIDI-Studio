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
