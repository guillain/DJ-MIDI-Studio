"""Contextual help: a compact "?" button that explains the panel it sits in.

Every tab and tool window carries one or more of these next to the controls
they explain. Clicking one shows a short explanation and, when the panel has
a page in the bundled user documentation (docs/enduser/features/), an
"Open full guide" button that opens that page locally -- the same files the
Help menu opens, shipped with release builds.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QWidget

FEATURES_DIR = "docs/enduser/features"


def resource_root() -> Path:
    """Where bundled resources (docs/, controllers/) live: the PyInstaller
    bundle in a release build, the repository root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return Path(__file__).resolve().parents[3]


def guide_path(doc: str) -> Path:
    """The bundled feature page for `doc` (a file name in docs/enduser/features)."""
    return resource_root() / FEATURES_DIR / doc


def show_help(parent: QWidget, title: str, text: str, doc: str | None = None) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(f"<b>{title}</b>")
    box.setInformativeText(text)
    guide = box.addButton("Open full guide", QMessageBox.ButtonRole.ActionRole) if doc else None
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if guide is not None and box.clickedButton() is guide:
        path = guide_path(doc)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(parent, "Documentation unavailable", str(path))


def help_button(parent: QWidget, title: str, text: str, doc: str | None = None) -> QPushButton:
    """A compact "?" button opening `text` (rich text allowed) under `title`."""
    button = QPushButton("?", parent)
    button.setProperty("compact", True)
    button.setProperty("help", True)
    button.setFixedSize(24, 24)
    button.setToolTip(f"Help: {title}")
    button.setAccessibleName(f"Help: {title}")
    button.setCursor(Qt.CursorShape.WhatsThisCursor)
    button.clicked.connect(lambda: show_help(parent, title, text, doc))
    return button


def help_row(parent: QWidget, title: str, text: str, doc: str | None = None) -> QHBoxLayout:
    """A right-aligned row holding one help button, for the top of a group
    box (whose title bar can't host widgets)."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    row.addWidget(help_button(parent, title, text, doc))
    return row


__all__ = ["FEATURES_DIR", "guide_path", "help_button", "help_row", "resource_root", "show_help"]
