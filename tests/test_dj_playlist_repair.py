"""Finding the tracks missing from Serato crates and Traktor playlists, and
the one file that replaces each (user request 2026-11-21). Writing is
`dj_playlists` (issue #458), tested on its own."""

from pathlib import Path

from djmidi.library import dj_playlist_repair as r
from djmidi.library import serato_library as s


def _setup(tmp_path):
    crates = tmp_path / "Music" / "_Serato_" / "Subcrates"
    crates.mkdir(parents=True)
    crate = crates / "Techno%%Peak.crate"
    root = Path(crate.resolve().anchor)
    music = tmp_path / "lib"
    music.mkdir()
    kept, found, tagged = music / "kept.mp3", music / "moved.mp3", music / "renamed.mp3"
    for f in (kept, found, tagged):
        f.write_bytes(b"x")
    gone = [str((tmp_path / "old" / n).resolve()) for n in ("dup.mp3", "moved.mp3", "lost.mp3", "nowhere.mp3")]
    s.write_crate_file(crate, [str(Path(g).relative_to(root)) for g in gone])
    return crate, gone, kept, found, tagged


def test_missing_entries_are_found_with_their_crate(tmp_path):
    crate, gone, *_ = _setup(tmp_path)
    dangling = r.find_dangling(r.serato_crates(tmp_path), None)
    assert [(d.playlist, d.path) for d in dangling] == [("Techno › Peak", g) for g in gone]
    assert r.find_dangling([crate], None, exists=lambda _p: True) == []


def test_replacements_kept_copy_then_unique_name_then_tags(tmp_path):
    _crate, gone, kept, found, tagged = _setup(tmp_path)
    dangling = r.find_dangling(r.serato_crates(tmp_path), None)
    library = [
        r.LibraryTrack(str(kept), "Dup", "X"),
        r.LibraryTrack(str(found), "Moved", "Y"),
        r.LibraryTrack(str(tagged), "Lost", "Z"),
        r.LibraryTrack(gone[2], "Lost", "Z", missing=True),
    ]
    plan = r.find_fixes(dangling, library, kept_for={gone[0]: str(kept)})
    assert [(f.new_path, f.how) for f in plan.fixes] == [
        (str(kept), r.HOW_KEPT), (str(found), r.HOW_NAME), (str(tagged), r.HOW_TAGS)
    ]
    assert [why for _e, why in plan.unresolved] == ["not found in your library"]


def test_two_candidates_or_a_vanished_replacement_are_not_guessed(tmp_path):
    _crate, gone, kept, *_ = _setup(tmp_path)
    twin = tmp_path / "other" / "moved.mp3"
    twin.parent.mkdir()
    twin.write_bytes(b"x")
    dangling = r.find_dangling(r.serato_crates(tmp_path), None)
    library = [r.LibraryTrack(str(tmp_path / "lib" / "moved.mp3"), None, None), r.LibraryTrack(str(twin), None, None)]
    chained = {gone[0]: str(tmp_path / "renamed-then-trashed.mp3")}
    plan = r.find_fixes(dangling, library, kept_for=chained)
    why = {e.path: w for e, w in plan.unresolved}
    assert why[gone[1]] == "several files could be it"
    assert why[gone[0]].startswith("its replacement is gone too")
    chained[str(tmp_path / "renamed-then-trashed.mp3")] = str(kept)
    plan = r.find_fixes(dangling, library, kept_for=chained)
    assert plan.fixes[0].new_path == str(kept)  # followed rename -> trash
