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


def workspace_dir() -> Path:
    override = os.environ.get("DJMIDI_WORKSPACE")
    return Path(override).expanduser() if override else Path.home() / "Documents" / "DJ MIDI Studio"


def controllers_dir() -> Path:
    """Installed controller profiles (JSON, plus their pictures)."""
    return workspace_dir() / CONTROLLERS


__all__ = ["CONTROLLERS", "controllers_dir", "workspace_dir"]
