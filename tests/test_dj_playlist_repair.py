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


def test_a_file_found_must_still_be_there_and_be_another_file(tmp_path):
    """An index not rescanned still lists the missing file itself as present:
    it is never proposed as its own replacement."""
    _crate, gone, *_ = _setup(tmp_path)
    dangling = r.find_dangling(r.serato_crates(tmp_path), None)
    stale = [r.LibraryTrack(gone[1], "Moved", "Y"), r.LibraryTrack(str(tmp_path / "gone-too" / "lost.mp3"), "L", "Z")]
    plan = r.find_fixes(dangling, stale)
    assert plan.fixes == []
    assert {e.path: w for e, w in plan.unresolved}[gone[1]] == "not found in your library"


def test_two_missing_tracks_never_get_the_same_file_by_a_guess(tmp_path):
    """Two albums' "01 Intro.mp3" are different tracks: the one library file
    of that name replaces neither (the crate would lose one entry)."""
    crates = tmp_path / "Music" / "_Serato_" / "Subcrates"
    crates.mkdir(parents=True)
    crate = crates / "Intros.crate"
    root = Path(crate.resolve().anchor)
    intro = tmp_path / "lib" / "01 Intro.mp3"
    intro.parent.mkdir()
    intro.write_bytes(b"x")
    gone = [str((tmp_path / album / "01 Intro.mp3").resolve()) for album in ("A", "B")]
    s.write_crate_file(crate, [str(Path(g).relative_to(root)) for g in gone])
    plan = r.find_fixes(r.find_dangling([crate], None), [r.LibraryTrack(str(intro), "Intro", "C")])
    assert plan.fixes == []
    assert [w for _e, w in plan.unresolved] == ["another missing track would get the same file"] * 2


def test_paths_compare_whatever_their_unicode_form(tmp_path):
    """A crate spelling "Café" composed (NFC) matches the decomposed (NFD)
    path macOS gave the library, for the kept copy and for `only_paths`."""
    import unicodedata

    crates = tmp_path / "Music" / "_Serato_" / "Subcrates"
    crates.mkdir(parents=True)
    crate = crates / "Accents.crate"
    root = Path(crate.resolve().anchor)
    composed = unicodedata.normalize("NFC", str((tmp_path / "old" / "Café.mp3").resolve()))
    decomposed = unicodedata.normalize("NFD", composed)
    s.write_crate_file(crate, [str(Path(composed).relative_to(root))])
    kept = tmp_path / "kept.mp3"
    kept.write_bytes(b"x")
    dangling = r.find_dangling([crate], None, only_paths={decomposed})
    assert [d.path for d in dangling] == [composed]
    plan = r.find_fixes(dangling, [], kept_for={decomposed: str(kept)})
    assert [(f.new_path, f.how) for f in plan.fixes] == [(str(kept), r.HOW_KEPT)]


def test_only_paths_entries_are_the_only_ones_looked_up(tmp_path):
    crate, gone, *_ = _setup(tmp_path)
    looked: list[str] = []
    dangling = r.find_dangling([crate], None, exists=lambda p: looked.append(p) or False, only_paths={gone[0]})
    assert [d.path for d in dangling] == [gone[0]] and looked == [gone[0]]


