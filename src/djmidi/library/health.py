"""Library health report (issue #225): files a DJ should look at.

One pass over the indexed, present tracks, strictly read-only: each file's
stream header and tags are read once with mutagen (no audio is decoded, no
file is written). A file can carry several problems at once; each is one
`HealthIssue` row:

- ``zero_length``: a 0-byte file, or one whose stream reports a 0 s
  duration. A 0-byte file is reported for that alone -- it has no header or
  tags to judge anything else by.
- ``unreadable``: mutagen can't parse it (corrupt header, truncated file,
  unsupported content behind an audio extension) or the OS refuses to open
  it. Nothing else is checked for such a file.
- ``empty_title`` / ``empty_artist``: the tag is missing or blank.
- ``no_artwork``: no embedded cover (ID3 ``APIC``, MP4 ``covr``, FLAC
  picture block, Vorbis ``metadata_block_picture``/``coverart``).
- ``low_bitrate``: the stream header reports at most `LOW_BITRATE_BPS`
  (128 kbps). Formats that report no bitrate are never flagged.

`iter_health_check` is a generator a GUI drives a slice at a time from a
`QTimer`, like `duplicates.iter_exact_duplicates`; `filter_issues` and
`write_csv` back the report window's filters and CSV export.
"""

from __future__ import annotations

import csv
import io
import logging
from collections import Counter
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import mutagen
from mutagen.id3 import ID3

from .db import LibraryDB
from .metadata import metadata_from_audio

_LOGGER = logging.getLogger(__name__)

LOW_BITRATE_BPS = 128_000

ISSUE_UNREADABLE = "unreadable"
ISSUE_ZERO_LENGTH = "zero_length"
ISSUE_EMPTY_TITLE = "empty_title"
ISSUE_EMPTY_ARTIST = "empty_artist"
ISSUE_NO_ARTWORK = "no_artwork"
ISSUE_LOW_BITRATE = "low_bitrate"

# Display order and labels, most serious first.
ISSUE_LABELS: dict[str, str] = {
    ISSUE_UNREADABLE: "Unreadable / corrupt",
    ISSUE_ZERO_LENGTH: "Zero length",
    ISSUE_EMPTY_TITLE: "Empty title",
    ISSUE_EMPTY_ARTIST: "Empty artist",
    ISSUE_NO_ARTWORK: "Missing artwork",
    ISSUE_LOW_BITRATE: "Low bitrate",
}
ISSUE_KINDS: tuple[str, ...] = tuple(ISSUE_LABELS)

CSV_HEADER = ("path", "issue", "detail")

_VORBIS_PICTURE_KEYS = ("metadata_block_picture", "coverart")


@dataclass(frozen=True)
class HealthIssue:
    path: str
    kind: str
    detail: str = ""

    @property
    def label(self) -> str:
        return ISSUE_LABELS.get(self.kind, self.kind)


@dataclass(frozen=True)
class HealthReport:
    checked: int
    """How many files were examined."""
    issues: tuple[HealthIssue, ...]

    def counts(self) -> dict[str, int]:
        """Issue count per kind, every kind present (0 when clean)."""
        found = Counter(issue.kind for issue in self.issues)
        return {kind: found.get(kind, 0) for kind in ISSUE_KINDS}

    @property
    def affected_files(self) -> int:
        return len({issue.path for issue in self.issues})


def has_artwork(audio: object) -> bool:
    """Whether an opened mutagen file embeds a cover picture."""
    if getattr(audio, "pictures", None):  # FLAC picture blocks
        return True
    tags = getattr(audio, "tags", None)
    if tags is None:
        return False
    if isinstance(tags, ID3):  # MP3, AIFF, WAV
        return bool(tags.getall("APIC") or tags.getall("PIC"))
    # Not `in tags`: Vorbis comments iterate as (key, value) pairs.
    keys = {str(key).lower() for key in tags.keys()}  # noqa: SIM118
    return "covr" in keys or any(key in keys for key in _VORBIS_PICTURE_KEYS)


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def check_file(path: str, size: int | None = None, low_bitrate: int = LOW_BITRATE_BPS) -> list[HealthIssue]:
    """Every problem found in one file (empty when healthy). `size` is the
    indexed size; the file is stat'ed when it isn't given."""
    if size is None:
        try:
            size = Path(path).stat().st_size
        except OSError as exc:
            return [HealthIssue(path, ISSUE_UNREADABLE, str(exc))]
    if size == 0:
        return [HealthIssue(path, ISSUE_ZERO_LENGTH, "0 bytes")]
    try:
        audio = mutagen.File(path)
    except (mutagen.MutagenError, OSError, ValueError, EOFError) as exc:
        return [HealthIssue(path, ISSUE_UNREADABLE, str(exc) or type(exc).__name__)]
    if audio is None:
        return [HealthIssue(path, ISSUE_UNREADABLE, "Not a recognized audio file")]
    issues: list[HealthIssue] = []
    info = getattr(audio, "info", None)
    length = getattr(info, "length", None)
    if length is not None and length <= 0:
        issues.append(HealthIssue(path, ISSUE_ZERO_LENGTH, "0 s duration"))
    metadata = metadata_from_audio(audio)
    if _blank(metadata.title):
        issues.append(HealthIssue(path, ISSUE_EMPTY_TITLE))
    if _blank(metadata.artist):
        issues.append(HealthIssue(path, ISSUE_EMPTY_ARTIST))
    if not has_artwork(audio):
        issues.append(HealthIssue(path, ISSUE_NO_ARTWORK))
    bitrate = getattr(info, "bitrate", None)
    if bitrate and bitrate <= low_bitrate:
        issues.append(HealthIssue(path, ISSUE_LOW_BITRATE, f"{round(bitrate / 1000)} kbps"))
    return issues


