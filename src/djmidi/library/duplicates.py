"""Duplicate track detection across the scanned library (issue #184).

Two independent tiers, both strictly read-only against the real files:

- **metadata** (`find_metadata_duplicates`): tracks whose *normalized*
  artist + title match. Cheap -- works off the tag cache, no file is
  opened. A candidate list, not proof: two genuinely different recordings
  that share an artist and title (a live take, a re-recording) land here
  too, so the GUI shows them for the DJ to judge.
- **exact** (`iter_exact_duplicates`): byte-identical files. Only files
  sharing the same size are ever read; within a same-size group a hash of
  the first `PREFIX_BYTES` rules most coincidences out before a full
  content hash (`hashlib.blake2b`, read in `CHUNK_BYTES` chunks) confirms
  the rest. A generator, so a GUI can drive it a slice at a time from a
  `QTimer` like `scanner.iter_scan_root`, without this module depending on
  Qt.

Normalization rules (`normalize_artist` / `normalize_title`), deliberately
conservative -- a false "duplicate" costs the DJ a look, a lost distinction
between two versions of a track would cost a mix:

1. Unicode NFKD, accents dropped (``Beyoncé`` == ``Beyonce``), casefolded.
2. A featured-artist credit is dropped: ``feat.``/``feat``/``ft.``/``ft``/
   ``featuring`` and everything after it in the artist, and the same inside
   a ``(…)``/``[…]`` group or after a bare ``feat.`` in the title.
3. In the title only, a version suffix meaning "the default version" is
   dropped: ``(Original Mix)``, ``(Original)``, ``(Original Version)``,
   ``- Original Mix`` (and the ``[…]`` forms). Every other version marker
   -- ``(Extended Mix)``, ``(Radio Edit)``, ``(X Remix)``, ``(Live)``, … --
   is kept, since those are different tracks to a DJ.
4. Every remaining non-alphanumeric run becomes one space (so ``&``, ``-``,
   ``'`` and punctuation don't matter), then whitespace is trimmed.

A track with no artist or no title after normalization is never grouped by
metadata: "Unknown artist / Track 01" is not evidence of a duplicate.

Duration is not compared yet -- the tag cache doesn't hold it, and reading
it would open every file; the exact tier is the stronger signal anyway.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections import defaultdict
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from pathlib import Path

from .db import LibraryDB

_LOGGER = logging.getLogger(__name__)

TIER_EXACT = "exact"
TIER_METADATA = "metadata"

CHUNK_BYTES = 1 << 20
PREFIX_BYTES = 64 * 1024

_FEAT = r"(?:feat\.?|ft\.?|featuring)"
# "Artist feat. Someone" -> "Artist" (word-bounded, so "Daft" stays).
_ARTIST_FEAT_RE = re.compile(rf"\s*[(\[]?\s*\b{_FEAT}(?=\s|$).*$", re.IGNORECASE)
# "(feat. Someone)" / "[ft Someone]" anywhere in a title.
_TITLE_FEAT_GROUP_RE = re.compile(rf"\s*[(\[]\s*{_FEAT}(?=\s|[)\]]).*?[)\]]", re.IGNORECASE)
# A bare trailing "feat. Someone" in a title.
_TITLE_FEAT_TAIL_RE = re.compile(rf"\s+\b{_FEAT}(?=\s).*$", re.IGNORECASE)
_ORIGINAL = r"original(?:\s+(?:mix|version))?"
_TITLE_ORIGINAL_RE = re.compile(
    rf"\s*(?:[(\[]\s*{_ORIGINAL}\s*[)\]]|-\s*{_ORIGINAL})\s*$",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def _squash(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", text).strip()


def normalize_artist(artist: str | None) -> str:
    """Comparison form of an artist tag (rules in the module docstring)."""
    if not artist:
        return ""
    text = _fold(artist)
    text = _ARTIST_FEAT_RE.sub("", text)
    return _squash(text)


def normalize_title(title: str | None) -> str:
    """Comparison form of a title tag (rules in the module docstring)."""
    if not title:
        return ""
    text = _fold(title)
    text = _TITLE_FEAT_GROUP_RE.sub("", text)
    text = _TITLE_FEAT_TAIL_RE.sub("", text)
    text = _TITLE_ORIGINAL_RE.sub("", text)
    return _squash(text)


def metadata_key(artist: str | None, title: str | None) -> tuple[str, str] | None:
    """`(artist, title)` in comparison form, or None if either is empty."""
    norm_artist = normalize_artist(artist)
    norm_title = normalize_title(title)
    if not norm_artist or not norm_title:
        return None
    return norm_artist, norm_title


@dataclass(frozen=True)
class DuplicateGroup:
    """Two or more files the given tier considers the same track."""

    tier: str
    key: str
    """Human-readable reason: ``artist — title`` or the content digest."""
    paths: tuple[str, ...]
    size: int | None = None
    """Shared file size in bytes (exact tier only)."""
    label: str = ""
    """Display name: the first file's own ``Artist — Title`` tags (metadata
    tier only -- `key` is the lowercased comparison form)."""


def find_metadata_duplicates(entries: Iterable[tuple[str, str | None, str | None]]) -> list[DuplicateGroup]:
    """Group `(path, artist, title)` entries by normalized artist + title.

    Returns only groups of two or more, largest first, then by key."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    labels: dict[tuple[str, str], str] = {}
    for path, artist, title in entries:
        key = metadata_key(artist, title)
        if key is not None:
            groups[key].append(path)
            labels.setdefault(key, f"{artist.strip()} — {title.strip()}")
    result = [
        DuplicateGroup(
            tier=TIER_METADATA, key=f"{artist} — {title}", paths=tuple(sorted(paths)), label=labels[(artist, title)]
        )
        for (artist, title), paths in groups.items()
        if len(paths) > 1
    ]
    result.sort(key=lambda group: (-len(group.paths), group.key))
    return result


