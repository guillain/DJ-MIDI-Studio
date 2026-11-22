"""Copy a playlist and its music to a drive, with a playlist file that points
at the copies (issue #454).

The DJ takes a USB stick or a removable disk to another computer: the music
files are **copied** (never moved, the collection is untouched) into one
folder per playlist on the drive, and a Traktor playlist (``.nml``, the shape
this app already writes for Traktor's Import Playlist) is written next to them,
pointing at the copies on that drive. Serato and rekordbox drive layouts are
not written: their on-drive format isn't documented in this project yet.

Real-world drive rules: names safe on FAT32/exFAT (no ``<>:"/\\|?*``, no
trailing dot or space, at most 255 characters), two tracks with the same name
get ``name (2).mp3``, a file already copied (same size) is skipped so an
interrupted copy resumes, every copy goes through a ``.part`` file, and the
space needed is checked before anything is written. FAT32 can't hold a file of
4 GiB or more: such a file is reported, not copied.

Qt-free; `copy` is a generator a GUI advances one file at a time.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass, field
from pathlib import Path

FOLDER = "DJ MIDI Studio"  # everything this app writes on the drive lives here
FAT32_MAX = 4 * 1024**3 - 1
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_NAME = 255


def safe_name(name: str, fallback: str = "untitled") -> str:
    """A file or folder name every removable drive accepts."""
    cleaned = _UNSAFE.sub("_", name).rstrip(" .")
    if not cleaned.strip(" ._"):
        cleaned = fallback
    stem, dot, suffix = cleaned.rpartition(".") if "." in cleaned else (cleaned, "", "")
    if len(cleaned) > _MAX_NAME:
        keep = _MAX_NAME - len(dot + suffix)
        cleaned = stem[:keep].rstrip(" .") + dot + suffix
    return cleaned


@dataclass(frozen=True)
class CopyItem:
    source: str
    target: Path
    size: int
    present: bool = False  # already on the drive with the same size: skipped


@dataclass
class DrivePlan:
    folder: Path  # the playlist's folder on the drive
    playlist_file: Path  # the .nml written there
    items: list[CopyItem] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # sources not on disk
    too_big: list[str] = field(default_factory=list)  # >= 4 GiB (FAT32)
    free: int | None = None  # bytes free on the drive

    @property
    def to_copy(self) -> list[CopyItem]:
        return [item for item in self.items if not item.present]

    @property
    def needed(self) -> int:
        return sum(item.size for item in self.to_copy)

    @property
    def fits(self) -> bool:
        return self.free is None or self.needed <= self.free


def plan(
    drive: str | os.PathLike[str],
    playlist_name: str,
    sources: Iterable[str],
    *,
    disk_usage: Callable[[str], object] = shutil.disk_usage,
    fat32: bool = True,
) -> DrivePlan:
    """What copying ``sources`` (playlist order, duplicates once) to
    ``drive/DJ MIDI Studio/<playlist>/`` means: names, sizes, what's there."""
    folder = Path(drive) / FOLDER / safe_name(playlist_name, "playlist")
    result = DrivePlan(folder, folder / (safe_name(playlist_name, "playlist") + ".nml"))
    taken: set[str] = set()
    for source in dict.fromkeys(str(path) for path in sources):
        path = Path(source)
        if not path.is_file():
            result.missing.append(source)
            continue
        size = path.stat().st_size
        if fat32 and size > FAT32_MAX:
            result.too_big.append(source)
            continue
        name = safe_name(path.name)
        stem, suffix = os.path.splitext(name)
        number = 2
        while name.casefold() in taken:  # drives often ignore case
            name = f"{stem} ({number}){suffix}"
            number += 1
        taken.add(name.casefold())
        target = folder / name
        present = target.is_file() and target.stat().st_size == size
        result.items.append(CopyItem(source, target, size, present))
    try:
        result.free = int(disk_usage(str(Path(drive))).free)
    except OSError:
        result.free = None
    return result


def copy(drive_plan: DrivePlan) -> Generator[CopyItem, None, list[tuple[str, str]]]:
    """Copies each file not already there (through ``.part``), yielding it
    when done; returns ``(source, error)`` for the files that failed."""
    drive_plan.folder.mkdir(parents=True, exist_ok=True)
    failed: list[tuple[str, str]] = []
    for item in drive_plan.to_copy:
        part = item.target.with_name(item.target.name + ".part")
        try:
            shutil.copy2(item.source, part)
            os.replace(part, item.target)
        except OSError as exc:
            failed.append((item.source, str(exc)))
            part.unlink(missing_ok=True)
            continue
        yield item
    return failed


def copied_paths(drive_plan: DrivePlan) -> list[str]:
    """The copies on the drive, in playlist order (what the playlist lists)."""
    return [str(item.target) for item in drive_plan.items if item.target.is_file()]


__all__ = ["FAT32_MAX", "FOLDER", "CopyItem", "DrivePlan", "copied_paths", "copy", "plan", "safe_name"]
