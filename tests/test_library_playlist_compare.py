from __future__ import annotations

import unicodedata

from djmidi.library.playlist_compare import compare_playlists, path_key


def _paths(comparison_tracks):
    return [track.path for track in comparison_tracks]


def test_identical_playlists():
    result = compare_playlists(["/m/a.mp3", "/m/b.mp3"], ["/m/a.mp3", "/m/b.mp3"])
    assert result.identical and result.same_tracks
    assert result.moved == () and len(result.in_both) == 2


def test_tracks_only_on_each_side_with_positions():
    result = compare_playlists(["/m/a.mp3", "/m/b.mp3", "/m/c.mp3"], ["/m/b.mp3", "/m/d.mp3"])
    assert [(t.path, t.app_position, t.other_position) for t in result.only_in_app] == [
        ("/m/a.mp3", 1, None),
        ("/m/c.mp3", 3, None),
    ]
    assert [(t.path, t.app_position, t.other_position) for t in result.only_in_other] == [("/m/d.mp3", None, 2)]
    assert [(t.app_position, t.other_position) for t in result.in_both] == [(2, 1)]
    # A missing or extra track never makes the rest look reordered.
    assert result.moved == ()
    assert not result.same_tracks and not result.identical


def test_one_moved_track_is_the_only_one_flagged():
    app = ["/m/a", "/m/b", "/m/c", "/m/d", "/m/e"]
    other = ["/m/b", "/m/c", "/m/d", "/m/e", "/m/a"]
    result = compare_playlists(app, other)
    assert result.same_tracks and not result.identical
    assert [(t.path, t.app_position, t.other_position) for t in result.moved] == [("/m/a", 1, 5)]


def test_swap_flags_one_of_the_pair_and_reversal_flags_all_but_one():
    assert len(compare_playlists(["/a", "/b", "/c"], ["/b", "/a", "/c"]).moved) == 1
    assert len(compare_playlists(["/a", "/b", "/c", "/d"], ["/d", "/c", "/b", "/a"]).moved) == 3


def test_duplicates_match_occurrence_by_occurrence():
    result = compare_playlists(["/a", "/b", "/a"], ["/a", "/b"])
    assert [(t.path, t.app_position) for t in result.only_in_app] == [("/a", 3)]
    assert result.only_in_other == () and result.moved == ()


def test_unicode_and_separator_normalization():
    nfd = unicodedata.normalize("NFD", "/m/Beyoncé.mp3")
    nfc = unicodedata.normalize("NFC", "/m/Beyoncé.mp3")
    assert nfd != nfc
    assert compare_playlists([nfc], [nfd]).identical
    assert compare_playlists(["/m//x/./a.mp3"], ["/m/x/a.mp3"]).identical
    # Case is kept: two files may differ only by case on a case-sensitive volume.
    assert path_key("/m/A.mp3") != path_key("/m/a.mp3")


def test_empty_sides():
    assert compare_playlists([], []).identical
    result = compare_playlists([], ["/a"])
    assert _paths(result.only_in_other) == ["/a"] and result.in_both == ()


def test_large_reorder_is_fast_and_minimal():
    app = [f"/m/{i}" for i in range(5000)]
    other = app[1:] + app[:1]
    result = compare_playlists(app, other)
    assert _paths(result.moved) == ["/m/0"]
