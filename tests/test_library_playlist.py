from djmidi.library.playlist import (
    PlaylistTrack,
    bpm_bucket,
    build_playlist_draft,
    compatibility_score,
    find_compatible_tracks,
    is_bpm_compatible,
    is_camelot_compatible,
)


def test_camelot_same_key_is_compatible():
    assert is_camelot_compatible("8A", "8A") is True


def test_camelot_adjacent_number_same_letter_is_compatible():
    assert is_camelot_compatible("8A", "9A") is True
    assert is_camelot_compatible("8A", "7A") is True
    assert is_camelot_compatible("1A", "12A") is True  # wraps around the wheel


def test_camelot_same_number_other_letter_is_compatible():
    assert is_camelot_compatible("8A", "8B") is True


def test_camelot_unrelated_key_is_incompatible():
    assert is_camelot_compatible("8A", "3B") is False


def test_camelot_invalid_key_is_incompatible():
    assert is_camelot_compatible("8A", "not-a-key") is False
    assert is_camelot_compatible("13A", "8A") is False


def test_bpm_compatible_within_tolerance():
    assert is_bpm_compatible(140.0, 144.0, tolerance_pct=6.0) is True


def test_bpm_incompatible_outside_tolerance():
    assert is_bpm_compatible(140.0, 200.0, tolerance_pct=6.0) is False


def test_bpm_incompatible_with_non_positive_values():
    assert is_bpm_compatible(0.0, 140.0) is False
    assert is_bpm_compatible(140.0, -1.0) is False


def test_compatibility_score_none_when_bpm_missing():
    seed = PlaylistTrack("seed", bpm=None, camelot_key="8A")
    candidate = PlaylistTrack("candidate", bpm=140.0, camelot_key="8A")
    assert compatibility_score(seed, candidate) is None


def test_compatibility_score_none_when_key_incompatible():
    seed = PlaylistTrack("seed", bpm=140.0, camelot_key="8A")
    candidate = PlaylistTrack("candidate", bpm=141.0, camelot_key="3B")
    assert compatibility_score(seed, candidate) is None


def test_compatibility_score_allows_missing_key_on_either_side():
    seed = PlaylistTrack("seed", bpm=140.0, camelot_key=None)
    candidate = PlaylistTrack("candidate", bpm=141.0, camelot_key="8A")
    assert compatibility_score(seed, candidate) == 1.0


def test_compatibility_score_respects_same_category_only():
    seed = PlaylistTrack("seed", category="Tek%%HardTek", bpm=140.0, camelot_key="8A")
    candidate = PlaylistTrack("candidate", category="Electro%%Dub", bpm=141.0, camelot_key="8A")
    assert compatibility_score(seed, candidate, same_category_only=True) is None
    assert compatibility_score(seed, candidate, same_category_only=False) == 1.0


def test_find_compatible_tracks_sorts_by_closeness_and_excludes_seed():
    seed = PlaylistTrack("seed", bpm=140.0, camelot_key="8A")
    close = PlaylistTrack("close", bpm=141.0, camelot_key="8A")
    closer = PlaylistTrack("closer", bpm=140.5, camelot_key="8A")
    incompatible = PlaylistTrack("incompatible", bpm=200.0, camelot_key="8A")

    result = find_compatible_tracks(seed, [seed, close, closer, incompatible])

    assert result == [closer, close]


def test_bpm_bucket_groups_close_values_together():
    assert bpm_bucket(140.5, width=4.0) == bpm_bucket(143.8, width=4.0)
    assert bpm_bucket(140.5, width=4.0) != bpm_bucket(150.0, width=4.0)


def test_build_playlist_draft_orders_by_category_then_bpm_bucket_then_key():
    tracks = [
        PlaylistTrack("t1", category="Tek%%HardTek", bpm=180.0, camelot_key="9A"),
        PlaylistTrack("t2", category="Tek%%HardTek", bpm=181.0, camelot_key="3A"),
        PlaylistTrack("t3", category="Tek%%HardTek", bpm=190.0, camelot_key="1A"),
        PlaylistTrack("t4", category="Electro%%Dub", bpm=90.0, camelot_key="5B"),
    ]

    ordered = build_playlist_draft(tracks, bpm_bucket_width=4.0)

    assert [t.identifier for t in ordered] == ["t4", "t2", "t1", "t3"]


def test_build_playlist_draft_sorts_missing_values_last_within_group():
    tracks = [
        PlaylistTrack("with_key", category="Tek%%HardTek", bpm=180.0, camelot_key="1A"),
        PlaylistTrack("no_key", category="Tek%%HardTek", bpm=180.0, camelot_key=None),
        PlaylistTrack("no_category", category=None, bpm=180.0, camelot_key="1A"),
    ]

    ordered = build_playlist_draft(tracks)

    assert [t.identifier for t in ordered] == ["with_key", "no_key", "no_category"]
