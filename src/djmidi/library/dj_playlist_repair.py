"""Repair the DJ's Serato crates and Traktor playlists: entries whose file is
gone are pointed at the file that replaced it.

Two cases, one tool: a duplicate moved to the Trash (the copy kept takes its
place) and a track missing from a playlist (found again in the library by the
same file name, or the same title and artist, when exactly one file fits).

This module only reads: it finds the dangling entries and, for each, the one
file that replaces it, as ``(missing path, new path)`` pairs. Writing goes
through `dj_playlists` (issue #458): refused while the software runs, a
preview, every file backed up, only playlist references changed, a Traktor
entry repointed only to a track in Traktor's collection.

Qt-free; locations, existence and processes are injectable for tests.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import traktor_library, workspace

SERATO, TRAKTOR = "serato", "traktor"
HOW_KEPT = "replaced in this app"  # a trashed duplicate's kept copy, or a file renamed or moved here
HOW_NAME = "same file name"
HOW_TAGS = "same title and artist"


@dataclass(frozen=True)
class Dangling:
    software: str
    file: Path  # the crate, or collection.nml
    playlist: str
    path: str  # the file the entry names, on this computer


@dataclass(frozen=True)
class Fix:
    entry: Dangling
    new_path: str
    how: str


@dataclass
class RepairPlan:
    fixes: list[Fix] = field(default_factory=list)
    unresolved: list[tuple[Dangling, str]] = field(default_factory=list)  # (entry, why)


# -- where things are -------------------------------------------------------


def dj_home() -> Path:
    """The home folder holding Music/_Serato_ and Documents/Native
    Instruments (`DJMIDI_DJ_HOME` overrides it: tests never read the real one)."""
    override = os.environ.get("DJMIDI_DJ_HOME")
    return Path(override) if override else Path.home()


def serato_crates(home: Path | None = None) -> list[Path]:
    folder = (home or Path.home()) / "Music" / "_Serato_" / "Subcrates"
    return sorted(folder.glob("*.crate")) if folder.is_dir() else []


def traktor_collection(home: Path | None = None) -> Path | None:
    """The newest Traktor version folder's collection.nml."""
    native = (home or Path.home()) / "Documents" / "Native Instruments"
    if not native.is_dir():
        return None
    found = [folder / "collection.nml" for folder in native.glob("Traktor*") if (folder / "collection.nml").is_file()]
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


# -- what's missing ---------------------------------------------------------


def find_dangling(
    crates: Iterable[Path],
    collection: Path | None,
    exists: Callable[[str], bool] = os.path.exists,
) -> list[Dangling]:
    """Every crate / playlist entry whose file is not there."""
    found: list[Dangling] = []
    for crate in crates:
        name = crate.stem.replace("%%", " › ")  # Serato's sub-crate separator
        try:
            paths = workspace.read_serato_crate(crate)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for path in dict.fromkeys(paths):
            if not exists(path):
                found.append(Dangling(SERATO, crate, name, path))
    if collection is not None:
        for playlist, keys in traktor_library.parse_playlists(collection).items():
            for path in dict.fromkeys(workspace.traktor_key_to_path(key) for key in keys):
                if not exists(path):
                    found.append(Dangling(TRAKTOR, collection, playlist, path))
    return found


@dataclass(frozen=True)
class LibraryTrack:
    path: str
    title: str | None
    artist: str | None
    missing: bool = False


def _tags(track: LibraryTrack) -> tuple[str, str] | None:
    if not track.title or not track.artist:
        return None
    return track.title.strip().casefold(), track.artist.strip().casefold()


def find_fixes(
    dangling: Iterable[Dangling],
    library: Iterable[LibraryTrack],
    kept_for: Mapping[str, str] | None = None,
    exists: Callable[[str], bool] = os.path.exists,
) -> RepairPlan:
    """A file for each dangling entry, when there is exactly one good one.

    ``kept_for`` maps a duplicate moved to the Trash to the copy kept;
    ``library`` gives present tracks and, for missing ones, the tags the
    index still remembers."""
    kept_for = dict(kept_for or {})
    tracks = list(library)
    present = [track for track in tracks if not track.missing]
    by_name: dict[str, list[str]] = {}
    by_tags: dict[tuple[str, str], list[str]] = {}
    for track in present:
        by_name.setdefault(Path(track.path).name.casefold(), []).append(track.path)
        if (tags := _tags(track)) is not None:
            by_tags.setdefault(tags, []).append(track.path)
    remembered = {track.path: _tags(track) for track in tracks if track.missing}
    plan = RepairPlan()
    for entry in dangling:
        if entry.path in kept_for:
            new_path, how, hops = kept_for[entry.path], HOW_KEPT, 0
            while not exists(new_path) and new_path in kept_for and hops < 20:  # renamed, then trashed…
                new_path, hops = kept_for[new_path], hops + 1
            if not exists(new_path):
                plan.unresolved.append((entry, f"its replacement is gone too: {new_path}"))
                continue
        else:
            names = by_name.get(Path(entry.path).name.casefold(), [])
            tags = remembered.get(entry.path)
            same_tags = by_tags.get(tags, []) if tags else []
            if len(names) == 1:
                new_path, how = names[0], HOW_NAME
            elif len(same_tags) == 1:
                new_path, how = same_tags[0], HOW_TAGS
            else:
                why = "several files could be it" if names or same_tags else "not found in your library"
                plan.unresolved.append((entry, why))
                continue
        plan.fixes.append(Fix(entry, new_path, how))
    return plan


def replaced_files(db) -> dict[str, str]:
    """From this app's change history: each duplicate moved to the Trash ->
    the copy kept, each file it renamed or moved -> its new path (newest
    change wins, reverted changes are skipped)."""
    from .change_log import KIND_RENAME, KIND_TRASH

    replaced: dict[str, str] = {}
    for record in reversed(db.list_changes()):
        if record.reverted_at is not None or record.kind not in (KIND_TRASH, KIND_RENAME):
            continue
        full = db.get_change(record.id)
        for item in full.items if full is not None else ():
            old = str(item.before.get("path", ""))
            new = item.before.get("kept") if record.kind == KIND_TRASH else item.after.get("path")
            if old and new:
                replaced[old] = str(new)
    return replaced


__all__ = [
    "HOW_KEPT",
    "HOW_NAME",
    "HOW_TAGS",
    "SERATO",
    "TRAKTOR",
    "Dangling",
    "Fix",
    "LibraryTrack",
    "RepairPlan",
    "dj_home",
    "find_dangling",
    "find_fixes",
    "replaced_files",
    "serato_crates",
    "traktor_collection",
]
