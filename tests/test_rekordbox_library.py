from __future__ import annotations

import struct

import pytest

from djmidi.library.rekordbox_library import (
    RekordboxPlaylist,
    RekordboxTrack,
    decode_device_sql_string,
    parse_export,
    parse_playlists,
)

# A from-scratch, minimal synthetic export.pdb builder -- exercises the real
# page/row-index binary layout end to end (not just our own wrapper logic),
# without ever touching the maintainer's real library file. Field layouts
# mirror djmidi.library.rekordbox_library's own offset constants, which were
# themselves verified against that real file during development (see
# CLAUDE.md).

_LEN_PAGE = 4096

_PAGE_TYPE_TRACKS = 0
_PAGE_TYPE_GENRES = 1
_PAGE_TYPE_ARTISTS = 2
_PAGE_TYPE_ALBUMS = 3
_PAGE_TYPE_LABELS = 4
_PAGE_TYPE_KEYS = 5
_PAGE_TYPE_PLAYLIST_TREE = 7
_PAGE_TYPE_PLAYLIST_ENTRIES = 8


def _short_ascii_string(text: str) -> bytes:
    raw = text.encode("ascii")
    length = len(raw) + 1
    kind = (length << 1) | 1
    return bytes([kind]) + raw


def _long_ascii_string(text: str) -> bytes:
    raw = text.encode("ascii")
    length = len(raw) + 4
    return bytes([0x40]) + struct.pack("<H", length) + b"\x00" + raw


def _long_utf16_string(text: str) -> bytes:
    raw = text.encode("utf-16-le")
    length = len(raw) + 4
    return bytes([0x90]) + struct.pack("<H", length) + b"\x00" + raw


def _genre_row(id_: int, name: str) -> bytes:
    return struct.pack("<I", id_) + _short_ascii_string(name)


def _label_row(id_: int, name: str) -> bytes:
    return struct.pack("<I", id_) + _short_ascii_string(name)


def _key_row(id_: int, name: str) -> bytes:
    return struct.pack("<II", id_, id_) + _short_ascii_string(name)


def _artist_row(id_: int, name: str) -> bytes:
    header = struct.pack("<HHIBB", 0x60, 0, id_, 0x03, 0x0A)
    return header + _short_ascii_string(name)


def _album_row(id_: int, artist_id: int, name: str) -> bytes:
    header = struct.pack("<HHIIIIBB", 0x80, 0, 0, artist_id, id_, 0, 0x03, 0x16)
    return header + _short_ascii_string(name)


def _playlist_tree_row(id_: int, parent_id: int, name: str, *, is_folder: bool, sort_order: int = 0) -> bytes:
    header = struct.pack("<IIIII", parent_id, 0, sort_order, id_, 1 if is_folder else 0)
    return header + _short_ascii_string(name)


def _playlist_entry_row(entry_index: int, track_id: int, playlist_id: int) -> bytes:
    return struct.pack("<III", entry_index, track_id, playlist_id)


def _track_row(
    track_id: int,
    *,
    artist_id: int = 0,
    album_id: int = 0,
    genre_id: int = 0,
    label_id: int = 0,
    key_id: int = 0,
    tempo: int = 0,
    year: int = 0,
    duration: int = 0,
    rating: int = 0,
    title: str = "",
    comment: str = "",
    filename: str = "",
    file_path: str = "",
) -> bytes:
    fixed = bytearray(0x88)
    struct.pack_into("<H", fixed, 0x00, 0x24)
    struct.pack_into("<I", fixed, 0x20, key_id)
    struct.pack_into("<I", fixed, 0x28, label_id)
    struct.pack_into("<I", fixed, 0x38, tempo)
    struct.pack_into("<I", fixed, 0x3C, genre_id)
    struct.pack_into("<I", fixed, 0x40, album_id)
    struct.pack_into("<I", fixed, 0x44, artist_id)
    struct.pack_into("<I", fixed, 0x48, track_id)
    struct.pack_into("<H", fixed, 0x50, year)
    struct.pack_into("<H", fixed, 0x54, duration)
    fixed[0x59] = rating

    tail = bytearray()
    cursor = 0x88
    for index, text in ((16, comment), (17, title), (19, filename), (20, file_path)):
        if not text:
            continue
        encoded = _short_ascii_string(text)
        struct.pack_into("<H", fixed, 0x5E + index * 2, cursor)
        tail += encoded
        cursor += len(encoded)
    return bytes(fixed) + bytes(tail)


def _build_page(page_index: int, page_type: int, rows: list[bytes]) -> bytes:
    page = bytearray(_LEN_PAGE)
    struct.pack_into("<I", page, 4, page_index)
    struct.pack_into("<I", page, 8, page_type)
    struct.pack_into("<I", page, 12, page_index)  # next_page: irrelevant, first_page == last_page
    n = len(rows)
    packed = ((n & 0x7FF) << 13) | (n & 0x1FFF)
    page[0x18:0x1B] = packed.to_bytes(3, "little")
    page[0x1B] = 0x24  # data page (bit 0x40 clear)

    heap_pos = 0x28
    cursor = heap_pos
    offsets = []
    for row in rows:
        offsets.append(cursor - heap_pos)
        page[cursor : cursor + len(row)] = row
        cursor += len(row)
    assert cursor <= _LEN_PAGE - 64, "test row data collided with the fixture page's row index"

    base = _LEN_PAGE
    present_mask = (1 << n) - 1 if n else 0
    struct.pack_into("<H", page, base - 4, present_mask)
    for i, ofs in enumerate(offsets):
        struct.pack_into("<H", page, base - 6 - 2 * i, ofs)
    return bytes(page)


