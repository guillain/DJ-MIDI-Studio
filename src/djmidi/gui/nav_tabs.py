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

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QTabWidget, QVBoxLayout, QWidget

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
        self._sections: list[str] = []  # per top tab: its colour section (theme.py)
        self.animate = True
        self._fade: QPropertyAnimation | None = None

    def _tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        # No native base: macOS paints a grey gradient band under document-mode
        # tabs, out of place on the light theme (theme.py styles the bar).
        tabs.tabBar().setDrawBase(False)
        keep_tab_titles_whole(tabs)
        tabs.currentChanged.connect(self._on_changed)
        return tabs

    def set_sections(self, sections: list[str]) -> None:
        """One name per top tab, in display order: the selected top tab's
        name goes on the ``section`` property, which colours it."""
        self._sections = list(sections)
        self._apply_section()

    def _apply_section(self) -> None:
        index = self.top.currentIndex()
        section = self._sections[index] if 0 <= index < len(self._sections) else ""
        if self.top.property("section") != section:
            self.top.setProperty("section", section)
            self.top.style().unpolish(self.top)
            self.top.style().polish(self.top)

    def _fade_in(self, widget: QWidget) -> None:
        """A short fade on the page just shown; the effect is removed after
        (an opacity effect makes every repaint offscreen)."""
        if not self.animate or not widget.isVisible():
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(160)
        fade.setStartValue(0.35)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._fade = fade
        fade.start()

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
        self._apply_section()
        if index != self._last:
            first = self._last < 0
            self._last = index
            if not first and index >= 0:
                self._fade_in(self._pages[index].widget)
            self.currentChanged.emit(index)


__all__ = ["NavTabs"]
