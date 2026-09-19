from __future__ import annotations

import logging
import struct
from collections.abc import Iterable, Iterator
from os import PathLike

_LOGGER = logging.getLogger(__name__)

_TAG_LENGTH = 4
_HEADER_LENGTH = 8

_VRSN_TAG = "vrsn"
_OTRK_TAG = "otrk"
_PTRK_TAG = "ptrk"

_CRATE_VERSION_STRING = "1.0/Serato ScratchLive Crate"


def iter_chunks(data: bytes) -> Iterator[tuple[str, bytes]]:
    """Yield (tag, value) pairs from a flat Serato chunk stream.

    Defensive by design: an unrecognized tag is yielded like any other, never
    raised on -- the crate schema beyond vrsn/otrk/ptrk/column-definition
    chunks isn't fully documented, so a caller that only cares about a few
    tags should be free to skip the rest.
    """
    offset = 0
    length = len(data)
    while offset + _HEADER_LENGTH <= length:
        tag_bytes = data[offset : offset + _TAG_LENGTH]
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError:
            _LOGGER.warning("non-ASCII chunk tag at offset %d, stopping scan", offset)
            return
        (value_length,) = struct.unpack(">I", data[offset + _TAG_LENGTH : offset + _HEADER_LENGTH])
        value_start = offset + _HEADER_LENGTH
        value_end = value_start + value_length
        if value_end > length:
            _LOGGER.warning(
                "chunk %r at offset %d claims length %d past end of data, stopping scan",
                tag,
                offset,
                value_length,
            )
            return
        yield tag, data[value_start:value_end]
        offset = value_end


def write_chunk(tag: str, value: bytes) -> bytes:
    if len(tag) != _TAG_LENGTH:
        raise ValueError(f"chunk tag must be exactly {_TAG_LENGTH} characters, got {tag!r}")
    return tag.encode("ascii") + struct.pack(">I", len(value)) + value


def write_chunks(chunks: Iterable[tuple[str, bytes]]) -> bytes:
    return b"".join(write_chunk(tag, value) for tag, value in chunks)


def _utf16be(text: str) -> bytes:
    return text.encode("utf-16-be")


def _decode_utf16be(value: bytes) -> str:
    return value.decode("utf-16-be")


def parse_crate(path: str | PathLike[str]) -> list[str]:
    """Return the ordered list of track paths a .crate file references.

    Tolerant of unknown sibling chunks (osrt/ovct column definitions, and
    anything else Serato writes that isn't documented) -- only otrk/ptrk are
    interpreted, everything else at the top level is skipped.
    """
    with open(path, "rb") as f:
        data = f.read()

    track_paths: list[str] = []
    for tag, value in iter_chunks(data):
        if tag != _OTRK_TAG:
            continue
        for inner_tag, inner_value in iter_chunks(value):
            if inner_tag != _PTRK_TAG:
                continue
            try:
                track_paths.append(_decode_utf16be(inner_value))
            except UnicodeDecodeError:
                _LOGGER.warning("skipping ptrk chunk that isn't valid UTF-16BE (%d bytes)", len(inner_value))
    return track_paths


def write_crate(track_paths: list[str]) -> bytes:
    """Build a new, valid .crate byte stream from scratch.

    Only the vrsn header and one otrk/ptrk pair per path are written --
    Serato itself also writes osrt/ovct column-definition chunks (sort order
    and visible columns), but those are display-only preferences the app
    regenerates fine without, so they're omitted here for simplicity. If a
    caller ever needs a crate whose display columns exactly mirror a
    hand-built Serato crate, add them via write_chunks() directly.
    """
    chunks: list[tuple[str, bytes]] = [(_VRSN_TAG, _utf16be(_CRATE_VERSION_STRING))]
    for track_path in track_paths:
        otrk_value = write_chunk(_PTRK_TAG, _utf16be(track_path))
        chunks.append((_OTRK_TAG, otrk_value))
    return write_chunks(chunks)


def write_crate_file(path: str | PathLike[str], track_paths: list[str]) -> None:
    """Write a new crate file to `path`.

    Only ever writes to the exact path the caller passes -- never searches
    for, resolves against, or overwrites an existing/live Serato crate file
    on its own initiative.
    """
    data = write_crate(track_paths)
    with open(path, "wb") as f:
        f.write(data)
