"""Accessibility (phase 5 item 6): names for icon-only buttons, keyboard
focus, and theme contrast."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QHeaderView,
    QLineEdit,
    QPushButton,
)

from djmidi.gui import theme
from djmidi.gui.accessibility import (
    MIN_TEXT_CONTRAST,
    TEXT_PAIRS,
    contrast_ratio,
    name_icon_buttons,
    unnamed_buttons,
)

# Deliberately out of the Tab order: the palette's result list (the search
# field keeps focus and drives it) and Stage Mode's log (read from a distance).
NO_FOCUS_ON_PURPOSE = {"stageLog"}


def _describe(widgets):
    return [(type(w).__name__, w.text() if hasattr(w, "text") else "", w.toolTip()) for w in widgets]


def test_contrast_formula_matches_wcag():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert contrast_ratio("#777777", "#777777") == 1.0


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_theme_text_meets_aa_contrast(mode):
    palette = theme._PALETTES[mode]
    weak = []
    for text, background in TEXT_PAIRS:
        foreground = text if text.startswith("#") else palette[text]
        ratio = contrast_ratio(foreground, palette[background])
        if ratio < MIN_TEXT_CONTRAST:
            weak.append((text, background, round(ratio, 2)))
    assert weak == []


def test_icon_buttons_take_their_tooltip_as_name_and_follow_it():
    button = QPushButton()
    button.setToolTip("Start learning")
    holder = QPushButton("Has text")
    holder.setToolTip("ignored")
    for widget in (button, holder):
        widget.setParent(None)
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    button.setParent(root)
    holder.setParent(root)
    assert unnamed_buttons(root) == [button]
    assert name_icon_buttons(root) == 1 and name_icon_buttons(root) == 0
    assert button.accessibleName() == "Start learning" and holder.accessibleName() == ""
    button.setToolTip("Stop learning")
    assert button.accessibleName() == "Stop learning"
    assert unnamed_buttons(root) == []
    root.deleteLater()


def test_every_button_of_the_main_window_has_a_name_and_every_control_takes_focus():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window._create_emulator_instance("DDJ-XP2")
        for index in range(window.left_tabs.count()):
            window.left_tabs.setCurrentIndex(index)
        assert _describe(unnamed_buttons(window)) == []
        unfocusable = [
            widget
            for cls in (QAbstractButton, QComboBox, QLineEdit, QAbstractSpinBox, QAbstractItemView)
            for widget in window.findChildren(cls)
            if not widget.focusPolicy() & Qt.FocusPolicy.TabFocus
            and widget.objectName() not in NO_FOCUS_ON_PURPOSE
            and not widget.objectName().startswith("qt_")
            and not isinstance(widget.parent(), QLineEdit)
            and not isinstance(widget, QHeaderView)
        ]
        assert _describe(unfocusable) == []
    finally:
        window.close()


def test_dialogs_name_their_buttons():
    from test_small_windows import WINDOWS

    missing = {}
    for name, factory in WINDOWS.items():
        window = factory()
        try:
            unnamed = unnamed_buttons(window)
            if unnamed:
                missing[name] = _describe(unnamed)
        finally:
            window.close()
            window.deleteLater()
    assert missing == {}
