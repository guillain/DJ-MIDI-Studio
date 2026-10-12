import random
import time

import pytest

from djmidi.library.playlist import (
    PathResult,
    PlaylistTrack,
    bpm_bucket,
    build_playlist_draft,
    build_playlist_path,
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


# --- path mode (issue #191) -------------------------------------------------


def _synthetic(count: int, seed: int = 191) -> list[PlaylistTrack]:
    rng = random.Random(seed)
    categories = ["Tek%%Tribe", "Tek%%HardTek", "Electro%%Dub", None]
    tracks = []
    for index in range(count):
        number = rng.randint(1, 12)
        letter = rng.choice("AB")
        tracks.append(
            PlaylistTrack(
                identifier=f"/t{index:05d}.mp3",
                category=rng.choice(categories),
                bpm=round(rng.uniform(80.0, 180.0), 1),
                camelot_key=f"{number}{letter}",
            )
        )
    return tracks


def _assert_valid_path(result: PathResult, tolerance_pct: float = 6.0) -> None:
    for previous, current in zip(result.path, result.path[1:], strict=False):
        assert is_bpm_compatible(previous.bpm, current.bpm, tolerance_pct), (previous, current)
        assert is_camelot_compatible(previous.camelot_key, current.camelot_key), (previous, current)


def test_path_every_adjacent_pair_is_compatible_and_rises():
    result = build_playlist_path(_synthetic(400), direction="up")
    _assert_valid_path(result)
    bpms = [track.bpm for track in result.path]
    assert bpms == sorted(bpms)
    assert len(result.path) > 50


def test_path_down_never_rises_and_starts_from_the_fastest():
    tracks = _synthetic(400)
    result = build_playlist_path(tracks, direction="down")
    _assert_valid_path(result)
    bpms = [track.bpm for track in result.path]
    assert bpms == sorted(bpms, reverse=True)
    assert result.path[0].bpm == max(track.bpm for track in tracks)


def test_path_flat_is_compatible():
    result = build_playlist_path(_synthetic(400), direction="flat")
    _assert_valid_path(result)
    assert len(result.path) > 50


def test_path_is_deterministic():
    tracks = _synthetic(300)
    first = build_playlist_path(tracks, direction="up")
    second = build_playlist_path(list(tracks), direction="up")
    assert first == second


def test_path_reports_every_unplaced_track_as_leftover():
    tracks = [
        PlaylistTrack("/a.mp3", "Tek%%Tribe", 170.0, "8A"),
        PlaylistTrack("/b.mp3", "Tek%%Tribe", 172.0, "9A"),
        PlaylistTrack("/c.mp3", "Tek%%Tribe", 174.0, "3B"),  # incompatible key
        PlaylistTrack("/d.mp3", "Electro%%Dub", 80.0, "8A"),  # unreachable BPM
        PlaylistTrack("/e.mp3", "Tek%%Tribe", None, "8A"),  # no BPM
        PlaylistTrack("/f.mp3", "Tek%%Tribe", 171.0, None),  # no key
    ]
    result = build_playlist_path(tracks, start="/a.mp3")
    assert [track.identifier for track in result.path] == ["/a.mp3", "/b.mp3"]
    assert {track.identifier for track in result.leftovers} == {"/c.mp3", "/d.mp3", "/e.mp3", "/f.mp3"}
    assert len(result.path) + len(result.leftovers) == len(tracks)


def test_path_prefers_same_key_on_equal_bpm_moves():
    tracks = [
        PlaylistTrack("/start.mp3", "Tek%%Tribe", 170.0, "8A"),
        PlaylistTrack("/other-key.mp3", "Tek%%Tribe", 171.0, "9A"),
        PlaylistTrack("/same-key.mp3", "Tek%%Tribe", 171.0, "8A"),
    ]
    result = build_playlist_path(tracks, start="/start.mp3")
    assert [track.identifier for track in result.path] == ["/start.mp3", "/same-key.mp3", "/other-key.mp3"]


def test_path_lookahead_avoids_a_dead_end():
    # Greedy would take the cheaper relative-key move to /trap (from which
    # nothing follows) and strand /far; the beam sees /trap dead-ends.
    tracks = [
        PlaylistTrack("/start.mp3", None, 100.0, "8A"),
        PlaylistTrack("/trap.mp3", None, 101.0, "8B"),
        PlaylistTrack("/far.mp3", None, 104.0, "9A"),
        PlaylistTrack("/end.mp3", None, 105.0, "10A"),
    ]
    result = build_playlist_path(tracks, start="/start.mp3")
    assert [track.identifier for track in result.path] == ["/start.mp3", "/far.mp3", "/end.mp3"]
    assert [track.identifier for track in result.leftovers] == ["/trap.mp3"]


def test_path_start_and_max_length_and_errors():
    tracks = _synthetic(200)
    result = build_playlist_path(tracks, start=tracks[10].identifier, max_length=5)
    assert result.path[0] == tracks[10]
    assert len(result.path) == 5
    assert len(result.leftovers) == len(tracks) - 5
    with pytest.raises(ValueError):
        build_playlist_path(tracks, start="/nope.mp3")
    with pytest.raises(ValueError):
        build_playlist_path(tracks, direction="sideways")
    assert build_playlist_path([]) == PathResult(path=[], leftovers=[])


def test_path_is_fast_on_a_few_thousand_tracks():
    tracks = _synthetic(3000)
    began = time.perf_counter()
    result = build_playlist_path(tracks, direction="flat")
    elapsed = time.perf_counter() - began
    _assert_valid_path(result)
    assert len(result.path) + len(result.leftovers) == 3000
    assert elapsed < 2.0, elapsed
