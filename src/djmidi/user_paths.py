"""The user's own DJ MIDI Studio folder (issue #175).

Everything the app creates for the user, as files they can see, back up and
share, lives under one visible folder -- ``~/Documents/DJ MIDI Studio`` by
default, ``DJMIDI_WORKSPACE`` to override it (tests point it at a temporary
folder). Mappings stay where the DJ software keeps them; only the app's own
files live here.
"""

from __future__ import annotations

import os
from pathlib import Path

CONTROLLERS = "Controllers"
SYNC = "Sync"
MACROS = "Macros"
DRAFTS = "Drafts"
LOGS = "Logs"
EXPORTS = "Exports"
SNAPSHOTS = "Snapshots"
SUBFOLDERS = (CONTROLLERS, SYNC, MACROS, DRAFTS, LOGS, EXPORTS, SNAPSHOTS)
_README = """DJ MIDI Studio -- your files

Controllers  controller profiles you installed from Controller Setup (JSON)
Sync         one initialization sync set per controller (JSON)
Macros       your MIDI macros, one per file (JSON)
Drafts       Controller Setup drafts you saved
Logs         Live Monitor logs you saved
Exports      playlists exported from the Music Library, cheat sheets (PDF)
Snapshots    named versions of your mappings, one folder per mapping

Your Serato / Traktor mappings are not here: they stay where your DJ
software keeps them, and DJ MIDI Studio remembers where they are.
"""


def workspace_dir() -> Path:
    override = os.environ.get("DJMIDI_WORKSPACE")
    return Path(override).expanduser() if override else Path.home() / "Documents" / "DJ MIDI Studio"


def controllers_dir() -> Path:
    """Installed controller profiles (JSON, plus their pictures)."""
    return workspace_dir() / CONTROLLERS


def subfolder(name: str) -> Path:
    return workspace_dir() / name


def sync_dir() -> Path:
    return subfolder(SYNC)


def macros_dir() -> Path:
    """MIDI macros (issue #228), one JSON file per macro."""
    return subfolder(MACROS)


def ensure_workspace() -> Path:
    """Create the folder and its subfolders (with a short README) if missing."""
    root = workspace_dir()
    for name in SUBFOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(_README, encoding="utf-8")
    return root


__all__ = [
    "CONTROLLERS",
    "DRAFTS",
    "EXPORTS",
    "LOGS",
    "MACROS",
    "SNAPSHOTS",
    "SUBFOLDERS",
    "SYNC",
    "controllers_dir",
    "ensure_workspace",
    "macros_dir",
    "subfolder",
    "sync_dir",
    "workspace_dir",
]
