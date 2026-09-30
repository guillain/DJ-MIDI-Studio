"""Generic codec for nested "4-character tag + 32-bit big-endian size" chunks.

Several DJ-software file formats share this ID3v2-like framing: Traktor's
`.tsi` controller-mapping blob (issue #122) and Serato's `.crate` files
both store a stream of ``tag (4 ASCII bytes) | size (u32 BE) | payload``
records, where some payloads are themselves chunk streams. What differs per
format is only *which* chunks are containers and what fixed header (a count,
a length-prefixed name, ...) precedes their children -- so that knowledge is
passed in as a `ContainerSpec`, and this module stays format-agnostic.

The decoded tree re-encodes byte-for-byte when unmodified (sizes are
recomputed from content, so an edited leaf that changes length propagates
correctly to every ancestor). Anything not declared a container is kept as
an opaque leaf -- unknown chunk types survive a round trip untouched.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

TAG_LENGTH = 4
HEADER_LENGTH = 8

# How many payload bytes precede a container's children: a fixed count, or
# a function of the payload (e.g. a length-prefixed UTF-16 name).
PrefixLength = int | Callable[[bytes], int]
# Keyed by (parent tag or None for top level, tag): the same tag can be a
# container in one place and a leaf in another (Traktor's DCBM is both).
ContainerSpec = Mapping[tuple[str | None, str], PrefixLength]


class ChunkError(ValueError):
    """Raised on a truncated or malformed chunk stream."""


@dataclass
class ChunkNode:
    tag: str
    prefix: bytes = b""
    """Container header bytes before the children (empty for a leaf)."""
    children: list[ChunkNode] | None = None
    """Child chunks, or None for an opaque leaf."""
    payload: bytes = b""
    """A leaf's raw payload (unused for a container)."""

    @property
    def is_container(self) -> bool:
        return self.children is not None

    def find(self, tag: str) -> ChunkNode | None:
        return next((child for child in self.children or () if child.tag == tag), None)

    def find_all(self, tag: str) -> list[ChunkNode]:
        return [child for child in self.children or () if child.tag == tag]

    def encoded_payload(self) -> bytes:
        if self.children is None:
            return self.payload
        return self.prefix + b"".join(encode_node(child) for child in self.children)


def iter_raw_chunks(data: bytes, start: int = 0, end: int | None = None) -> Iterator[tuple[str, int, int]]:
    """Yields ``(tag, payload_start, payload_end)`` for each chunk in
    ``data[start:end]``; raises `ChunkError` on truncation."""
    end = len(data) if end is None else end
    offset = start
    while offset < end:
        if offset + HEADER_LENGTH > end:
            raise ChunkError(f"truncated chunk header at offset {offset}")
        try:
            tag = data[offset : offset + TAG_LENGTH].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ChunkError(f"non-ASCII chunk tag at offset {offset}") from exc
        (size,) = struct.unpack(">I", data[offset + TAG_LENGTH : offset + HEADER_LENGTH])
        payload_start = offset + HEADER_LENGTH
        payload_end = payload_start + size
        if payload_end > end:
            raise ChunkError(f"chunk {tag!r} at offset {offset} claims {size} bytes past the end of its parent")
        yield tag, payload_start, payload_end
        offset = payload_end


def decode(data: bytes, containers: ContainerSpec) -> list[ChunkNode]:
    return _decode_range(data, 0, len(data), None, containers)


def _decode_range(
    data: bytes, start: int, end: int, parent: str | None, containers: ContainerSpec
) -> list[ChunkNode]:
    nodes = []
    for tag, payload_start, payload_end in iter_raw_chunks(data, start, end):
        spec = containers.get((parent, tag))
        if spec is None:
            nodes.append(ChunkNode(tag=tag, payload=data[payload_start:payload_end]))
            continue
        payload = data[payload_start:payload_end]
        prefix_length = spec(payload) if callable(spec) else spec
        if prefix_length > len(payload):
            raise ChunkError(f"container {tag!r} header ({prefix_length} bytes) exceeds its payload")
        children = _decode_range(data, payload_start + prefix_length, payload_end, tag, containers)
        nodes.append(ChunkNode(tag=tag, prefix=payload[:prefix_length], children=children))
    return nodes


def encode_node(node: ChunkNode) -> bytes:
    payload = node.encoded_payload()
    tag = node.tag.encode("ascii")
    if len(tag) != TAG_LENGTH:
        raise ChunkError(f"chunk tag must be {TAG_LENGTH} ASCII characters, got {node.tag!r}")
    return tag + struct.pack(">I", len(payload)) + payload


def encode(nodes: list[ChunkNode]) -> bytes:
    return b"".join(encode_node(node) for node in nodes)


class BigEndianReader:
    """Cursor over a payload for the fixed-layout fields inside a leaf."""

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.offset = offset

    def _take(self, size: int) -> bytes:
        if self.offset + size > len(self.data):
            raise ChunkError(f"read of {size} bytes at offset {self.offset} past the end of a {len(self.data)}-byte field")
        chunk = self.data[self.offset : self.offset + size]
        self.offset += size
        return chunk

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def f32(self) -> float:
        return struct.unpack(">f", self._take(4))[0]

    def utf16_string(self) -> str:
        """An ``int32`` character count followed by that many UTF-16BE units."""
        length = self.i32()
        if length < 0:
            raise ChunkError(f"negative string length {length} at offset {self.offset - 4}")
        return self._take(2 * length).decode("utf-16-be")


def utf16_string_bytes(text: str) -> bytes:
    encoded = text.encode("utf-16-be")
    return struct.pack(">i", len(encoded) // 2) + encoded


def utf16_string_length(data: bytes, offset: int = 0) -> int:
    """Byte length of a length-prefixed UTF-16BE string at `offset` -- a
    ready-made `PrefixLength` for containers headed by a name."""
    (length,) = struct.unpack(">i", data[offset : offset + 4])
    return 4 + 2 * length