def _build_pdb_bytes(table_pages: dict[int, list[bytes]]) -> bytes:
    num_tables = len(table_pages)
    total_pages = 1 + num_tables
    buf = bytearray(_LEN_PAGE * total_pages)
    struct.pack_into("<I", buf, 4, _LEN_PAGE)
    struct.pack_into("<I", buf, 8, num_tables)
    struct.pack_into("<I", buf, 12, total_pages)

    entry_pos = 0x1C
    page_index = 1
    for table_type, rows in table_pages.items():
        struct.pack_into("<I", buf, entry_pos, table_type)
        struct.pack_into("<I", buf, entry_pos + 4, 0)
        struct.pack_into("<I", buf, entry_pos + 8, page_index)
        struct.pack_into("<I", buf, entry_pos + 12, page_index)
        page = _build_page(page_index, table_type, rows)
        buf[page_index * _LEN_PAGE : (page_index + 1) * _LEN_PAGE] = page
        entry_pos += 16
        page_index += 1
    return bytes(buf)


def _synthetic_pdb_path(tmp_path) -> str:
    pdb = _build_pdb_bytes(
        {
            _PAGE_TYPE_GENRES: [_genre_row(1, "Drum & Bass")],
            _PAGE_TYPE_ARTISTS: [_artist_row(10, "Amon Tobin"), _artist_row(11, "Squarepusher")],
            _PAGE_TYPE_ALBUMS: [_album_row(20, 10, "Supermodified")],
            _PAGE_TYPE_LABELS: [_label_row(30, "Ninja Tune")],
            _PAGE_TYPE_KEYS: [_key_row(40, "Am")],
            _PAGE_TYPE_TRACKS: [
                _track_row(
                    1,
                    artist_id=10,
                    album_id=20,
                    genre_id=1,
                    label_id=30,
                    key_id=40,
                    tempo=17000,
                    year=2000,
                    duration=300,
                    rating=4,
                    title="Get Your Snack On",
                    comment="great track",
                    filename="track.mp3",
                    file_path="/Contents/Amon Tobin/track.mp3",
                ),
                _track_row(2, title="No Metadata"),
            ],
            _PAGE_TYPE_PLAYLIST_TREE: [
                _playlist_tree_row(100, 0, "Drum & Bass", is_folder=True),
                _playlist_tree_row(101, 100, "Favorites", is_folder=False),
            ],
            _PAGE_TYPE_PLAYLIST_ENTRIES: [
                _playlist_entry_row(1, 2, 101),
                _playlist_entry_row(0, 1, 101),
            ],
        }
    )
    path = tmp_path / "export.pdb"
    path.write_bytes(pdb)
    return str(path)


def test_decode_device_sql_string_short_ascii():
    data = _short_ascii_string("Hello")
    assert decode_device_sql_string(data, 0) == "Hello"


def test_decode_device_sql_string_long_ascii():
    data = _long_ascii_string("A longer ASCII string")
    assert decode_device_sql_string(data, 0) == "A longer ASCII string"


def test_decode_device_sql_string_long_utf16le():
    data = _long_utf16_string("Héllo Wörld")
    assert decode_device_sql_string(data, 0) == "Héllo Wörld"


def test_decode_device_sql_string_out_of_range_is_empty():
    assert decode_device_sql_string(b"", 0) == ""
    assert decode_device_sql_string(b"abc", 99) == ""


def test_parse_export_resolves_names_and_fields(tmp_path):
    path = _synthetic_pdb_path(tmp_path)

    tracks = parse_export(path)

    assert len(tracks) == 2
    by_id = {t.id: t for t in tracks}
    full = by_id[1]
    assert full.title == "Get Your Snack On"
    assert full.artist == "Amon Tobin"
    assert full.album == "Supermodified"
    assert full.genre == "Drum & Bass"
    assert full.label == "Ninja Tune"
    assert full.key == "Am"
    assert full.bpm == pytest.approx(170.0)
    assert full.duration_seconds == 300
    assert full.year == 2000
    assert full.rating == 4
    assert full.comment == "great track"
    assert full.filename == "track.mp3"
    assert full.file_path == "/Contents/Amon Tobin/track.mp3"

    minimal = by_id[2]
    assert minimal.title == "No Metadata"
    assert minimal.artist == ""
    assert minimal.album == ""
    assert minimal.bpm is None


def test_parse_playlists_builds_tree_and_orders_entries(tmp_path):
    path = _synthetic_pdb_path(tmp_path)

    playlists = parse_playlists(path)

    by_id = {p.id: p for p in playlists}
    assert by_id[100].name == "Drum & Bass"
    assert by_id[100].is_folder is True
    assert by_id[100].parent_id == 0
    assert by_id[101].name == "Favorites"
    assert by_id[101].is_folder is False
    assert by_id[101].parent_id == 100
    # entries were appended out of entry_index order; parse_playlists must sort them
    assert by_id[101].track_ids == [1, 2]


def test_rekordbox_track_and_playlist_are_plain_dataclasses():
    track = RekordboxTrack(
        id=1,
        title="t",
        artist="a",
        album="al",
        genre="g",
        label="l",
        key="k",
        bpm=120.0,
        duration_seconds=100,
        year=2020,
        rating=5,
        comment="c",
        file_path="/x",
        filename="x.mp3",
    )
    assert track.id == 1

    playlist = RekordboxPlaylist(id=1, name="n", parent_id=0, is_folder=False)
    assert playlist.track_ids == []
