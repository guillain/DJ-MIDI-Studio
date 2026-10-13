"""Library statistics (issue #258): counts a DJ can read at a glance.

Pure aggregation over what the Music Library tab already holds -- its
`workspace.LibraryRow`s (cached tags, Camelot key, taxonomy category), the
index's file mtimes and, when play history (issue #227) is loaded, the
`history.summarize_plays` result. Nothing is read from or written to an
audio file here.

Only *present* tracks are counted; missing ones (an unplugged drive) are
reported as a single number, so the charts don't change shape every time a
drive is unmounted.

- **Categories**: the confirmed taxonomy category (an exact/alias match);
  a fuzzy suggestion is never counted as a category, same as the table.
- **Genres**: the raw genre tag, grouped case- and space-insensitively
  (the most used spelling is the label).
- **BPM**: a histogram of `bpm_bin_width`-wide bins, every bin between the
  lowest and the highest present so gaps show as empty bars.
- **Keys**: all 24 Camelot codes in wheel order (1A, 1B, … 12B), zeros
  included, so the wheel's shape is always the same.
- **Added per month**: the file's mtime -- the index has no "date added",
  and a file's mtime is when it was copied/downloaded unless something
  rewrote it since (a tag edit does). Every month between the first and the
  last is listed.
- **Plays**: most-played present tracks and how many were never played;
  `None` when no history is loaded (no history is not "never played").
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .history import TrackPlays
from .workspace import LibraryRow

UNCATEGORIZED_LABEL = "Uncategorized"
NO_GENRE_LABEL = "(no genre)"
DEFAULT_BPM_BIN_WIDTH = 5
DEFAULT_TOP_PLAYED = 25

CAMELOT_ORDER: tuple[str, ...] = tuple(
    f"{number}{letter}" for number in range(1, 13) for letter in "AB"
)


@dataclass(frozen=True)
class Bucket:
    label: str
    count: int


@dataclass(frozen=True)
class PlayedTrack:
    path: str
    label: str
    play_count: int
    last_played: datetime | None


@dataclass(frozen=True)
class LibraryStats:
    total: int
    """Present tracks counted below."""
    missing: int
    by_category: tuple[Bucket, ...]
    by_genre: tuple[Bucket, ...]
    bpm_histogram: tuple[Bucket, ...]
    no_bpm: int
    by_camelot: tuple[Bucket, ...]
    no_key: int
    added_per_month: tuple[Bucket, ...]
    most_played: tuple[PlayedTrack, ...] | None = None
    """`None` when no play history was given."""
    never_played: int | None = None
    played: int | None = None
    """Present tracks played at least once (`None` without history)."""


def category_label(canonical: str) -> str:
    return canonical.replace("%%", " / ")


def _sorted_buckets(counts: Counter[str]) -> tuple[Bucket, ...]:
    """Most frequent first, ties alphabetical."""
    return tuple(
        Bucket(label, count)
        for label, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def count_categories(rows: Iterable[LibraryRow]) -> tuple[Bucket, ...]:
    counts: Counter[str] = Counter(
        category_label(row.category) if row.category else UNCATEGORIZED_LABEL
        for row in rows
    )
    return _sorted_buckets(counts)


def count_genres(rows: Iterable[LibraryRow]) -> tuple[Bucket, ...]:
    counts: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for row in rows:
        raw = row.metadata.genre if row.metadata else None
        text = " ".join(raw.split()) if raw else ""
        if not text:
            counts[NO_GENRE_LABEL] += 1
            continue
        spellings.setdefault(text.casefold(), Counter())[text] += 1
    for variants in spellings.values():
        # The most used spelling names the group; ties go to the
        # alphabetically first, so the label doesn't depend on row order.
        label = min(variants, key=lambda text: (-variants[text], text))
        counts[label] += variants.total()
    return _sorted_buckets(counts)


def bpm_histogram(
    bpms: Iterable[float | None], bin_width: int = DEFAULT_BPM_BIN_WIDTH
) -> tuple[tuple[Bucket, ...], int]:
    """(bins, how many had no usable BPM). A bin is labelled ``"120–124"``
    for width 5; bins run from the lowest to the highest present."""
    if bin_width < 1:
        raise ValueError("bin_width must be at least 1")
    counts: Counter[int] = Counter()
    missing = 0
    for bpm in bpms:
        if bpm is None or not math.isfinite(bpm) or bpm <= 0:
            missing += 1
            continue
        counts[int(bpm // bin_width) * bin_width] += 1
    if not counts:
        return (), missing
    low, high = min(counts), max(counts)
    bins = tuple(
        Bucket(
            f"{start}–{start + bin_width - 1}" if bin_width > 1 else str(start),
            counts.get(start, 0),
        )
        for start in range(low, high + bin_width, bin_width)
    )
    return bins, missing


def camelot_distribution(keys: Iterable[str | None]) -> tuple[tuple[Bucket, ...], int]:
    """(the 24 Camelot codes in wheel order, how many had no key)."""
    counts: Counter[str] = Counter()
    missing = 0
    for key in keys:
        code = key.strip().upper() if key else ""
        if code in CAMELOT_ORDER:
            counts[code] += 1
        else:
            missing += 1
    return tuple(Bucket(code, counts.get(code, 0)) for code in CAMELOT_ORDER), missing


def added_per_month(mtimes: Iterable[float]) -> tuple[Bucket, ...]:
    """``"YYYY-MM"`` (local time) → files, every month from first to last."""
    counts: Counter[tuple[int, int]] = Counter()
    for mtime in mtimes:
        try:
            moment = datetime.fromtimestamp(mtime).astimezone()
        except OverflowError, OSError, ValueError:
            continue
        counts[(moment.year, moment.month)] += 1
    if not counts:
        return ()
    (year, month), last = min(counts), max(counts)
    buckets: list[Bucket] = []
    while (year, month) <= last:
        buckets.append(Bucket(f"{year:04d}-{month:02d}", counts.get((year, month), 0)))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(buckets)


def _track_label(row: LibraryRow) -> str:
    metadata = row.metadata
    parts = [metadata.artist, metadata.title] if metadata else []
    return " — ".join(part for part in parts if part) or Path(row.path).name


def compute_library_stats(
    rows: Iterable[LibraryRow],
    mtimes: Mapping[str, float] | None = None,
    plays: Mapping[str, TrackPlays] | None = None,
    bpm_bin_width: int = DEFAULT_BPM_BIN_WIDTH,
    top_played: int = DEFAULT_TOP_PLAYED,
) -> LibraryStats:
    """Every statistic for `rows`. `mtimes` maps a path to its indexed
    mtime (tracks without one are left out of "added per month"); `plays`
    is `history.summarize_plays` output, or `None` when no history is loaded."""
    all_rows = list(rows)
    present = [row for row in all_rows if not row.missing]
    bins, no_bpm = bpm_histogram((row.bpm for row in present), bpm_bin_width)
    keys, no_key = camelot_distribution(row.camelot_key for row in present)
    mtimes = mtimes or {}
    months = added_per_month(mtimes[row.path] for row in present if row.path in mtimes)
    most_played: tuple[PlayedTrack, ...] | None = None
    never: int | None = None
    played: int | None = None
    if plays is not None:
        hits = [
            (row, plays[row.path])
            for row in present
            if row.path in plays and plays[row.path].play_count > 0
        ]
        hits.sort(
            key=lambda pair: (-pair[1].play_count, _track_label(pair[0]).casefold())
        )
        most_played = tuple(
            PlayedTrack(
                row.path, _track_label(row), track.play_count, track.last_played
            )
            for row, track in hits[: max(top_played, 0)]
        )
        played = len(hits)
        never = len(present) - played
    return LibraryStats(
        total=len(present),
        missing=len(all_rows) - len(present),
        by_category=count_categories(present),
        by_genre=count_genres(present),
        bpm_histogram=bins,
        no_bpm=no_bpm,
        by_camelot=keys,
        no_key=no_key,
        added_per_month=months,
        most_played=most_played,
        never_played=never,
        played=played,
    )
