"""The main window's navigation: three top tabs -- Dashboard, Controller,
Music -- the Controller tab holding Setup, Images, Studio and By… (By
Channel / By Deck / By Controller).

`NavTabs` keeps the flat API the rest of the window used on the former
single tab bar: every page has an index in display order (`page_index`),
and `setCurrentIndex`, `currentIndex`, `count`, `tabText`, `widget`,
`currentWidget` and `currentChanged(int)` work on those page indexes, so
callers address a page without knowing in which nested tab it sits.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from djmidi.gui.window_size import keep_tab_titles_whole


@dataclass
class _Page:
    key: str
    widget: QWidget
    title: str
    path: tuple[QTabWidget, ...]  # the tab widgets from the top down to the page


class NavTabs(QWidget):
    currentChanged = Signal(int)  # page index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.top = self._tabs()
        self.top.setObjectName("navTop")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.top)
        self._pages: list[_Page] = []
        self._last = -1

    def _tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        keep_tab_titles_whole(tabs)
        tabs.currentChanged.connect(self._on_changed)
        return tabs

    def add_group(self, title: str, parent: QTabWidget | None = None) -> QTabWidget:
        """A tab holding its own tabs."""
        group = self._tabs()
        # Each level has its own look (theme.py): main tabs, sub-tabs, pills.
        group.setObjectName("navSub" if parent is None or parent is self.top else "navPills")
        (parent or self.top).addTab(group, title)
        return group

    def add_page(self, key: str, widget: QWidget, title: str, parent: QTabWidget | None = None) -> int:
        holder = parent or self.top
        holder.addTab(widget, title)
        path = []
        tabs: QWidget | None = holder
        while isinstance(tabs, QTabWidget):
            path.insert(0, tabs)
            tabs = tabs.parentWidget()
            while tabs is not None and not isinstance(tabs, QTabWidget) and tabs is not self:
                tabs = tabs.parentWidget()
        self._pages.append(_Page(key, widget, title, tuple(path)))
        return len(self._pages) - 1

    # -- the flat API ---------------------------------------------------------

    def page_index(self, key: str) -> int:
        return next(index for index, page in enumerate(self._pages) if page.key == key)

    def count(self) -> int:
        return len(self._pages)

    def tabText(self, index: int) -> str:
        return self._pages[index].title

    def widget(self, index: int) -> QWidget:
        return self._pages[index].widget

    def currentWidget(self) -> QWidget:
        return self._pages[self.currentIndex()].widget

    def usesScrollButtons(self) -> bool:
        return self.top.usesScrollButtons()

    def currentIndex(self) -> int:
        widget: QWidget = self.top.currentWidget()
        while isinstance(widget, QTabWidget):
            widget = widget.currentWidget()
        return next((index for index, page in enumerate(self._pages) if page.widget is widget), -1)

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self._pages):
            return
        page = self._pages[index]
        child: QWidget = page.widget
        for tabs in reversed(page.path):
            tabs.blockSignals(True)
            tabs.setCurrentWidget(child)
            tabs.blockSignals(False)
            child = tabs
        self._on_changed()

    def _on_changed(self, *_args) -> None:
        index = self.currentIndex()
        if index != self._last:
            self._last = index
            self.currentChanged.emit(index)


__all__ = ["NavTabs"]
