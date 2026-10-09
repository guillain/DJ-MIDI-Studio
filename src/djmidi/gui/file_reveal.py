"""Show a file in the system file manager (Finder on macOS)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def reveal_in_file_manager(path: str | Path) -> None:
    """Select `path` in Finder / Explorer; elsewhere open its folder."""
    target = Path(path)
    if sys.platform == "darwin" and target.exists():
        subprocess.run(["open", "-R", str(target)], check=False)
    elif sys.platform == "win32" and target.exists():
        subprocess.run(["explorer", "/select,", str(target)], check=False)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent if target.is_file() else target)))


__all__ = ["reveal_in_file_manager"]
