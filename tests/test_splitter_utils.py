"""Tests for gui/splitter_utils.py."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from djmidi.gui.splitter_utils import replace_splitter


def _make_container_with_splitter() -> tuple[QWidget, QSplitter]:
    container = QWidget()
    layout = QVBoxLayout(container)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    layout.addWidget(splitter)
    return container, splitter


def test_replace_splitter_returns_new_splitter():
    container, old = _make_container_with_splitter()
    new = replace_splitter(container, old)
    assert new is not old
    assert isinstance(new, QSplitter)


def test_replace_splitter_new_splitter_is_in_layout():
    container, old = _make_container_with_splitter()
    new = replace_splitter(container, old)
    layout = container.layout()
    widgets_in_layout = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
    assert new in widgets_in_layout


def test_replace_splitter_new_splitter_is_horizontal():
    container, old = _make_container_with_splitter()
    new = replace_splitter(container, old)
    assert new.orientation() == Qt.Orientation.Horizontal


def test_replace_splitter_new_splitter_starts_empty():
    container, old = _make_container_with_splitter()
    new = replace_splitter(container, old)
    assert new.count() == 0

