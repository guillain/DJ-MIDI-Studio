"""Discard duplicate copies to the Trash (issue #208, follow-up of #184).

`duplicates` only finds groups; this module acts on the copies the DJ
ticked in the Duplicate tracks window:

- `plan_discard` pairs every ticked copy with a copy that stays (the first
  unticked file of the first group listing it, exact-copy groups before
  same-artist+title ones) and lists every group that would keep **no** file
  -- the GUI refuses the whole operation then, so a track can never vanish
  from the library by ticking all of its copies. Version groups
  (`TIER_VERSIONS`, issue #257) are ignored: another version of a song is
  a suggestion, never a "copy" to keep in a discarded file's place.
- `move_to_trash` hands each copy to an injected `trash` callable -- the GUI
  passes `QFile.moveToTrash`, so files go to the system Trash and can be
  put back; nothing here ever deletes a file itself -- and flags each moved
  copy `missing` in the index, like a scan would.
- `repoint_playlists` points this app's playlists at the kept copy, reusing
  `LibraryDB.relink_tracks` (#190): the missing row folds into the kept
  one, so it also leaves the index. Serato/Traktor/Rekordbox files are
  never written.

Qt-free, so the decisions are testable without a `QApplication`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .db import LibraryDB
from .duplicates import TIER_EXACT, TIER_VERSIONS, DuplicateGroup


@dataclass(frozen=True)
class DiscardPlan:
    discards: tuple[tuple[str, str], ...]
    """``(copy to discard, copy kept in its place)``, in tick order."""
    refused: tuple[DuplicateGroup, ...] = ()
    """Groups every one of whose files is ticked: nothing may be moved."""

    @property
    def ok(self) -> bool:
        return bool(self.discards) and not self.refused


@dataclass
class TrashResult:
    moved: list[tuple[str, str]] = field(default_factory=list)
    """``(discarded copy, kept copy)`` actually moved to the Trash."""
    failed: list[tuple[str, str]] = field(default_factory=list)
    """``(path, reason)`` left where it was."""


def plan_discard(groups: Iterable[DuplicateGroup], discard_paths: Iterable[str]) -> DiscardPlan:
    """Pair each path of `discard_paths` with a kept copy; see module docstring."""
    ordered = sorted(
        (group for group in groups if group.tier != TIER_VERSIONS), key=lambda group: group.tier != TIER_EXACT
    )
    ticked = list(dict.fromkeys(str(path) for path in discard_paths))
    ticked_set = set(ticked)
    refused = tuple(group for group in ordered if ticked_set.intersection(group.paths) and ticked_set >= set(group.paths))
    discards: list[tuple[str, str]] = []
    for path in ticked:
        kept = next(
            (
                other
                for group in ordered
                if path in group.paths
                for other in group.paths
                if other not in ticked_set
            ),
            None,
        )
        if kept is not None:
            discards.append((path, kept))
    return DiscardPlan(discards=tuple(discards), refused=refused)


def move_to_trash(db: LibraryDB, plan: DiscardPlan, trash: Callable[[str], bool]) -> TrashResult:
    """Move every planned copy to the Trash and flag it missing.

    `trash(path)` returns True when the file went to the Trash. A refused
    plan moves nothing; a copy whose file or kept copy is gone, or that
    `trash` couldn't move (False or OSError), is reported in `failed` and
    the others still go."""
    result = TrashResult()
    if plan.refused:
        result.failed.extend((path, "its group would keep no copy") for path, _kept in plan.discards)
        return result
    for path, kept in plan.discards:
        if not Path(path).is_file():
            result.failed.append((path, "file not found"))
            continue
        if not Path(kept).is_file():
            result.failed.append((path, f"the kept copy is gone: {kept}"))
            continue
        try:
            moved = trash(path)
        except OSError as exc:
            result.failed.append((path, str(exc)))
            continue
        if not moved or Path(path).exists():
            result.failed.append((path, "could not move it to the Trash"))
            continue
        result.moved.append((path, kept))
    db.mark_paths_missing(path for path, _kept in result.moved)
    return result


def playlists_referencing(db: LibraryDB, moved: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Playlist names listing each discarded copy (copies no playlist lists
    are left out)."""
    return db.playlists_containing(path for path, _kept in moved)


def repoint_playlists(db: LibraryDB, moved: Iterable[tuple[str, str]]) -> int:
    """Point this app's playlists at each kept copy instead of the discarded
    one, via `LibraryDB.relink_tracks`. Returns how many copies were
    repointed (a copy no longer missing, or whose kept copy isn't indexed
    and present, is skipped).

    A playlist that listed both the discarded and the kept copy keeps only
    the first of them (as the kept copy), so the track isn't listed twice;
    `relink_tracks` itself is unchanged for #190's relinking."""
    links: list[tuple[int, str, int, int, float]] = []
    kept_for: dict[str, str] = {}
    for path, kept in moved:
        gone = db.get_track_by_path(path)
        target = db.get_track_by_path(kept)
        if gone is None or not gone.missing or target is None or target.missing:
            continue
        links.append((gone.id, target.path, target.root_id, target.size, target.mtime))
        kept_for[path] = target.path
    # Playlists listing a discarded copy next to its kept copy, collapsed
    # before relinking (afterwards both entries would read the kept path).
    collapsed: dict[int, list[str]] = {}
    for playlist in db.list_playlists():
        paths = db.playlist_paths(playlist.id)
        listed = set(paths)
        if not any(path in listed and kept in listed for path, kept in kept_for.items()):
            continue
        merged: list[str] = []
        seen: set[str] = set()
        for entry in paths:
            kept = kept_for.get(entry)
            if kept is None and entry not in kept_for.values():
                merged.append(entry)
                continue
            target = kept or entry
            if target not in seen:
                seen.add(target)
                merged.append(target)
        collapsed[playlist.id] = merged
    applied = db.relink_tracks(links)
    for playlist_id, paths in collapsed.items():
        db.set_playlist_paths(playlist_id, paths)
    return applied


__all__ = [
    "DiscardPlan",
    "TrashResult",
    "move_to_trash",
    "plan_discard",
    "playlists_referencing",
    "repoint_playlists",
]
