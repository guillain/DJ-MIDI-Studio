"""Played-tracks history (issue #227), against synthetic fixtures shaped
like the real Serato ``.session`` and Traktor ``History/*.nml`` files."""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from pathlib import Path

from djmidi.library import history
from djmidi.library.serato_library import write_chunks


def _unix(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC).astimezone()


def _local(*parts: int) -> datetime:
    return datetime(*parts).astimezone()


def _field(field_id: int, value: bytes) -> bytes:
    return struct.pack(">II", field_id, len(value)) + value


def _text(value: str) -> bytes:
    return (value + "\0").encode("utf-16-be")


def _serato_row(path: str, start: int, *, title=None, artist=None, deck=1, played=True, session_id=1) -> bytes:
    fields = [_field(1, struct.pack(">I", 7)), _field(2, _text(path))]
    if title:
        fields.append(_field(6, _text(title)))
    if artist:
        fields.append(_field(7, _text(artist)))
    fields += [
        _field(15, struct.pack(">I", 0)),  # an unrelated field, skipped
        _field(28, struct.pack(">Q", start)),
        _field(31, struct.pack(">I", deck)),
        _field(48, struct.pack(">I", session_id)),
        _field(50, b"\x01" if played else b"\x00"),
        _field(63, _text("Offline Player")),
    ]
    return write_chunks([("adat", b"".join(fields))])


