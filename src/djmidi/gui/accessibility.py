"""Accessibility helpers (phase 5 item 6).

- **Names for icon-only buttons.** A screen reader announces a button by its
  accessible name, which Qt takes from the button's text -- empty for an
  icon, a bare glyph (⚙, ☰, ⟳) for the compact ones. Their tooltip already
  says what they do, so :func:`name_icon_buttons` copies it into the
  accessible name and keeps it in step when the tooltip changes (Controller
  Setup's Learn button swaps "Start learning" / "Stop learning").
- **Contrast.** :func:`contrast_ratio` is the WCAG 2 formula; the theme's
  text/background pairs in :data:`TEXT_PAIRS` are checked against
  :data:`MIN_TEXT_CONTRAST` (AA for normal text) by the tests.

:func:`unnamed_buttons` is what the tests use to find a button a screen
reader couldn't name.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractButton, QLineEdit, QWidget

MIN_TEXT_CONTRAST = 4.5
# (text token, background token) pairs the theme's QSS draws text with;
# "#ffffff" stands for the literal white the QSS uses on the accent colour.
TEXT_PAIRS = (
    ("text", "window_bg"),
    ("text", "panel_bg"),
    ("text", "menu_bg"),
    ("text", "field_bg"),
    ("label_text", "window_bg"),
    ("label_text", "panel_bg"),
    ("button_text", "button_bg"),
    ("button_text", "button_hover_bg"),
    ("table_text", "field_bg"),
    ("table_text", "table_alt"),
    ("table_text", "table_selected_bg"),
    ("header_text", "header_bg"),
    ("tab_text", "tab_bg"),
    ("hint_text", "window_bg"),
    ("hint_text", "panel_bg"),
    ("title", "window_bg"),
    ("title", "panel_bg"),
    ("tree_hover_text", "tree_hover_bg"),
    ("#ffffff", "accent"),
    ("#ffffff", "tooltip_bg"),
)
_WORD = re.compile(r"\w")


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    hex_color = color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _has_readable_text(button: QAbstractButton) -> bool:
    return bool(_WORD.search(button.text().replace("&", "")))


def _is_qt_internal(button: QAbstractButton) -> bool:
    """Buttons Qt builds itself (a table's corner button, a line edit's
    clear button, the menu bar's overflow arrow) -- named by Qt's own
    accessibility layer, not ours."""
    return button.objectName().startswith("qt_") or isinstance(button.parent(), QLineEdit)


def _tooltip_name(button: QAbstractButton) -> str:
    return " ".join(button.toolTip().split())


class _TooltipNamer(QObject):
    """Keeps an icon-only button's accessible name equal to its tooltip."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTipChange and isinstance(watched, QAbstractButton):
            watched.setAccessibleName(_tooltip_name(watched))
        return False


def name_icon_buttons(root: QWidget) -> int:
    """Names every icon/glyph-only button under `root` after its tooltip;
    returns how many were named. Buttons with readable text, an explicit
    accessible name or no tooltip are left alone. Safe to call again."""
    named = 0
    for button in root.findChildren(QAbstractButton):
        if _has_readable_text(button) or _is_qt_internal(button) or not button.toolTip():
            continue
        if button.property("_dj_tooltip_named"):
            continue
        if button.accessibleName() and button.accessibleName() != _tooltip_name(button):
            continue  # named on purpose
        namer = _TooltipNamer(button)
        button.installEventFilter(namer)
        button.setProperty("_dj_tooltip_named", True)
        button.setAccessibleName(_tooltip_name(button))
        named += 1
    return named


def unnamed_buttons(root: QWidget) -> list[QAbstractButton]:
    """Buttons under `root` a screen reader would announce without a name."""
    return [
        button
        for button in root.findChildren(QAbstractButton)
        if not _has_readable_text(button) and not button.accessibleName() and not _is_qt_internal(button)
    ]


__all__ = [
    "MIN_TEXT_CONTRAST",
    "TEXT_PAIRS",
    "contrast_ratio",
    "name_icon_buttons",
    "relative_luminance",
    "unnamed_buttons",
]
