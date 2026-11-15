"""Where the app's files are, and where file dialogs should start (issue #175).

Qt-free so it can be tested without a QApplication: the GUI keeps the
recent-mappings list in its own settings and asks this module what to do
with it, where to open a dialog, and where a mapping's previous version is.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

RECENT_LIMIT = 8


def push_recent(recents: Iterable[str], path: str | Path, limit: int = RECENT_LIMIT) -> list[str]:
    """`path` first, then the other recents in order, without duplicates."""
    first = str(Path(path))
    return [first, *(entry for entry in recents if entry != first)][:limit]


def existing_recents(recents: Iterable[str]) -> list[str]:
    """The recents that still exist on disk (a mapping may have moved)."""
    return [entry for entry in recents if Path(entry).is_file()]


def backup_path(mapping_path: str | Path) -> Path:
    """The previous version kept next to a mapping by every save
    (safe_update.prepare_update writes it before replacing the file)."""
    path = Path(mapping_path)
    return path.with_name(f"{path.name}.bak")


def _version_key(folder: Path) -> tuple[int, ...]:
    """"Traktor 4.10.0" sorts after "Traktor 4.9.1" (a plain string sort
    put it first)."""
    return tuple(int(part) for part in re.findall(r"\d+", folder.name))


def software_mapping_dirs(software_id: str | None, home: Path | None = None) -> list[Path]:
    """Where each DJ software keeps its MIDI mappings, most specific first."""
    home = home or Path.home()
    if software_id == "serato":
        return [home / "Music" / "_Serato_" / "MIDI" / "Xml", home / "Music" / "_Serato_"]
    if software_id == "traktor":
        # Traktor keeps "Traktor Settings.tsi" (and the user's exported
        # .tsi files) in the version folder itself, e.g. "Traktor 4.4.1";
        # its "Settings" subfolder only holds "Default Settings".
        native = home / "Documents" / "Native Instruments"
        versions = sorted(native.glob("Traktor*"), key=_version_key, reverse=True) if native.is_dir() else []
        return [*versions, native]
    return []


def mapping_start_dir(
    software_id: str | None,
    last_dir: str | Path | None = None,
    home: Path | None = None,
) -> Path:
    """The folder an Open/Save mapping dialog should start in: the last one
    used, else where the current software keeps its mappings (Serato first
    when nothing is known yet), else the home folder."""
    home = home or Path.home()
    if last_dir and Path(last_dir).is_dir():
        return Path(last_dir)
    candidates = software_mapping_dirs(software_id, home) or [
        *software_mapping_dirs("serato", home),
        *software_mapping_dirs("traktor", home),
    ]
    return next((candidate for candidate in candidates if candidate.is_dir()), home)


__all__ = [
    "RECENT_LIMIT",
    "backup_path",
    "existing_recents",
    "mapping_start_dir",
    "push_recent",
    "software_mapping_dirs",
]