def iter_health_check(
    entries: Iterable[tuple[str, int | None]], low_bitrate: int = LOW_BITRATE_BPS
) -> Generator[int, None, HealthReport]:
    """Check `(path, size)` entries one file at a time.

    Yields the number of files checked so far and returns the
    `HealthReport` via ``StopIteration.value``. A file that raises anything
    unexpected is reported unreadable rather than aborting the pass."""
    issues: list[HealthIssue] = []
    checked = 0
    for path, size in entries:
        try:
            issues.extend(check_file(path, size, low_bitrate))
        except Exception as exc:  # noqa: BLE001 - one odd file must not stop the report
            _LOGGER.warning("Health check failed on %s: %s", path, exc)
            issues.append(HealthIssue(path, ISSUE_UNREADABLE, str(exc) or type(exc).__name__))
        checked += 1
        yield checked
    return HealthReport(checked=checked, issues=tuple(sort_issues(issues)))


def check_library(entries: Iterable[tuple[str, int | None]], low_bitrate: int = LOW_BITRATE_BPS) -> HealthReport:
    """Blocking `iter_health_check` (scripts, tests)."""
    steps = iter_health_check(entries, low_bitrate)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def health_entries(db: LibraryDB) -> list[tuple[str, int | None]]:
    """`(path, size)` for every present track of the index."""
    return [(record.path, record.size) for record in db.list_tracks(include_missing=False)]


def sort_issues(issues: Iterable[HealthIssue]) -> list[HealthIssue]:
    """Most serious kind first, then by path."""
    order = {kind: index for index, kind in enumerate(ISSUE_KINDS)}
    return sorted(issues, key=lambda issue: (order.get(issue.kind, len(order)), issue.path))


def filter_issues(
    issues: Iterable[HealthIssue], kinds: Iterable[str] | None = None, text: str = ""
) -> list[HealthIssue]:
    """Issues of the given kinds (all when None) whose path, label or detail
    contains `text` (case-insensitive)."""
    wanted = None if kinds is None else set(kinds)
    needle = text.strip().casefold()
    return [
        issue
        for issue in issues
        if (wanted is None or issue.kind in wanted)
        and (not needle or needle in f"{issue.path}\n{issue.label}\n{issue.detail}".casefold())
    ]


def write_csv(handle: TextIO, issues: Iterable[HealthIssue]) -> int:
    """Write `path,issue,detail` rows (issue = its display label); returns
    how many rows were written."""
    writer = csv.writer(handle)
    writer.writerow(CSV_HEADER)
    count = 0
    for issue in issues:
        writer.writerow((issue.path, issue.label, issue.detail))
        count += 1
    return count


def issues_to_csv(issues: Iterable[HealthIssue]) -> str:
    buffer = io.StringIO()
    write_csv(buffer, issues)
    return buffer.getvalue()


def export_csv(path: str | Path, issues: Iterable[HealthIssue]) -> int:
    """Write the CSV to `path` (UTF-8 with BOM so spreadsheet apps detect it)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        return write_csv(handle, issues)


__all__ = [
    "CSV_HEADER",
    "ISSUE_EMPTY_ARTIST",
    "ISSUE_EMPTY_TITLE",
    "ISSUE_KINDS",
    "ISSUE_LABELS",
    "ISSUE_LOW_BITRATE",
    "ISSUE_NO_ARTWORK",
    "ISSUE_UNREADABLE",
    "ISSUE_ZERO_LENGTH",
    "LOW_BITRATE_BPS",
    "HealthIssue",
    "HealthReport",
    "check_file",
    "check_library",
    "export_csv",
    "filter_issues",
    "has_artwork",
    "health_entries",
    "issues_to_csv",
    "iter_health_check",
    "sort_issues",
    "write_csv",
]
