import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from djmidi.gui.theme import (
    DARK_THEME,
    DJ_THEME,
    LIGHT_THEME,
    THEME_MODES,
    apply_theme,
    resolve_mode,
)


def test_light_and_dark_stylesheets_differ_and_are_non_empty():
    assert DARK_THEME.strip() and LIGHT_THEME.strip()
    assert DARK_THEME != LIGHT_THEME
    assert DJ_THEME == DARK_THEME  # back-compat alias


def test_theme_modes_are_the_three_expected():
    assert THEME_MODES == ("system", "light", "dark")


@pytest.mark.parametrize("mode,expected", [("light", "light"), ("dark", "dark")])
def test_resolve_mode_explicit(mode, expected):
    assert resolve_mode(mode) == expected


def test_resolve_mode_system_reads_color_scheme(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(app.styleHints(), "colorScheme", lambda: Qt.ColorScheme.Light)
    assert resolve_mode("system", app) == "light"
    monkeypatch.setattr(app.styleHints(), "colorScheme", lambda: Qt.ColorScheme.Dark)
    assert resolve_mode("system", app) == "dark"


def test_apply_theme_sets_the_matching_stylesheet():
    app = QApplication.instance() or QApplication([])
    try:
        apply_theme(app, "light")
        assert app.styleSheet() == LIGHT_THEME
        apply_theme(app, "dark")
        assert app.styleSheet() == DARK_THEME
        apply_theme(app, "bogus")  # falls back to dark, no crash
        assert app.styleSheet() == DARK_THEME
    finally:
        app.styleHints().unsetColorScheme()
        apply_theme(app, "dark")
