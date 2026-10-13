"""Compare one of this app's playlists with a Serato crate or Traktor playlist (#229).

Read-only by design: this only compares two lists of track paths and never
writes anything -- syncing the other side stays a separate, explicit export.

Tracks are matched by path. Each side lists absolute paths (the caller turns
a crate's volume-relative paths or a Traktor ``PRIMARYKEY`` into one first,
see `workspace.read_serato_crate` / `workspace.read_traktor_playlists`), and
`path_key` only normalizes what is safe to normalize without touching the
filesystem: Unicode form (macOS file names often come back decomposed, NFD,
while a tag editor or another app wrote them composed, NFC) and redundant
separators/``.`` segments. Case is kept: a case-sensitive volume may hold two
files differing only by case.

A track listed twice is matched occurrence by occurrence: the second copy in
the app playlist pairs with the second copy on the other side, and an extra
copy with no counterpart is reported as being on one side only.

Order differences are reported as *moved* tracks: among the tracks both sides
share, the longest run that keeps the same relative order on both sides is
taken as "in place" (a longest increasing subsequence of the other side's
positions, read in app order), and every other shared track is a move. So a
missing or added track never makes the rest look reordered, and moving one
track flags that one track rather than everything between its two positions.
"""

from __future__ import annotations

import bisect
import os
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def path_key(path: str) -> str:
    """The form two paths are compared in: NFC Unicode, normalized separators."""
    return os.path.normpath(unicodedata.normalize("NFC", path))


@dataclass(frozen=True)
class ComparedTrack:
    """One track of a comparison. Positions are 1-based; `None` on the side
    that doesn't list it. `path` is as the app playlist lists it, else as the
    other side does."""

    path: str
    app_position: int | None
    other_position: int | None


@dataclass(frozen=True)
class PlaylistComparison:
    only_in_app: tuple[ComparedTrack, ...]
    only_in_other: tuple[ComparedTrack, ...]
    in_both: tuple[ComparedTrack, ...]
    """Shared tracks, in app-playlist order."""
    moved: tuple[ComparedTrack, ...]
    """The shared tracks out of order relative to the others, in app order."""

    @property
    def same_tracks(self) -> bool:
        return not self.only_in_app and not self.only_in_other

    @property
    def identical(self) -> bool:
        return self.same_tracks and not self.moved


def _occurrence_keys(paths: Iterable[str]) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    keys = []
    for path in paths:
        key = path_key(path)
        keys.append((key, seen.get(key, 0)))
        seen[key] = seen.get(key, 0) + 1
    return keys


def _longest_increasing(values: Sequence[int]) -> set[int]:
    """Indexes (into `values`) of one longest strictly increasing subsequence."""
    tails: list[int] = []  # index of the smallest tail of a run of length k + 1
    tail_values: list[int] = []  # values[tails[k]], kept alongside for bisect
    previous = [-1] * len(values)
    for index, value in enumerate(values):
        length = bisect.bisect_left(tail_values, value)
        if length > 0:
            previous[index] = tails[length - 1]
        if length == len(tails):
            tails.append(index)
            tail_values.append(value)
        else:
            tails[length] = index
            tail_values[length] = value
    kept: set[int] = set()
    index = tails[-1] if tails else -1
    while index >= 0:
        kept.add(index)
        index = previous[index]
    return kept


def compare_playlists(app_paths: Sequence[str], other_paths: Sequence[str]) -> PlaylistComparison:
    """Tracks only in the app playlist, only on the other side, and the
    shared tracks whose order differs (see the module docstring)."""
    app_keys = _occurrence_keys(app_paths)
    other_keys = _occurrence_keys(other_paths)
    other_position = {key: index for index, key in enumerate(other_keys)}
    app_set = set(app_keys)

    only_in_app = []
    in_both = []
    for index, key in enumerate(app_keys):
        if key in other_position:
            in_both.append(ComparedTrack(app_paths[index], index + 1, other_position[key] + 1))
        else:
            only_in_app.append(ComparedTrack(app_paths[index], index + 1, None))
    only_in_other = [
        ComparedTrack(other_paths[index], None, index + 1)
        for index, key in enumerate(other_keys)
        if key not in app_set
    ]
    in_place = _longest_increasing([track.other_position for track in in_both])
    moved = [track for index, track in enumerate(in_both) if index not in in_place]
    return PlaylistComparison(tuple(only_in_app), tuple(only_in_other), tuple(in_both), tuple(moved))
