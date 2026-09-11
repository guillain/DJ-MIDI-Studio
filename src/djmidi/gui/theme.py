"""Application-wide theme for Qt windows and dialogs.

One QSS template, two colour palettes (dark = the DJ-booth look, light = its
readable daylight twin), plus a "system" mode that follows the OS. Switching
mode also sets Qt's colour scheme so native controls and ``QStyle`` standard
icons pick the matching tone instead of staying dark on a light theme.
"""

from __future__ import annotations

import logging
from string import Template
from typing import Literal

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

_LOGGER = logging.getLogger(__name__)

ThemeMode = Literal["system", "light", "dark"]
THEME_MODES: tuple[ThemeMode, ...] = ("system", "light", "dark")

_QSS = Template("""
QMainWindow, QDialog, QDockWidget, QWidget {
    background: $window_bg;
    color: $text;
}
QMenuBar {
    background: $bar_bg;
    color: $text;
    border-bottom: 1px solid $panel_border;
    padding: 3px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: $accent;
    color: #ffffff;
}
QMenu {
    background: $menu_bg;
    color: $text;
    border: 1px solid $field_border;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
}
QTabWidget::pane {
    background: $tab_pane_bg;
    border: 1px solid $panel_border;
}
QTabBar::tab {
    background: $tab_bg;
    color: $tab_text;
    border: 1px solid $panel_border;
    padding: 8px 13px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: $accent;
    color: #ffffff;
    border-color: $accent_soft;
}
QGroupBox {
    background: $panel_bg;
    border: 1px solid $panel_border;
    border-radius: 9px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: $title;
    background: $window_bg;
}
QPushButton {
    background: $button_bg;
    color: $button_text;
    border: 1px solid $button_border;
    border-radius: 6px;
    padding: 7px 11px;
    font-weight: 600;
}
QPushButton:hover {
    background: $button_hover_bg;
    border-color: $accent2;
}
QPushButton:pressed {
    background: $accent;
    color: #ffffff;
}
QPushButton:disabled {
    background: $disabled_bg;
    color: $disabled_text;
    border-color: $disabled_border;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget,
QSpinBox, QDoubleSpinBox {
    background: $field_bg;
    color: $text;
    border: 1px solid $field_border;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: $accent;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QListWidget:focus {
    border-color: $accent2;
}
QComboBox QAbstractItemView, QListView {
    background: $field_bg;
    color: $text;
    border: 1px solid $field_border;
    selection-background-color: $accent;
    selection-color: #ffffff;
}
QCheckBox, QLabel, QRadioButton {
    color: $label_text;
}
QTableWidget, QTableView, QTreeView {
    background: $field_bg;
    alternate-background-color: $table_alt;
    color: $table_text;
    border: 1px solid $panel_border;
    selection-background-color: $accent;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: $header_bg;
    color: $header_text;
    border: 0;
    border-bottom: 1px solid $field_border;
    padding: 7px;
    font-weight: 600;
}
QStatusBar {
    background: $bar_bg;
    color: $header_text;
    border-top: 1px solid $panel_border;
}
QDockWidget {
    color: $text;
    titlebar-close-icon: none;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: $bar_bg;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $scroll_handle;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: $accent2;
}
QToolTip {
    background: $tooltip_bg;
    color: #ffffff;
    border: 1px solid $accent2;
    padding: 6px;
}
""")

_DARK = {
    "window_bg": "#0d121b",
    "text": "#e8eef7",
    "label_text": "#c9d5e4",
    "bar_bg": "#111a28",
    "menu_bg": "#151e2b",
    "panel_bg": "#151e2b",
    "panel_border": "#2b3b53",
    "field_bg": "#0e1724",
    "field_border": "#3a506d",
    "tab_pane_bg": "#101925",
    "tab_bg": "#182437",
    "tab_text": "#aebed1",
    "title": "#8fe8ff",
    "accent": "#d33c72",
    "accent_soft": "#f26395",
    "accent2": "#00c2e8",
    # Buttons: lighter fill + higher-contrast border so icon-only buttons
    # stand out against the dark panels.
    "button_bg": "#33465f",
    "button_text": "#f2f7fd",
    "button_border": "#5d7d9f",
    "button_hover_bg": "#40597c",
    "disabled_bg": "#1a2432",
    "disabled_text": "#6d7f96",
    "disabled_border": "#2a3a4d",
    "table_alt": "#121e2d",
    "table_text": "#dce7f5",
    "header_bg": "#202d42",
    "header_text": "#b9c9dc",
    "scroll_handle": "#56769a",
    "tooltip_bg": "#202d42",
    "tree_hover_bg": "#263b56",
    "tree_hover_text": "#ffffff",
    "table_selected_bg": "#284765",
    "clock_accent": "#008eaa",
    "clock_accent_border": "#28d5ef",
    # A muted "hint/subtitle" shade distinct from label_text -- reused
    # verbatim (as a hardcoded literal, before this token existed) across
    # several panels for secondary explanatory text under a heading.
    "hint_text": "#8fa7bd",
}

