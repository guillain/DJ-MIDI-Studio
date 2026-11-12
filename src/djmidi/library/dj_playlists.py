"""Point Serato crates and Traktor playlists at a kept duplicate (issue #458).

The one place this app writes a DJ software's own playlist files, and only
when the DJ asks for it, per software, after a preview:

- **Serato**: every ``.crate`` in the chosen folder (``_Serato_/Subcrates``).
  Each crate's chunks are rebuilt as read; only the ``ptrk`` paths of
  dropped copies change (stored relative to the crate's volume, as Serato
  does), an entry whose kept copy the crate already lists is dropped (each
  track once), every other chunk (``vrsn``, ``osrt``, ``ovct``…) stays
  byte-identical. A crate that wouldn't round-trip byte for byte is left
  alone.
- **Traktor**: ``collection.nml``. Only ``PRIMARYKEY`` ``KEY`` attributes
  after ``<PLAYLISTS>`` change, as text: the collection, cue points and
  analysis are never touched. A dropped copy is repointed only when its
  kept copy is in Traktor's collection (a playlist entry refers to a
  collection entry).

Refused while that software runs (it would overwrite the files when it
quits). Every file is copied to a backup folder before it is replaced
(through a ``.part`` file). Qt-free.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from djmidi.i18n import QT_TRANSLATE_NOOP
from djmidi.library.serato_library import iter_chunks, write_chunks
from djmidi.library.traktor_library import parse_collection
from djmidi.library.workspace import traktor_location, volume_root

SERATO, TRAKTOR = "serato", "traktor"
# Fragments of the process names, matched case-insensitively.
PROCESS_NAMES = {SERATO: ("serato dj",), TRAKTOR: ("traktor",)}


@dataclass
class FileChange:
    path: Path
    replaced: int  # entries pointed at a kept copy
    removed: int = 0  # entries dropped because the kept copy was listed already
    data: bytes = b""


@dataclass
class Plan:
    software: str
    changes: list[FileChange] = field(default_factory=list)
    # dropped path -> why it was left alone (kept copy unknown to the software…)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def entries(self) -> int:
        return sum(change.replaced for change in self.changes)


def running_processes() -> list[str]:
    """Names of the running processes ([] when they can't be listed)."""
    command = ["tasklist", "/fo", "csv", "/nh"] if sys.platform == "win32" else ["ps", "-axo", "comm="]
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip().strip('"').split('","')[0] for line in output.splitlines() if line.strip()]


def is_running(software: str, processes: Callable[[], list[str]] = running_processes) -> bool:
    fragments = PROCESS_NAMES[software]
    return any(fragment in Path(name).name.lower() for name in processes() for fragment in fragments)


# --- Serato -----------------------------------------------------------------


def _stored(path: str, root: Path) -> str | None:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return None  # another volume: a crate can't list it


def _crate_change(crate: Path, kept_for: Mapping[str, str]) -> tuple[FileChange | None, dict[str, str]]:
    data = crate.read_bytes()
    chunks = list(iter_chunks(data))
    if write_chunks(chunks) != data:
        return None, {}  # not a plain chunk stream: leave it alone
    root = volume_root(crate.resolve())

    def absolute(stored: str) -> str:
        candidate = PurePosixPath(stored)
        return str(Path(stored) if Path(stored).is_absolute() else root / candidate)

    kept_paths = set(kept_for.values())
    out: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    replaced = removed = 0
    skipped: dict[str, str] = {}
    for tag, value in chunks:
        inner = list(iter_chunks(value)) if tag == "otrk" else []
        paths = [absolute(v.decode("utf-16-be")) for t, v in inner if t == "ptrk"]
        if not paths:
            out.append((tag, value))
            continue
        path = target = paths[0]
        stored = None
        if path in kept_for:
            stored = _stored(kept_for[path], root)
            if stored is None:
                skipped[path] = QT_TRANSLATE_NOOP("DjPlaylists", "the kept copy is on another drive than the crate")
            else:
                target = kept_for[path]
        if target in kept_paths and target in seen:
            removed += 1  # the kept copy is listed already: each track once
            continue
        seen.add(target)
        if stored is None:
            out.append((tag, value))
            continue
        out.append((tag, write_chunks([(t, stored.encode("utf-16-be") if t == "ptrk" else v) for t, v in inner])))
        replaced += 1
    if not replaced and not removed:
        return None, skipped
    return FileChange(crate, replaced, removed, write_chunks(out)), skipped


def plan_serato(crates_dir: str | os.PathLike[str], pairs: Iterable[tuple[str, str]]) -> Plan:
    kept_for = {dropped: kept for dropped, kept in pairs if dropped != kept}
    plan = Plan(SERATO)
    for crate in sorted(Path(crates_dir).glob("*.crate")):
        try:
            change, skipped = _crate_change(crate, kept_for)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        plan.skipped.update(skipped)
        if change is not None:
            plan.changes.append(change)
    return plan


# --- Traktor ----------------------------------------------------------------

_KEY_RE = re.compile(rb'(<PRIMARYKEY\b[^>]*?\bKEY=")([^"]*)(")')


def _key(path: str, volumes_dir: str | os.PathLike[str]) -> str:
    volume, directory, filename = traktor_location(path, volumes_dir)
    return f"{volume}{directory}{filename}"


def _escape(text: str) -> bytes:
    return html.escape(text, quote=True).replace("&#x27;", "'").encode("utf-8")


def plan_traktor(
    nml_path: str | os.PathLike[str], pairs: Iterable[tuple[str, str]], volumes_dir: str | os.PathLike[str] = "/Volumes"
) -> Plan:
    nml = Path(nml_path)
    plan = Plan(TRAKTOR)
    known = {track.key for track in parse_collection(nml)}
    new_key: dict[str, str] = {}
    for dropped, kept in pairs:
        if dropped == kept:
            continue
        kept_key = _key(kept, volumes_dir)
        if kept_key not in known:
            plan.skipped[dropped] = QT_TRANSLATE_NOOP("DjPlaylists", "the kept copy is not in Traktor's collection")
            continue
        new_key[_key(dropped, volumes_dir)] = kept_key
    data = nml.read_bytes()
    start = data.find(b"<PLAYLISTS")
    if start < 0 or not new_key:
        return plan
    replaced = 0

    def swap(match: re.Match) -> bytes:
        nonlocal replaced
        key = html.unescape(match.group(2).decode("utf-8"))
        if key not in new_key:
            return match.group(0)
        replaced += 1
        return match.group(1) + _escape(new_key[key]) + match.group(3)

    tail = _KEY_RE.sub(swap, data[start:])
    if replaced:
        plan.changes.append(FileChange(nml, replaced, 0, data[:start] + tail))
    return plan


# --- applying ---------------------------------------------------------------


def apply(plan: Plan, backup_root: str | os.PathLike[str], now: datetime | None = None) -> Path | None:
    """Backs every file up under ``backup_root/<software>-<stamp>/`` then
    replaces it. Returns the backup folder (None when nothing changed)."""
    if not plan.changes:
        return None
    stamp = (now or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
    backup = Path(backup_root) / f"{plan.software}-playlists-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for change in plan.changes:
        shutil.copy2(change.path, backup / change.path.name)
    for change in plan.changes:
        part = change.path.with_name(change.path.name + ".part")
        part.write_bytes(change.data)
        part.replace(change.path)
    return backup


__all__ = [
    "PROCESS_NAMES",
    "SERATO",
    "TRAKTOR",
    "FileChange",
    "Plan",
    "apply",
    "is_running",
    "plan_serato",
    "plan_traktor",
    "running_processes",
]