def _write_session(path: Path, rows: list[bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [("vrsn", "1.0/Serato Scratch LIVE Review".encode("utf-16-be"))]
    chunks += [("oent", row) for row in rows]
    path.write_bytes(write_chunks(chunks))
    return path


_TRAKTOR_NML = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20"><HEAD COMPANY="www.native-instruments.com" PROGRAM="Traktor Pro 4"></HEAD>
<COLLECTION ENTRIES="2">
<ENTRY TITLE="Alpha" ARTIST="Zed"><LOCATION DIR="/:Music/:Tek/:" FILE="a.mp3" VOLUME="NoSuchVolume" VOLUMEID="NoSuchVolume"></LOCATION></ENTRY>
<ENTRY TITLE="Bravo" ARTIST="Yan"><LOCATION DIR="/:Music/:Tek/:" FILE="b.mp3" VOLUME="NoSuchVolume" VOLUMEID="NoSuchVolume"></LOCATION></ENTRY>
</COLLECTION>
<SETS ENTRIES="0"></SETS>
<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1"><NODE TYPE="PLAYLIST" NAME="HISTORY">
<PLAYLIST ENTRIES="2" TYPE="PROTOCOL" UUID="00000000000000000000000000000000">
<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="NoSuchVolume/:Music/:Tek/:a.mp3"></PRIMARYKEY>
<EXTENDEDDATA DECK="0" DURATION="238.5" EXTENDEDTYPE="HistoryData" PLAYEDPUBLIC="1" STARTDATE="132713223" STARTTIME="73065"></EXTENDEDDATA>
</ENTRY>
<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="NoSuchVolume/:Music/:Tek/:b.mp3"></PRIMARYKEY>
<EXTENDEDDATA DECK="1" DURATION="60" EXTENDEDTYPE="HistoryData" PLAYEDPUBLIC="0" STARTDATE="132713223" STARTTIME="73500"></EXTENDEDDATA>
</ENTRY>
</PLAYLIST></NODE></SUBNODES></NODE></PLAYLISTS>
<INDEXING></INDEXING>
</NML>
"""


def _write_traktor(folder: Path, name: str = "history_2025y11m07d_20h21m47s.nml") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(_TRAKTOR_NML, encoding="utf-8")
    return path


def test_parse_serato_session_reads_rows(tmp_path):
    path = _write_session(
        tmp_path / "Sessions" / "3.session",
        [
            _serato_row("/Music/a.mp3", 1_700_000_500, title="Alpha", artist="Zed", deck=1),
            _serato_row("/Music/b.mp3", 1_700_000_900, deck=2, played=False),
        ],
    )
    session = history.parse_serato_session(path)
    assert session.source == history.SOURCE_SERATO
    assert session.name == "Serato session 3"
    first, second = session.entries
    assert first.path == "/Music/a.mp3"
    assert (first.title, first.artist, first.deck, first.played) == ("Alpha", "Zed", 1, True)
    assert first.played_at == _unix(1_700_000_500)
    assert second.title is None and second.played is False and second.deck == 2
    assert session.started_at == _unix(1_700_000_500)


def test_serato_truncated_row_is_tolerated(tmp_path):
    row = _serato_row("/Music/a.mp3", 1_700_000_500)
    good = _write_session(tmp_path / "1.session", [row])
    data = good.read_bytes()
    # Lie about the last field's length: the scan stops, nothing raises.
    truncated = data[:-1]
    path = tmp_path / "2.session"
    path.write_bytes(truncated)
    assert history.parse_serato_session(path).entries == []


def test_read_serato_history_accepts_history_or_sessions_folder(tmp_path):
    _write_session(tmp_path / "History" / "Sessions" / "1.session", [_serato_row("/a.mp3", 1_700_000_000)])
    (tmp_path / "History" / "Sessions" / "._1.session").write_bytes(b"\x00\x05\x16\x07junk")
    assert len(history.read_serato_history(tmp_path / "History")) == 1
    assert len(history.read_serato_history(tmp_path / "History" / "Sessions")) == 1


def test_decode_traktor_date():
    assert history.decode_traktor_date(132713223) == (2025, 11, 7)
    assert history.decode_traktor_date(0) is None


def test_parse_traktor_history(tmp_path):
    session = history.parse_traktor_history(_write_traktor(tmp_path))
    assert session.source == history.SOURCE_TRAKTOR
    first, second = session.entries
    assert first.path == "/Music/Tek/a.mp3"
    assert (first.title, first.artist, first.deck, first.duration) == ("Alpha", "Zed", 0, 238.5)
    assert first.played_at == _local(2025, 11, 7, 20, 17, 45)
    assert first.played is True
    assert second.played is False  # PLAYEDPUBLIC="0": pre-listened only


def test_read_traktor_history_skips_bad_and_appledouble_files(tmp_path):
    _write_traktor(tmp_path)
    (tmp_path / "._history_2025y11m07d_20h21m47s.nml").write_bytes(b"\x00\x05\x16\x07")
    (tmp_path / "broken.nml").write_text("<NML", encoding="utf-8")
    assert len(history.read_traktor_history(tmp_path)) == 1


def test_detect_source_and_default_dirs(tmp_path):
    serato = tmp_path / "_Serato_" / "History" / "Sessions"
    _write_session(serato / "1.session", [_serato_row("/a.mp3", 1_700_000_000)])
    traktor = tmp_path / "_Traktor" / "History"
    _write_traktor(traktor)
    assert history.detect_source(serato) == history.SOURCE_SERATO
    assert history.detect_source(serato.parent) == history.SOURCE_SERATO
    assert history.detect_source(traktor) == history.SOURCE_TRAKTOR
    assert history.detect_source(tmp_path) is None
    assert history.default_history_dirs(tmp_path) == {
        history.SOURCE_SERATO: serato,
        history.SOURCE_TRAKTOR: traktor,
    }
    assert history.default_history_dirs(tmp_path / "nothing") == {}


def test_read_history_sorts_newest_first_and_summarizes(tmp_path):
    serato = tmp_path / "Sessions"
    _write_session(serato / "1.session", [_serato_row("/Music/Tek/a.mp3", 1_600_000_000)])
    _write_session(
        serato / "2.session",
        [_serato_row("/Music/Tek/b.mp3", 1_800_000_000, played=False)],
    )
    traktor = tmp_path / "Traktor"
    _write_traktor(traktor)
    sessions = history.read_history({history.SOURCE_SERATO: serato, history.SOURCE_TRAKTOR: traktor})
    assert [s.name for s in sessions] == [
        "Serato session 2",
        "Traktor history_2025y11m07d_20h21m47s",
        "Serato session 1",
    ]
    plays = history.summarize_plays(sessions)
    # b.mp3 was only loaded (Serato) and pre-listened (Traktor): never played.
    assert set(plays) == {"/Music/Tek/a.mp3"}
    a = plays["/Music/Tek/a.mp3"]
    assert a.play_count == 2
    assert a.first_played == _unix(1_600_000_000)
    assert a.last_played == _local(2025, 11, 7, 20, 17, 45)
    library = ["/Music/Tek/a.mp3", "/Music/Tek/b.mp3", "/Music/c.mp3"]
    assert history.never_played(library, sessions) == ["/Music/Tek/b.mp3", "/Music/c.mp3"]
