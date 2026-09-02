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

from PySide6.QtCore import Qt
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
}

DARK_THEME = _QSS.substitute(_DARK)
LIGHT_THEME = _QSS.substitute(_LIGHT)
# Back-compat alias for callers/tests that referred to the single old theme.
DJ_THEME = DARK_THEME


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
    _LOGGER.info("Applied %s theme (mode=%s)", concrete, mode)


__all__ = [
    "DARK_THEME",
    "DJ_THEME",
    "LIGHT_THEME",
    "THEME_MODES",
    "ThemeMode",
    "apply_theme",
    "resolve_mode",
]
