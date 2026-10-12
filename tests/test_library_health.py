from __future__ import annotations

import csv
import io
import struct

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1
from mutagen.mp4 import MP4, MP4Cover

from djmidi.library import health
from djmidi.library.db import LibraryDB
from djmidi.library.health import (
    ISSUE_EMPTY_ARTIST,
    ISSUE_EMPTY_TITLE,
    ISSUE_LOW_BITRATE,
    ISSUE_NO_ARTWORK,
    ISSUE_UNREADABLE,
    ISSUE_ZERO_LENGTH,
    HealthIssue,
    check_file,
    check_library,
    filter_issues,
    issues_to_csv,
    iter_health_check,
)

# MPEG-1 Layer III, 44.1 kHz: bitrate index 9 = 128 kbps, 11 = 192 kbps.
_FRAME_128 = bytes([0xFF, 0xFB, 0x90, 0xC4]) + b"\x00" * (417 - 4)
_FRAME_192 = bytes([0xFF, 0xFB, 0xB0, 0xC4]) + b"\x00" * (626 - 4)


def _mp3(path, frame=_FRAME_192, title="Title", artist="Artist", cover=True):
    path.write_bytes(frame * 20)
    tags = ID3()
    if title is not None:
        tags.add(TIT2(encoding=3, text=[title]))
    if artist is not None:
        tags.add(TPE1(encoding=3, text=[artist]))
    if cover:
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=b"\x89PNG fake"))
    tags.save(path)
    return path


def _kinds(issues):
    return [issue.kind for issue in issues]


def test_healthy_mp3_has_no_issue(tmp_path):
    assert check_file(str(_mp3(tmp_path / "ok.mp3"))) == []


def test_mp3_problems_are_each_reported(tmp_path):
    path = _mp3(tmp_path / "bad.mp3", frame=_FRAME_128, title="  ", artist=None, cover=False)
    issues = check_file(str(path))
    assert _kinds(issues) == [ISSUE_EMPTY_TITLE, ISSUE_EMPTY_ARTIST, ISSUE_NO_ARTWORK, ISSUE_LOW_BITRATE]
    assert issues[-1].detail == "128 kbps"


def test_bitrate_threshold_is_configurable(tmp_path):
    path = str(_mp3(tmp_path / "a.mp3"))
    assert ISSUE_LOW_BITRATE in _kinds(check_file(path, low_bitrate=192_000))
    assert ISSUE_LOW_BITRATE not in _kinds(check_file(path, low_bitrate=191_999))


def test_untagged_file_misses_title_artist_and_artwork(tmp_path):
    path = tmp_path / "raw.mp3"
    path.write_bytes(_FRAME_192 * 20)
    assert _kinds(check_file(str(path))) == [ISSUE_EMPTY_TITLE, ISSUE_EMPTY_ARTIST, ISSUE_NO_ARTWORK]


def test_zero_byte_file_is_reported_for_that_alone(tmp_path):
    path = tmp_path / "empty.mp3"
    path.write_bytes(b"")
    assert check_file(str(path)) == [HealthIssue(str(path), ISSUE_ZERO_LENGTH, "0 bytes")]
    # The indexed size is trusted when given.
    assert _kinds(check_file(str(path), size=0)) == [ISSUE_ZERO_LENGTH]


def test_corrupt_and_missing_files_are_unreadable(tmp_path):
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"not audio at all" * 64)
    unknown = tmp_path / "notes.flac"
    unknown.write_bytes(b"plain text" * 10)
    gone = tmp_path / "gone.mp3"
    for path in (corrupt, unknown, gone):
        issues = check_file(str(path))
        assert _kinds(issues) == [ISSUE_UNREADABLE], path
        assert issues[0].detail


def _flac(path, title=None, picture=False):
    bits = (
        format(4096, "016b")
        + format(4096, "016b")
        + format(0, "024b")
        + format(0, "024b")
        + format(44100, "020b")
        + format(1, "03b")
        + format(15, "05b")
        + format(0, "036b")
    )
    streaminfo = int(bits, 2).to_bytes(18, "big") + b"\x00" * 16
    path.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo + b"\x00" * 32)
    audio = FLAC(path)
    if title:
        audio["title"] = title
        audio["artist"] = "Someone"
    if picture:
        pic = Picture()
        pic.type = 3
        pic.mime = "image/png"
        pic.data = b"\x89PNG fake"
        audio.add_picture(pic)
    audio.save()
    return path


def test_flac_artwork_and_zero_duration(tmp_path):
    # The synthetic stream declares 0 samples: a 0 s duration.
    with_cover = _flac(tmp_path / "a.flac", title="T", picture=True)
    assert _kinds(check_file(str(with_cover))) == [ISSUE_ZERO_LENGTH]
    without = _flac(tmp_path / "b.flac", title="T")
    assert ISSUE_NO_ARTWORK in _kinds(check_file(str(without)))


