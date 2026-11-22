"""Copy a playlist and its music to a drive (issue #454): copies only, safe
names, duplicates numbered, resume, space check, a Traktor playlist of the
copies."""

from collections import namedtuple

from djmidi.library import drive_export as d
from djmidi.library import traktor_library, workspace

Usage = namedtuple("Usage", "total used free")


def _music(tmp_path):
    music = tmp_path / "music"
    (music / "a").mkdir(parents=True)
    (music / "b").mkdir()
    one = music / "a" / "Intro: part 1?.mp3"
    two = music / "b" / "intro- part 1_.mp3"  # a different file whose safe name collides
    three = music / "b" / "Outro.mp3"
    for f, n in ((one, 10), (two, 20), (three, 30)):
        f.write_bytes(b"x" * n)
    return one, two, three


def test_safe_names_for_fat32_and_exfat():
    assert d.safe_name('AC/DC: "Live"?.mp3') == "AC_DC_ _Live__.mp3"
    assert d.safe_name("Track. ") == "Track"
    assert d.safe_name("???") == "untitled"
    long = "x" * 300 + ".flac"
    assert len(d.safe_name(long)) == 255 and d.safe_name(long).endswith(".flac")


def test_plan_copies_names_duplicates_missing_and_space(tmp_path):
    one, two, three = _music(tmp_path)
    drive = tmp_path / "USB"
    drive.mkdir()
    sources = [str(one), str(two), str(three), str(three), str(tmp_path / "gone.mp3")]
    p = d.plan(drive, "Friday: peak", sources, disk_usage=lambda _p: Usage(0, 0, 1000))
    assert p.folder == drive / "DJ MIDI Studio" / "Friday_ peak"
    assert [i.target.name for i in p.items] == ["Intro_ part 1_.mp3", "intro- part 1_.mp3", "Outro.mp3"]
    assert p.missing == [str(tmp_path / "gone.mp3")]
    assert p.needed == 60 and p.fits
    assert not d.plan(drive, "x", sources, disk_usage=lambda _p: Usage(0, 0, 10)).fits


def test_copy_leaves_the_originals_and_resumes(tmp_path):
    one, _two, three = _music(tmp_path)
    drive = tmp_path / "USB"
    drive.mkdir()
    p = d.plan(drive, "Set", [str(one), str(three)], disk_usage=lambda _p: Usage(0, 0, 10**6))
    steps = d.copy(p)
    first = next(steps)
    assert first.target.read_bytes() == one.read_bytes()
    steps.close()  # interrupted after one file
    again = d.plan(drive, "Set", [str(one), str(three)], disk_usage=lambda _p: Usage(0, 0, 10**6))
    assert [i.present for i in again.items] == [True, False] and again.needed == 30
    assert next(iter(d.copy(again))).target.name == "Outro.mp3"
    assert one.is_file() and three.is_file()  # copied, never moved
    assert not list(p.folder.glob("*.part"))
    assert d.copied_paths(again) == [str(p.folder / "Intro_ part 1_.mp3"), str(p.folder / "Outro.mp3")]


def test_the_traktor_playlist_points_at_the_copies_on_the_drive(tmp_path):
    one, _two, three = _music(tmp_path)
    drive = tmp_path / "USB"
    drive.mkdir()
    p = d.plan(drive, "Set", [str(one), str(three)], disk_usage=lambda _p: Usage(0, 0, 10**6))
    list(d.copy(p))
    workspace.export_traktor_playlist(p.playlist_file, "Set", d.copied_paths(p))
    keys = traktor_library.parse_playlists(p.playlist_file)["Set"]
    assert [k.rsplit("/:", 3)[-3:] for k in keys] == [
        ["DJ MIDI Studio", "Set", "Intro_ part 1_.mp3"], ["DJ MIDI Studio", "Set", "Outro.mp3"]
    ]
    # On a real drive (/Volumes/<name>) the key names that drive, so Traktor
    # finds the copies wherever the drive is plugged in.
    assert workspace.traktor_location("/Volumes/USB/DJ MIDI Studio/Set/Outro.mp3") == (
        "USB", "/:DJ MIDI Studio/:Set/:", "Outro.mp3"
    )


def test_files_too_big_for_fat32_are_reported(tmp_path, monkeypatch):
    one, *_ = _music(tmp_path)
    monkeypatch.setattr(d, "FAT32_MAX", 5)
    p = d.plan(tmp_path, "Set", [str(one)], disk_usage=lambda _p: Usage(0, 0, 10**6))
    assert p.too_big == [str(one)] and p.items == []
    assert d.plan(tmp_path, "Set", [str(one)], fat32=False).items
