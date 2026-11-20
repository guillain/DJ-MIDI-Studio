"""Which DJ programs this computer has, and which one is running.

The Dashboard's "Your setup" names the DJ software next to the controllers,
so the DJ sees their whole setup at once. Only the programs the app has a
plugin for (Serato, Traktor, rekordbox, Mixxx) are looked for. A program
counts as found when its application sits in the usual applications folder
or its own data folder exists in the home folder; nothing is opened or
written, and folders are matched by name pattern, not by exact install path.

Qt-free. Every location is injectable so tests never look at the real disk.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DjProgram:
    id: str  # the software plugin id
    name: str
    pattern: re.Pattern[str]  # an application or install folder name
    data_dirs: tuple[str, ...]  # relative to the home folder; any one existing counts


PROGRAMS = (
    DjProgram("serato", "Serato DJ", re.compile(r"^Serato DJ", re.IGNORECASE), ("Music/_Serato_",)),
    DjProgram("traktor", "Traktor", re.compile(r"^Traktor", re.IGNORECASE), ("Documents/Native Instruments",)),
    DjProgram("rekordbox", "rekordbox", re.compile(r"^rekordbox", re.IGNORECASE), ()),
    DjProgram("mixxx", "Mixxx", re.compile(r"^Mixxx", re.IGNORECASE), ()),
)


@dataclass(frozen=True)
class FoundSoftware:
    id: str
    name: str
    running: bool


def _application_dirs() -> list[Path]:
    if sys.platform == "darwin":
        return [Path("/Applications"), Path.home() / "Applications"]
    if sys.platform.startswith("win"):
        return [Path(os.environ[key]) for key in ("ProgramFiles", "ProgramFiles(x86)") if os.environ.get(key)]
    return [Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt")]


def _names_under(folders: Iterable[Path], depth: int = 2) -> set[str]:
    """Entry names in ``folders`` and one level down (vendor folders such as
    "Native Instruments" hold the application)."""
    names: set[str] = set()
    for folder in folders:
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            names.add(entry.name)
            if depth > 1 and entry.is_dir() and not entry.name.endswith(".app"):
                try:
                    names.update(child.name for child in entry.iterdir())
                except OSError:
                    continue
    return names


def running_process_names() -> set[str]:
    """Names of the running programs (empty when the system won't say)."""
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=3, check=False).stdout
            return {line.split('","')[0].strip('"') for line in out.splitlines() if line}
        out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=3, check=False).stdout
        return {Path(line.strip()).name for line in out.splitlines()[1:] if line.strip()}
    except (OSError, subprocess.SubprocessError):
        return set()


def find_dj_software(
    *,
    home: Path | None = None,
    app_dirs: Iterable[Path] | None = None,
    running: Callable[[], set[str]] = running_process_names,
) -> list[FoundSoftware]:
    """The DJ programs found on this computer, running ones first."""
    home = home or Path.home()
    installed = _names_under(_application_dirs() if app_dirs is None else app_dirs)
    processes = running()
    found: list[FoundSoftware] = []
    for program in PROGRAMS:
        present = any(program.pattern.match(name) for name in installed) or any(
            (home / folder).is_dir() for folder in program.data_dirs
        )
        is_running = any(program.pattern.match(name) for name in processes)
        if present or is_running:
            found.append(FoundSoftware(program.id, program.name, is_running))
    return sorted(found, key=lambda software: not software.running)


__all__ = ["PROGRAMS", "DjProgram", "FoundSoftware", "find_dj_software", "running_process_names"]