_LIGHT = {
    "window_bg": "#f4f6fa",
    "text": "#1c2530",
    "label_text": "#33404f",
    "bar_bg": "#e7ecf3",
    "menu_bg": "#ffffff",
    "panel_bg": "#ffffff",
    "panel_border": "#c3ccd9",
    "field_bg": "#ffffff",
    "field_border": "#b3bfd0",
    "tab_pane_bg": "#ffffff",
    "tab_bg": "#e3e9f1",
    "tab_text": "#4a5768",
    "title": "#0a6f8c",
    "accent": "#d33c72",
    "accent_soft": "#e885a8",
    "accent2": "#0a97b8",
    "button_bg": "#e2e8f1",
    "button_text": "#1c2530",
    "button_border": "#a4b2c5",
    "button_hover_bg": "#d2dce9",
    "disabled_bg": "#eceff4",
    "disabled_text": "#9aa6b4",
    "disabled_border": "#d3d9e2",
    "table_alt": "#f1f4f9",
    "table_text": "#22303f",
    "header_bg": "#e7ecf3",
    "header_text": "#45566a",
    "scroll_handle": "#aab6c6",
    "tooltip_bg": "#23303f",
    "tree_hover_bg": "#dce6f1",
    "tree_hover_text": "#1c2530",
    "table_selected_bg": "#cfe0f0",
    "clock_accent": "#0a7fa0",
    "clock_accent_border": "#39b6d6",
    "hint_text": "#5b7086",
}

DARK_THEME = _QSS.substitute(_DARK)
LIGHT_THEME = _QSS.substitute(_LIGHT)
# Back-compat alias for callers/tests that referred to the single old theme.
DJ_THEME = DARK_THEME

_PALETTES: dict[Literal["light", "dark"], dict[str, str]] = {"light": _LIGHT, "dark": _DARK}

# Several custom-styled panels (mapping trees, MIDI Routing/Clock, Controller
# Setup, Live send) build their own scoped QSS instead of relying purely on
# the app-wide cascade above -- e.g. to scope colors to one objectName, or to
# style a QGraphicsView that ignores stylesheets for its scene content. Before
# this module tracked the active mode, those were written with a literal
# hardcoded copy of _DARK's values: switching to Light in Preferences left
# every one of them stuck dark, since nothing ever told them to rebuild.
# `colors()`/`current_mode()` let them build (and `signals.themeChanged` let
# them rebuild, live, on a theme switch) from the same token dict this
# module already substitutes its own QSS from, instead of a frozen snapshot.
_current_mode: Literal["light", "dark"] = "dark"


class _ThemeSignals(QObject):
    """A module-level signal source: `theme.py` has no QWidget of its own to
    hang a Signal off, so this tiny QObject singleton stands in for one."""

    themeChanged = Signal(str)  # "light" or "dark" -- always the resolved mode, never "system"


signals = _ThemeSignals()


def colors(mode: Literal["light", "dark"] | None = None) -> dict[str, str]:
    """The resolved color-token dict for `mode` (or the currently active one
    if omitted), for components that build their own scoped QSS. A copy, so
    callers substituting into a Template can't mutate the shared palette."""
    return dict(_PALETTES[mode or _current_mode])


def current_mode() -> Literal["light", "dark"]:
    """The last mode `apply_theme()` resolved and applied -- always a
    concrete "light"/"dark", never "system" (see `resolve_mode`)."""
    return _current_mode


_TREE_QSS = Template("""
QTreeView {
    background: $field_bg;
    alternate-background-color: $table_alt;
    color: $table_text;
    border: 1px solid $panel_border;
    border-radius: 8px;
    padding: 5px;
    outline: none;
}
QTreeView::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QTreeView::item:hover {
    background: $tree_hover_bg;
    color: $tree_hover_text;
}
QTreeView::item:selected {
    background: $accent;
    color: #ffffff;
}
QHeaderView::section {
    background: $header_bg;
    color: $header_text;
    border: 0;
    border-bottom: 1px solid $field_border;
    padding: 7px;
    font-weight: 600;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: $bar_bg;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $scroll_handle;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: $accent2;
}
""")


def mapping_tree_stylesheet(mode: Literal["light", "dark"] | None = None) -> str:
    """The scoped QSS every mapping QTreeView (By Channel/Deck/Controller)
    sets on itself directly, rather than relying on the app-wide cascade in
    `_QSS`: it needs its own :hover/:selected rules the generic QTreeView
    block above doesn't define. Callable per-mode (see `colors()`) so a
    caller can rebuild it after a live theme switch instead of the widget
    being stuck with whatever was current at construction time."""
    return _TREE_QSS.substitute(colors(mode))


