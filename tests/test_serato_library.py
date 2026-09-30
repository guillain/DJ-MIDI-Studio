import struct

import pytest

from djmidi.library.serato_library import (
    iter_chunks,
    parse_crate,
    write_chunk,
    write_chunks,
    write_crate,
    write_crate_file,
)

_SYNTHETIC_PATHS = [
    "Users/testuser/Music/Fake Genre/Fake Artist - Fake Track.mp3",
    "Users/testuser/Music/Fake Genre/Another Fake Track.flac",
    "Users/testuser/Music/Weird & Chars (Remix) [2026].wav",
]


def test_write_chunk_round_trips_tag_and_value():
    chunk = write_chunk("abcd", b"hello")

    assert chunk[:4] == b"abcd"
    assert struct.unpack(">I", chunk[4:8])[0] == 5
    assert chunk[8:] == b"hello"


def test_write_chunk_rejects_bad_tag_length():
    with pytest.raises(ValueError):
        write_chunk("toolong", b"")


def test_iter_chunks_reads_back_multiple_top_level_chunks():
    data = write_chunks([("aaaa", b"1"), ("bbbb", b"22"), ("cccc", b"")])

    chunks = list(iter_chunks(data))

    assert chunks == [("aaaa", b"1"), ("bbbb", b"22"), ("cccc", b"")]


def test_iter_chunks_is_tolerant_of_unknown_tags():
    data = write_chunks([("wxyz", b"unknown chunk"), ("vrsn", "hi".encode("utf-16-be"))])

    tags = [tag for tag, _ in iter_chunks(data)]

    assert tags == ["wxyz", "vrsn"]


def test_iter_chunks_stops_gracefully_on_truncated_length():
    data = write_chunk("aaaa", b"1234") + b"bbbb" + struct.pack(">I", 999) + b"short"

    chunks = list(iter_chunks(data))

    assert chunks == [("aaaa", b"1234")]


def test_write_crate_round_trips_track_paths(tmp_path):
    data = write_crate(_SYNTHETIC_PATHS)
    crate_path = tmp_path / "synthetic.crate"
    crate_path.write_bytes(data)

    result = parse_crate(crate_path)

    assert result == _SYNTHETIC_PATHS


def test_write_crate_file_round_trips(tmp_path):
    crate_path = tmp_path / "synthetic.crate"

    write_crate_file(crate_path, _SYNTHETIC_PATHS)
    result = parse_crate(crate_path)

    assert result == _SYNTHETIC_PATHS


def test_write_crate_includes_vrsn_header():
    data = write_crate([])

    tags = [tag for tag, _ in iter_chunks(data)]

    assert tags == ["vrsn"]


def test_parse_crate_skips_unknown_sibling_chunks(tmp_path):
    chunks = [
        ("vrsn", "1.0/Serato ScratchLive Crate".encode("utf-16-be")),
        ("osrt", write_chunk("tvcn", "bpm".encode("utf-16-be"))),
        ("ovct", write_chunk("tvcn", "song".encode("utf-16-be"))),
        ("otrk", write_chunk("ptrk", _SYNTHETIC_PATHS[0].encode("utf-16-be"))),
    ]
    crate_path = tmp_path / "with_columns.crate"
    crate_path.write_bytes(write_chunks(chunks))

    result = parse_crate(crate_path)

    assert result == [_SYNTHETIC_PATHS[0]]


def test_parse_crate_tolerates_otrk_with_extra_sibling_chunks(tmp_path):
    otrk_value = write_chunks(
        [
            ("ttyp", "audio".encode("utf-16-be")),
            ("ptrk", _SYNTHETIC_PATHS[1].encode("utf-16-be")),
        ]
    )
    crate_path = tmp_path / "with_extra.crate"
    crate_path.write_bytes(write_chunks([("otrk", otrk_value)]))

    result = parse_crate(crate_path)

    assert result == [_SYNTHETIC_PATHS[1]]