def test_a_missing_traktor_track_keeps_its_drive_so_the_entry_is_repointed(tmp_path):
    """traktor_key_to_path puts a file it can't find on the boot disk; the
    repair keeps the drive, so dj_playlists finds the same PRIMARYKEY again."""
    from djmidi.library import dj_playlists

    volumes = tmp_path / "volumes"  # no symlink to "/": no boot volume name
    volumes.mkdir()
    nml = tmp_path / "collection.nml"
    nml.write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<NML VERSION="19"><COLLECTION ENTRIES="1">'
        '<ENTRY TITLE="A" ARTIST="X"><LOCATION DIR="/:Music/:New/:" FILE="a.mp3" VOLUME="Gig Drive" '
        'VOLUMEID="Gig Drive"/></ENTRY></COLLECTION><PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1">'
        '<NODE TYPE="PLAYLIST" NAME="Friday"><PLAYLIST ENTRIES="1" TYPE="LIST" UUID="u"><ENTRY>'
        '<PRIMARYKEY TYPE="TRACK" KEY="Gig Drive/:Music/:Old/:a.mp3"/></ENTRY></PLAYLIST></NODE></SUBNODES></NODE>'
        "</PLAYLISTS></NML>",
        encoding="utf-8",
    )
    new = "/Volumes/Gig Drive/Music/New/a.mp3"
    dangling = r.find_dangling([], nml, exists=lambda p: p == new, volumes_dir=volumes)
    assert [(d.playlist, d.path) for d in dangling] == [("Friday", "/Volumes/Gig Drive/Music/Old/a.mp3")]
    plan = r.find_fixes(dangling, [r.LibraryTrack(new, "A", "X")], exists=lambda p: p == new)
    write = dj_playlists.plan_traktor(nml, [(f.entry.path, f.new_path) for f in plan.fixes], volumes)
    assert [change.replaced for change in write.changes] == [1]
    assert b'KEY="Gig Drive/:Music/:New/:a.mp3"' in write.changes[0].data


def test_a_same_named_file_tagged_as_another_song_is_not_it(tmp_path):
    """Generic rip names ("01.mp3"): the one library 01.mp3 is another
    album's song; the file tagged as the remembered song replaces it."""
    crates = tmp_path / "Music" / "_Serato_" / "Subcrates"
    crates.mkdir(parents=True)
    crate = crates / "Rips.crate"
    root = Path(crate.resolve().anchor)
    gone = str((tmp_path / "old" / "AlbumA" / "01.mp3").resolve())
    s.write_crate_file(crate, [str(Path(gone).relative_to(root))])
    other, song = tmp_path / "lib" / "AlbumB" / "01.mp3", tmp_path / "lib" / "Moved" / "Song A.mp3"
    for f in (other, song):
        f.parent.mkdir(parents=True)
        f.write_bytes(b"x")
    library = [
        r.LibraryTrack(str(other), "Song B", "Artist B"),
        r.LibraryTrack(str(song), "Song A", "Artist A"),
        r.LibraryTrack(gone, "Song A", "Artist A", missing=True),
    ]
    plan = r.find_fixes(r.find_dangling([crate], None), library)
    assert [(f.new_path, f.how) for f in plan.fixes] == [(str(song), r.HOW_TAGS)]


def test_traktor_playlists_sharing_a_name_are_all_looked_at(tmp_path):
    nml = tmp_path / "collection.nml"
    playlist = (
        '<NODE TYPE="PLAYLIST" NAME="Friday"><PLAYLIST ENTRIES="1" TYPE="LIST" UUID="{uuid}"><ENTRY>'
        '<PRIMARYKEY TYPE="TRACK" KEY="/:old{year}/:a.mp3"/></ENTRY></PLAYLIST></NODE>'
    )
    nml.write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<NML VERSION="19"><COLLECTION ENTRIES="0">'
        '</COLLECTION><PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="2">'
        f'<NODE TYPE="FOLDER" NAME="2025"><SUBNODES COUNT="1">{playlist.format(uuid="a", year=2025)}</SUBNODES></NODE>'
        f'<NODE TYPE="FOLDER" NAME="2026"><SUBNODES COUNT="1">{playlist.format(uuid="b", year=2026)}</SUBNODES></NODE>'
        "</SUBNODES></NODE></PLAYLISTS></NML>",
        encoding="utf-8",
    )
    dangling = r.find_dangling([], nml, exists=lambda _p: False)
    assert [(d.playlist, d.path) for d in dangling] == [("Friday", "/old2025/a.mp3"), ("Friday", "/old2026/a.mp3")]
