import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from djmidi.gui.theme import (
    DARK_THEME,
    DJ_THEME,
    LIGHT_THEME,
    THEME_MODES,
    apply_theme,
    colors,
    current_mode,
    mapping_tree_stylesheet,
    resolve_mode,
    signals,
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


def test_colors_and_current_mode_track_the_last_applied_theme():
    app = QApplication.instance() or QApplication([])
    try:
        apply_theme(app, "dark")
        assert current_mode() == "dark"
        assert colors()["window_bg"] == colors("dark")["window_bg"] != colors("light")["window_bg"]

        apply_theme(app, "light")
        assert current_mode() == "light"
        assert colors()["window_bg"] == colors("light")["window_bg"]
    finally:
        apply_theme(app, "dark")


def test_colors_returns_an_independent_copy():
    """Callers substitute into their own Template -- mutating what colors()
    returns must never leak into the shared palette dict."""
    snapshot = colors("dark")
    snapshot["window_bg"] = "#000000"
    assert colors("dark")["window_bg"] != "#000000"


def test_mapping_tree_stylesheet_reflects_the_requested_mode():
    dark_qss = mapping_tree_stylesheet("dark")
    light_qss = mapping_tree_stylesheet("light")
    assert dark_qss != light_qss
    assert colors("dark")["field_bg"] in dark_qss
    assert colors("light")["field_bg"] in light_qss
    # No leftover $tokens: every placeholder in the template must have been
    # substituted, in both palettes.
    assert "$" not in dark_qss
    assert "$" not in light_qss


def test_mapping_tree_stylesheet_defaults_to_the_current_mode():
    app = QApplication.instance() or QApplication([])
    try:
        apply_theme(app, "light")
        assert mapping_tree_stylesheet() == mapping_tree_stylesheet("light")
    finally:
        apply_theme(app, "dark")


def test_apply_theme_emits_theme_changed_with_the_resolved_mode():
    app = QApplication.instance() or QApplication([])
    received: list[str] = []
    signals.themeChanged.connect(received.append)
    try:
        apply_theme(app, "light")
        apply_theme(app, "dark")
        assert received == ["light", "dark"]
    finally:
        signals.themeChanged.disconnect(received.append)
        apply_theme(app, "dark")