def _hash_file(path: str, limit: int | None = None) -> Generator[None, None, str]:
    """Hash `path` (only its first `limit` bytes if given), yielding after
    every chunk so a very large WAV can't stall a GUI slice."""
    digest = hashlib.blake2b(digest_size=20)
    remaining = limit
    with open(path, "rb") as handle:
        while True:
            size = CHUNK_BYTES if remaining is None else min(CHUNK_BYTES, remaining)
            if size <= 0:
                break
            chunk = handle.read(size)
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
            yield
    return digest.hexdigest()


def _group_by_hash(paths: list[str], limit: int | None) -> Generator[None, None, dict[str, list[str]]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        try:
            digest = yield from _hash_file(path, limit)
        except OSError as exc:
            _LOGGER.warning("Skipping unreadable file %s: %s", path, exc)
            continue
        by_hash[digest].append(path)
    return by_hash


def exact_candidate_count(entries: Iterable[tuple[str, int]]) -> int:
    """How many files `iter_exact_duplicates` will open (its progress total):
    the non-empty files whose size at least one other file shares."""
    sizes: dict[int, int] = defaultdict(int)
    for _path, size in entries:
        if size > 0:
            sizes[size] += 1
    return sum(count for count in sizes.values() if count > 1)


def iter_exact_duplicates(
    entries: Iterable[tuple[str, int]],
) -> Generator[int, None, list[DuplicateGroup]]:
    """Find byte-identical files among `(path, size)` entries.

    Yields the number of candidate files fully processed so far (after
    every chunk read, so the value may repeat) and returns the groups via
    ``StopIteration.value``. Files of a size no other file shares are never
    opened; empty files are ignored. An unreadable file is skipped with a
    logged warning instead of aborting the search."""
    by_size: dict[int, list[str]] = defaultdict(list)
    for path, size in entries:
        if size > 0:
            by_size[size].append(path)
    candidates = {size: paths for size, paths in by_size.items() if len(paths) > 1}
    result: list[DuplicateGroup] = []
    processed = 0
    for size, paths in sorted(candidates.items()):
        prefix_groups = yield from _counting(_group_by_hash(paths, PREFIX_BYTES), processed)
        for prefix_digest, same_prefix in prefix_groups.items():
            if len(same_prefix) < 2:
                continue
            if size <= PREFIX_BYTES:
                # The prefix hash already covered the whole file.
                full_groups = {prefix_digest: same_prefix}
            else:
                full_groups = yield from _counting(_group_by_hash(same_prefix, None), processed)
            for digest, same in full_groups.items():
                if len(same) > 1:
                    result.append(DuplicateGroup(tier=TIER_EXACT, key=digest, paths=tuple(sorted(same)), size=size))
        processed += len(paths)
        yield processed
    result.sort(key=lambda group: (-len(group.paths), -(group.size or 0), group.paths))
    return result


def _counting(steps: Generator[None, None, dict[str, list[str]]], processed: int):
    """Re-yield a hashing generator's steps as the running file count."""
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value
        yield processed


def find_exact_duplicates(entries: Iterable[tuple[str, int]]) -> list[DuplicateGroup]:
    """Blocking `iter_exact_duplicates` (scripts, tests)."""
    steps = iter_exact_duplicates(entries)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def metadata_entries(db: LibraryDB) -> list[tuple[str, str | None, str | None]]:
    """`(path, artist, title)` for every present track with cached tags."""
    return [
        (record.path, metadata.artist, metadata.title)
        for record, metadata in db.list_tracks_with_metadata()
        if metadata is not None and not record.missing
    ]


def size_entries(db: LibraryDB) -> list[tuple[str, int]]:
    """`(path, size)` for every present track, as recorded by the last scan."""
    return [(record.path, record.size) for record in db.list_tracks(include_missing=False)]


def audio_bitrate(path: str | Path) -> int | None:
    """Bitrate in bits/s from the file's stream header, None if unknown.

    Reads only the header mutagen needs, never decodes audio; returns None
    for an unreadable or unrecognized file (and for lossless formats that
    don't report one)."""
    import mutagen

    try:
        audio = mutagen.File(str(path))
    except (mutagen.MutagenError, OSError, ValueError):
        return None
    bitrate = getattr(getattr(audio, "info", None), "bitrate", None)
    return int(bitrate) if bitrate else None


__all__ = [
    "CHUNK_BYTES",
    "PREFIX_BYTES",
    "TIER_EXACT",
    "TIER_METADATA",
    "DuplicateGroup",
    "audio_bitrate",
    "exact_candidate_count",
    "find_exact_duplicates",
    "find_metadata_duplicates",
    "iter_exact_duplicates",
    "metadata_entries",
    "metadata_key",
    "normalize_artist",
    "normalize_title",
    "size_entries",
]
