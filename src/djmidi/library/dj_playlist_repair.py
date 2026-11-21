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

Paths are compared the way `playlist_compare.path_key` does (a crate may
spell "Café" composed while macOS hands the library a decomposed name).

Qt-free; locations, existence and processes are injectable for tests.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import traktor_library, workspace
from .playlist_compare import path_key

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
    folder = (home or dj_home()) / "Music" / "_Serato_" / "Subcrates"
    return sorted(folder.glob("*.crate")) if folder.is_dir() else []


def traktor_collection(home: Path | None = None) -> Path | None:
    """The newest Traktor version folder's collection.nml."""
    native = (home or dj_home()) / "Documents" / "Native Instruments"
    if not native.is_dir():
        return None
    found = [folder / "collection.nml" for folder in native.glob("Traktor*") if (folder / "collection.nml").is_file()]
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


# -- what's missing ---------------------------------------------------------


def _traktor_path(key: str, boot_volume: str, exists: Callable[[str], bool]) -> str:
    """The file a Traktor ``PRIMARYKEY`` names. `workspace.traktor_key_to_path`
    puts a file it can't find on the boot disk; a missing file of another
    drive keeps that drive here (``/Volumes/<drive>/…``, or ``D:\\…``), so the
    entry shows where it was and `dj_playlists` finds the same key again."""
    path = workspace.traktor_key_to_path(key)
    volume, separator, _rest = key.partition("/:")
    if not separator or not volume or volume == boot_volume or path.startswith("/Volumes/") or exists(path):
        return path
    if len(volume) == 2 and volume[1] == ":":  # a Windows drive letter
        return str(Path(volume + path))
    return str(Path("/Volumes", volume, path.lstrip("/")))


def find_dangling(
    crates: Iterable[Path],
    collection: Path | None,
    exists: Callable[[str], bool] = os.path.exists,
    only_paths: Iterable[str] | None = None,
    volumes_dir: str | os.PathLike[str] = "/Volumes",
) -> list[Dangling]:
    """Every crate / playlist entry whose file is not there; with
    ``only_paths``, only entries naming one of those files (the others are
    not even looked up). An unreadable crate is skipped; an unreadable
    collection.nml raises (`OSError`, `xml.etree.ElementTree.ParseError`)."""
    wanted = None if only_paths is None else {path_key(path) for path in only_paths}

    def missing(path: str) -> bool:
        return (wanted is None or path_key(path) in wanted) and not exists(path)

    found: list[Dangling] = []
    for crate in crates:
        name = crate.stem.replace("%%", " › ")  # Serato's sub-crate separator
        try:
            paths = workspace.read_serato_crate(crate)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for path in dict.fromkeys(paths):
            if missing(path):
                found.append(Dangling(SERATO, crate, name, path))
    if collection is not None:
        playlists = traktor_library.iter_playlists(collection)  # two "Friday" folders: both
        boot = workspace.boot_volume_name(volumes_dir)
        for playlist, keys in playlists:
            for path in dict.fromkeys(_traktor_path(key, boot, exists) for key in keys):
                if missing(path):
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


def _name(path: str) -> str:
    return Path(path_key(path)).name.casefold()


def find_fixes(
    dangling: Iterable[Dangling],
    library: Iterable[LibraryTrack],
    kept_for: Mapping[str, str] | None = None,
    exists: Callable[[str], bool] = os.path.exists,
) -> RepairPlan:
    """A file for each dangling entry, when there is exactly one good one.

    ``kept_for`` maps a duplicate moved to the Trash to the copy kept;
    ``library`` gives present tracks and, for missing ones, the tags the
    index still remembers. A file found by name or tags must still be there
    (the index may not have been rescanned) and be another file; a file of
    the same name tagged as another song than the one the index remembers is
    not it; two different missing tracks are never both given one file that
    way (two albums' "01 Intro.mp3"): neither is guessed."""
    kept = {path_key(old): new for old, new in (kept_for or {}).items()}
    by_name: dict[str, list[str]] = {}
    by_tags: dict[tuple[str, str], list[str]] = {}
    remembered: dict[str, tuple[str, str] | None] = {}
    tagged: dict[str, tuple[str, str]] = {}  # present files' title + artist
    for track in library:
        if track.missing:
            remembered[path_key(track.path)] = _tags(track)
            continue
        by_name.setdefault(_name(track.path), []).append(track.path)
        if (tags := _tags(track)) is not None:
            by_tags.setdefault(tags, []).append(track.path)
            tagged[path_key(track.path)] = tags

    def still_there(paths: list[str], key: str) -> list[str]:
        return [path for path in paths if path_key(path) != key and exists(path)]

    plan = RepairPlan()
    guessed: dict[str, set[str]] = {}  # a file found by name or tags -> the missing files it would replace
    for entry in dangling:
        key = path_key(entry.path)
        if key in kept:
            new_path, how, hops = kept[key], HOW_KEPT, 0
            while not exists(new_path) and path_key(new_path) in kept and hops < 20:  # renamed, then trashed…
                new_path, hops = kept[path_key(new_path)], hops + 1
            if not exists(new_path):
                plan.unresolved.append((entry, f"its replacement is gone too: {new_path}"))
                continue
        else:
            tags = remembered.get(key)
            names = [
                path
                for path in still_there(by_name.get(_name(entry.path), []), key)
                if not tags or tagged.get(path_key(path), tags) == tags  # "01.mp3" of another album: not it
            ]
            same_tags = still_there(by_tags.get(tags, []), key) if tags else []
            if len(names) == 1:
                new_path, how = names[0], HOW_NAME
            elif len(same_tags) == 1:
                new_path, how = same_tags[0], HOW_TAGS
            else:
                why = "several files could be it" if names or same_tags else "not found in your library"
                plan.unresolved.append((entry, why))
                continue
            guessed.setdefault(path_key(new_path), set()).add(key)
        plan.fixes.append(Fix(entry, new_path, how))
    shared = {target for target, missing in guessed.items() if len(missing) > 1}
    if shared:
        fixes, plan.fixes = plan.fixes, []
        for fix in fixes:
            if fix.how != HOW_KEPT and path_key(fix.new_path) in shared:
                plan.unresolved.append((fix.entry, "another missing track would get the same file"))
            else:
                plan.fixes.append(fix)
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
