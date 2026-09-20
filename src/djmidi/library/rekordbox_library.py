from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# Reads Rekordbox's device-export "export.pdb" table format (the file found
# under PIONEER/rekordbox on a USB/SD export, and used as the primary fixture
# here) -- a totally different, legacy binary table format from the modern
# encrypted `master.db` SQLite database, and from the CSV controller-mapping
# format documented separately at software/rekordbox/README.md.
#
# pyrekordbox (this project's preferred, actively maintained dependency for
# every other Rekordbox format) does NOT read this format: inspecting its
# installed source (v0.4.4) shows it covers master.db, RekordboxXML, ANLZ
# analysis files and My-Settings files only, and its own README recommends
# rekordcrate/crate-digger for "device exports" -- a from-scratch PDB reader
# is still on its master branch only as an unreleased, differently-scoped
# `devicelib_plus` module for the newer encrypted `exportLibrary.db` format,
# not this one. There is no other actively-maintained Python package for this
# exact format either (the one candidate found, PyPI package "rekordbox-pdb",
# doesn't actually exist on PyPI -- only a two-star, single-commit GitHub repo
# under that name -- too thin a provenance to depend on for real personal
# library data). So this module hand-implements the format directly against
# Deep Symmetry's crate-digger `rekordbox_pdb.ksy` Kaitai Struct spec
# (https://github.com/Deep-Symmetry/crate-digger, EPL-2.0/MPL-2.0/LGPL-3.0 --
# a factual byte-layout reference, not code copied from it), verified
# byte-for-byte against the maintainer's real export.pdb during development.
# See CLAUDE.md's `library/` section for the fuller reuse-vs-hand-roll
# reasoning.

_PAGE_TYPE_TRACKS = 0
_PAGE_TYPE_GENRES = 1
_PAGE_TYPE_ARTISTS = 2
_PAGE_TYPE_ALBUMS = 3
_PAGE_TYPE_LABELS = 4
_PAGE_TYPE_KEYS = 5
_PAGE_TYPE_PLAYLIST_TREE = 7
_PAGE_TYPE_PLAYLIST_ENTRIES = 8

_HEADER_TABLES_START = 0x1C
_TABLE_ENTRY_SIZE = 16
_PAGE_HEAP_START = 0x28
_ROW_GROUP_SIZE = 0x24

_ARTIST_ID_OFFSET = 0x04
_ARTIST_NAME_NEAR_OFFSET = 0x09
_ARTIST_NAME_FAR_OFFSET = 0x0A
_ALBUM_ID_OFFSET = 0x0C
_ALBUM_NAME_NEAR_OFFSET = 0x15
_ALBUM_NAME_FAR_OFFSET = 0x16

_TRACK_OFF_KEY_ID = 0x20
_TRACK_OFF_LABEL_ID = 0x28
_TRACK_OFF_TEMPO = 0x38
_TRACK_OFF_GENRE_ID = 0x3C
_TRACK_OFF_ALBUM_ID = 0x40
_TRACK_OFF_ARTIST_ID = 0x44
_TRACK_OFF_ID = 0x48
_TRACK_OFF_YEAR = 0x50
_TRACK_OFF_DURATION = 0x54
_TRACK_OFF_RATING = 0x59
_TRACK_OFF_STRINGS = 0x5E

_STRING_INDEX_COMMENT = 16
_STRING_INDEX_TITLE = 17
_STRING_INDEX_FILENAME = 19
_STRING_INDEX_FILE_PATH = 20

_PLAYLIST_TREE_OFF_PARENT_ID = 0x00
_PLAYLIST_TREE_OFF_ID = 0x0C
_PLAYLIST_TREE_OFF_IS_FOLDER = 0x10
_PLAYLIST_TREE_OFF_NAME = 0x14


@dataclass
class RekordboxTrack:
    id: int
    title: str
    artist: str
    album: str
    genre: str
    label: str
    key: str
    bpm: float | None
    duration_seconds: int
    year: int
    rating: int
    comment: str
    file_path: str
    filename: str


@dataclass
class RekordboxPlaylist:
    id: int
    name: str
    parent_id: int
    is_folder: bool
    track_ids: list[int] = field(default_factory=list)


def decode_device_sql_string(data: bytes, pos: int) -> str:
    """Decode a DeviceSQL string starting at absolute offset `pos` in `data`.

    Three encodings share one leading byte: 0x40 is a long ASCII string, 0x90
    a long UTF-16LE string (both with a 2-byte length following), and any
    other value is a short ASCII string whose length is packed into that
    byte itself (`length = byte >> 1`).
    """
    if pos < 0 or pos >= len(data):
        return ""
    kind = data[pos]
    if kind == 0x40:
        length = struct.unpack_from("<H", data, pos + 1)[0]
        text_len = max(0, length - 4)
        return data[pos + 4 : pos + 4 + text_len].decode("ascii", errors="replace")
    if kind == 0x90:
        length = struct.unpack_from("<H", data, pos + 1)[0]
        text_len = max(0, length - 4)
        raw = data[pos + 4 : pos + 4 + text_len]
        return raw.decode("utf-16-le", errors="replace").rstrip("\x00")
    length = kind >> 1
    text_len = max(0, length - 1)
    return data[pos + 1 : pos + 1 + text_len].decode("ascii", errors="replace")