def _atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), name) + payload


def test_mp4_cover_atom_counts_as_artwork(tmp_path):
    path = tmp_path / "a.m4a"
    ilst = _atom(b"ilst", b"")
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + ilst)
    moov = _atom(b"moov", _atom(b"udta", meta))
    ftyp = _atom(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2mp41")
    path.write_bytes(ftyp + moov + _atom(b"mdat", b"\x00" * 16))
    audio = MP4(path)
    assert not health.has_artwork(audio)
    audio["covr"] = [MP4Cover(b"\x89PNG fake", imageformat=MP4Cover.FORMAT_PNG)]
    audio.save()
    assert health.has_artwork(MP4(path))


def test_check_is_read_only(tmp_path):
    paths = [
        _mp3(tmp_path / "a.mp3", frame=_FRAME_128, title=None, cover=False),
        _mp3(tmp_path / "b.mp3"),
    ]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    check_library([(str(p), None) for p in paths])
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths} == before


def test_iter_health_check_yields_progress_and_sorts(tmp_path):
    bad = _mp3(tmp_path / "z.mp3", frame=_FRAME_128)
    empty = tmp_path / "a.mp3"
    empty.write_bytes(b"")
    good = _mp3(tmp_path / "m.mp3")
    steps = iter_health_check([(str(bad), None), (str(empty), 0), (str(good), None)])
    progress = []
    while True:
        try:
            progress.append(next(steps))
        except StopIteration as done:
            report = done.value
            break
    assert progress == [1, 2, 3]
    assert report.checked == 3
    assert report.affected_files == 2
    assert [(i.kind, i.path) for i in report.issues] == [
        (ISSUE_ZERO_LENGTH, str(empty)),
        (ISSUE_LOW_BITRATE, str(bad)),
    ]
    counts = report.counts()
    assert counts[ISSUE_ZERO_LENGTH] == 1 and counts[ISSUE_LOW_BITRATE] == 1
    assert counts[ISSUE_UNREADABLE] == 0 and set(counts) == set(health.ISSUE_KINDS)


def test_unexpected_error_is_reported_not_raised(monkeypatch):
    def boom(path, size, low_bitrate):
        raise RuntimeError("weird file")

    monkeypatch.setattr(health, "check_file", boom)
    report = check_library([("/x.mp3", 10)])
    assert report.issues == (HealthIssue("/x.mp3", ISSUE_UNREADABLE, "weird file"),)


def test_filter_issues_by_kind_and_text():
    issues = [
        HealthIssue("/music/Tek/a.mp3", ISSUE_NO_ARTWORK),
        HealthIssue("/music/Dub/b.mp3", ISSUE_LOW_BITRATE, "96 kbps"),
        HealthIssue("/music/Dub/c.mp3", ISSUE_NO_ARTWORK),
    ]
    assert filter_issues(issues) == issues
    assert filter_issues(issues, kinds=[ISSUE_NO_ARTWORK]) == [issues[0], issues[2]]
    assert filter_issues(issues, text="dub") == issues[1:]
    assert filter_issues(issues, text="96 KBPS") == [issues[1]]
    assert filter_issues(issues, text="artwork") == [issues[0], issues[2]]
    assert filter_issues(issues, kinds=[]) == []


def test_csv_export_round_trips(tmp_path):
    issues = [
        HealthIssue("/music/a, b.mp3", ISSUE_LOW_BITRATE, "96 kbps"),
        HealthIssue("/music/é.mp3", ISSUE_EMPTY_TITLE),
    ]
    rows = list(csv.reader(io.StringIO(issues_to_csv(issues))))
    assert rows == [
        ["path", "issue", "detail"],
        ["/music/a, b.mp3", "Low bitrate", "96 kbps"],
        ["/music/é.mp3", "Empty title", ""],
    ]
    target = tmp_path / "report.csv"
    assert health.export_csv(target, issues) == 2
    with open(target, encoding="utf-8-sig", newline="") as handle:
        assert list(csv.reader(handle)) == rows


def test_health_entries_skip_missing_tracks(tmp_path):
    db = LibraryDB()
    root = db.add_root(tmp_path)
    db.upsert_track(root.id, tmp_path / "a.mp3", 10, 1.0)
    db.upsert_track(root.id, tmp_path / "b.mp3", 0, 1.0)
    db.mark_paths_missing([str(tmp_path / "b.mp3")])
    assert health.health_entries(db) == [(str(tmp_path / "a.mp3"), 10)]
    db.close()