_MIDI_TOOLS_QSS = Template("""
#midiToolsSurface {
    background: $window_bg;
    color: $text;
}
#midiToolsSurface QLabel {
    color: $label_text;
}
#midiToolsSurface QGroupBox {
    background: $panel_bg;
    border: 1px solid $panel_border;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}
#midiToolsSurface QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: $title;
    background: $window_bg;
}
#midiToolsSurface QComboBox,
#midiToolsSurface QTableWidget,
#midiToolsSurface QLineEdit,
#midiToolsSurface QListWidget {
    background: $field_bg;
    color: $text;
    border: 1px solid $field_border;
    border-radius: 6px;
    padding: 5px;
}
#midiToolsSurface QComboBox:focus,
#midiToolsSurface QTableWidget:focus {
    border: 1px solid $accent2;
}
#midiToolsSurface QComboBox QAbstractItemView {
    background: $field_bg;
    color: $text;
    border: 1px solid $field_border;
    selection-background-color: $accent;
    selection-color: #ffffff;
}
#midiToolsSurface QHeaderView::section {
    background: $header_bg;
    color: $header_text;
    border: 0;
    border-bottom: 1px solid $field_border;
    padding: 7px;
    font-weight: 600;
}
#midiToolsSurface QTableWidget::item:selected {
    background: $table_selected_bg;
    color: $text;
}
#midiToolsSurface QPushButton {
    background: $button_bg;
    color: $button_text;
    border: 1px solid $button_border;
    border-radius: 6px;
    padding: 7px 11px;
    font-weight: 600;
}
#midiToolsSurface QPushButton:hover {
    background: $button_hover_bg;
    border-color: $accent2;
}
#midiToolsSurface QPushButton#primaryAction {
    background: $accent;
    border-color: $accent_soft;
    color: #ffffff;
}
#midiToolsSurface QPushButton#clockAction {
    background: $clock_accent;
    border-color: $clock_accent_border;
    color: #ffffff;
}
#midiToolsSurface QPushButton#primaryAction:hover,
#midiToolsSurface QPushButton#clockAction:hover {
    background: $accent_soft;
}
#midiToolsSurface QPushButton:disabled {
    background: $disabled_bg;
    color: $disabled_text;
    border-color: $disabled_border;
}
#midiToolsSurface QCheckBox {
    color: $label_text;
    spacing: 7px;
    padding: 3px 0;
}
#midiToolsSurface QCheckBox::indicator:checked {
    background: $accent2;
    border: 1px solid $accent2;
}
#midiToolsSurface #clockStatus {
    background: $header_bg;
    border-left: 4px solid $accent2;
    border-radius: 5px;
    padding: 9px;
}
""")


def midi_tools_stylesheet(mode: Literal["light", "dark"] | None = None) -> str:
    """The scoped QSS MidiRoutingView applies to itself (and reuses verbatim
    on the reparented MIDI Clock panel) under the #midiToolsSurface
    objectName. Callable per-mode for the same reason as
    mapping_tree_stylesheet(): a widget built once needs to rebuild this on
    a live theme switch, not just read it at construction."""
    return _MIDI_TOOLS_QSS.substitute(colors(mode))


def resolve_mode(mode: str, app: QApplication | None = None) -> Literal["light", "dark"]:
    """Turn a stored ThemeMode into a concrete "light"/"dark". For "system",
    read the OS colour scheme; fall back to dark if it can't be determined."""
    if mode == "light":
        return "light"
    if mode == "dark":
        return "dark"
    application = app or QApplication.instance()
    if application is not None:
        scheme = application.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
    return "dark"


def apply_theme(app: QApplication, mode: str = "dark") -> None:
    """Apply the palette for ``mode`` ("system"/"light"/"dark") to every window.

    Also drives Qt's colour scheme so native controls and ``QStyle`` standard
    icons match: forced for light/dark, released to the OS for "system".
    """
    if mode not in THEME_MODES:
        _LOGGER.warning("Unknown theme mode %r; using 'dark'", mode)
        mode = "dark"
    style_hints = app.styleHints()
    if mode == "system":
        style_hints.unsetColorScheme()
    else:
        style_hints.setColorScheme(
            Qt.ColorScheme.Light if mode == "light" else Qt.ColorScheme.Dark
        )
    concrete = resolve_mode(mode, app)
    app.setStyleSheet(LIGHT_THEME if concrete == "light" else DARK_THEME)
    global _current_mode
    _current_mode = concrete
    # Emitted unconditionally, not just on an actual flip: a scoped-QSS
    # widget only needs to read colors() once at construction (by the time
    # any widget exists, MainWindow.__init__ has already applied the saved
    # preference), and this signal is purely for a *live* Preferences change
    # -- cheap to always fire, and simpler than tracking whether this call
    # happened to change anything.
    signals.themeChanged.emit(concrete)
    _LOGGER.info("Applied %s theme (mode=%s)", concrete, mode)


__all__ = [
    "DARK_THEME",
    "DJ_THEME",
    "LIGHT_THEME",
    "THEME_MODES",
    "ThemeMode",
    "apply_theme",
    "colors",
    "current_mode",
    "mapping_tree_stylesheet",
    "midi_tools_stylesheet",
    "resolve_mode",
    "signals",
]