def _string_at_offset(data: bytes, row_base: int, ofs: int) -> str:
    # An offset of 0 means "no string" -- it would otherwise point back into
    # the row's own fixed fields, never valid string data.
    if ofs == 0:
        return ""
    return decode_device_sql_string(data, row_base + ofs)


@dataclass
class _Header:
    len_page: int
    tables: dict[int, tuple[int, int]]  # table_type -> (first_page, last_page)


def _read_header(data: bytes) -> _Header:
    len_page, num_tables = struct.unpack_from("<II", data, 4)
    tables: dict[int, tuple[int, int]] = {}
    for i in range(num_tables):
        entry_pos = _HEADER_TABLES_START + i * _TABLE_ENTRY_SIZE
        table_type, _empty_candidate, first_page, last_page = struct.unpack_from("<IIII", data, entry_pos)
        tables[table_type] = (first_page, last_page)
    return _Header(len_page=len_page, tables=tables)


def _iter_row_starts(data: bytes, header: _Header, table_type: int) -> Iterator[int]:
    """Yield the absolute byte offset of every present row of `table_type`.

    Table pages form a linked list (not necessarily contiguous page indices);
    each page's row index is built backwards from the page's own end, in
    groups of 16 rows with a presence bitmask per group.
    """
    pages = header.tables.get(table_type)
    if pages is None:
        return
    first_page, last_page = pages
    len_page = header.len_page
    page_index = first_page
    visited: set[int] = set()
    while page_index not in visited:
        visited.add(page_index)
        page_start = page_index * len_page
        page = data[page_start : page_start + len_page]
        if len(page) < _PAGE_HEAP_START:
            break
        page_type = struct.unpack_from("<I", page, 8)[0]
        if page_type != table_type:
            break
        next_page = struct.unpack_from("<I", page, 12)[0]
        page_flags = page[0x1B]
        packed = int.from_bytes(page[0x18:0x1B], "little")
        num_row_offsets = packed & 0x1FFF
        is_data_page = (page_flags & 0x40) == 0
        if is_data_page and num_row_offsets:
            num_row_groups = (num_row_offsets - 1) // 16 + 1
            for group in range(num_row_groups):
                base = len_page - group * _ROW_GROUP_SIZE
                if base - 4 < 0 or base > len_page:
                    continue
                row_present_flags = struct.unpack_from("<H", page, base - 4)[0]
                for row_index in range(16):
                    global_index = group * 16 + row_index
                    if global_index >= num_row_offsets:
                        continue
                    if not (row_present_flags >> row_index) & 1:
                        continue
                    ofs_pos = base - 6 - 2 * row_index
                    if ofs_pos < 0:
                        continue
                    ofs_row = struct.unpack_from("<H", page, ofs_pos)[0]
                    yield page_start + _PAGE_HEAP_START + ofs_row
        if page_index == last_page:
            break
        page_index = next_page


def _parse_name_row(data: bytes, row_start: int, id_offset: int, name_offset: int) -> tuple[int, str]:
    row_id = struct.unpack_from("<I", data, row_start + id_offset)[0]
    name = decode_device_sql_string(data, row_start + name_offset)
    return row_id, name


def _parse_artist_or_album_row(
    data: bytes, row_start: int, id_offset: int, near_offset: int, far_offset: int
) -> tuple[int, str]:
    subtype = struct.unpack_from("<H", data, row_start)[0]
    row_id = struct.unpack_from("<I", data, row_start + id_offset)[0]
    if subtype & 0x04:
        ofs = struct.unpack_from("<H", data, row_start + far_offset)[0]
    else:
        ofs = data[row_start + near_offset]
    name = _string_at_offset(data, row_start, ofs)
    return row_id, name


def _build_name_lookup(data: bytes, header: _Header, table_type: int, id_offset: int, name_offset: int) -> dict[int, str]:
    return dict(
        _parse_name_row(data, row_start, id_offset, name_offset)
        for row_start in _iter_row_starts(data, header, table_type)
    )


def _build_artist_or_album_lookup(
    data: bytes, header: _Header, table_type: int, id_offset: int, near_offset: int, far_offset: int
) -> dict[int, str]:
    return dict(
        _parse_artist_or_album_row(data, row_start, id_offset, near_offset, far_offset)
        for row_start in _iter_row_starts(data, header, table_type)
    )


def _track_string(data: bytes, row_start: int, index: int) -> str:
    ofs = struct.unpack_from("<H", data, row_start + _TRACK_OFF_STRINGS + index * 2)[0]
    return _string_at_offset(data, row_start, ofs)


def _parse_track_row(
    data: bytes,
    row_start: int,
    artists: dict[int, str],
    albums: dict[int, str],
    genres: dict[int, str],
    labels: dict[int, str],
    keys: dict[int, str],
) -> RekordboxTrack:
    track_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_ID)[0]
    artist_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_ARTIST_ID)[0]
    album_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_ALBUM_ID)[0]
    genre_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_GENRE_ID)[0]
    label_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_LABEL_ID)[0]
    key_id = struct.unpack_from("<I", data, row_start + _TRACK_OFF_KEY_ID)[0]
    tempo = struct.unpack_from("<I", data, row_start + _TRACK_OFF_TEMPO)[0]
    year = struct.unpack_from("<H", data, row_start + _TRACK_OFF_YEAR)[0]
    duration = struct.unpack_from("<H", data, row_start + _TRACK_OFF_DURATION)[0]
    rating = data[row_start + _TRACK_OFF_RATING]
    return RekordboxTrack(
        id=track_id,
        title=_track_string(data, row_start, _STRING_INDEX_TITLE),
        artist=artists.get(artist_id, ""),
        album=albums.get(album_id, ""),
        genre=genres.get(genre_id, ""),
        label=labels.get(label_id, ""),
        key=keys.get(key_id, ""),
        bpm=tempo / 100.0 if tempo else None,
        duration_seconds=duration,
        year=year,
        rating=rating,
        comment=_track_string(data, row_start, _STRING_INDEX_COMMENT),
        file_path=_track_string(data, row_start, _STRING_INDEX_FILE_PATH),
        filename=_track_string(data, row_start, _STRING_INDEX_FILENAME),
    )


def _parse_playlist_tree_row(data: bytes, row_start: int) -> RekordboxPlaylist:
    parent_id = struct.unpack_from("<I", data, row_start + _PLAYLIST_TREE_OFF_PARENT_ID)[0]
    playlist_id = struct.unpack_from("<I", data, row_start + _PLAYLIST_TREE_OFF_ID)[0]
    raw_is_folder = struct.unpack_from("<I", data, row_start + _PLAYLIST_TREE_OFF_IS_FOLDER)[0]
    name = decode_device_sql_string(data, row_start + _PLAYLIST_TREE_OFF_NAME)
    return RekordboxPlaylist(id=playlist_id, name=name, parent_id=parent_id, is_folder=bool(raw_is_folder))


def _load(pdb_path: str | Path) -> tuple[bytes, _Header]:
    data = Path(pdb_path).read_bytes()
    return data, _read_header(data)


def parse_export(pdb_path: str | Path) -> list[RekordboxTrack]:
    """Parse every track from a Rekordbox device export's `export.pdb`.

    Read-only: never writes to `pdb_path`. Artist/album/genre/label/key names
    are resolved from their own tables so each `RekordboxTrack` carries plain
    strings rather than the raw internal row IDs.
    """
    data, header = _load(pdb_path)
    artists = _build_artist_or_album_lookup(
        data, header, _PAGE_TYPE_ARTISTS, _ARTIST_ID_OFFSET, _ARTIST_NAME_NEAR_OFFSET, _ARTIST_NAME_FAR_OFFSET
    )
    albums = _build_artist_or_album_lookup(
        data, header, _PAGE_TYPE_ALBUMS, _ALBUM_ID_OFFSET, _ALBUM_NAME_NEAR_OFFSET, _ALBUM_NAME_FAR_OFFSET
    )
    genres = _build_name_lookup(data, header, _PAGE_TYPE_GENRES, 0x00, 0x04)
    labels = _build_name_lookup(data, header, _PAGE_TYPE_LABELS, 0x00, 0x04)
    keys = _build_name_lookup(data, header, _PAGE_TYPE_KEYS, 0x00, 0x08)
    return [
        _parse_track_row(data, row_start, artists, albums, genres, labels, keys)
        for row_start in _iter_row_starts(data, header, _PAGE_TYPE_TRACKS)
    ]


def parse_playlists(pdb_path: str | Path) -> list[RekordboxPlaylist]:
    """Parse the playlist/folder tree and each playlist's ordered track IDs.

    Entries are sorted by their stored `entry_index` per playlist before
    being attached, so `track_ids` reflects the playlist's real track order
    rather than page-iteration order.
    """
    data, header = _load(pdb_path)
    playlists: dict[int, RekordboxPlaylist] = {}
    for row_start in _iter_row_starts(data, header, _PAGE_TYPE_PLAYLIST_TREE):
        playlist = _parse_playlist_tree_row(data, row_start)
        playlists[playlist.id] = playlist
    entries: list[tuple[int, int, int]] = []  # (playlist_id, entry_index, track_id)
    for row_start in _iter_row_starts(data, header, _PAGE_TYPE_PLAYLIST_ENTRIES):
        entry_index, track_id, playlist_id = struct.unpack_from("<III", data, row_start)
        entries.append((playlist_id, entry_index, track_id))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    for playlist_id, _entry_index, track_id in entries:
        playlist = playlists.get(playlist_id)
        if playlist is not None:
            playlist.track_ids.append(track_id)
    return list(playlists.values())
