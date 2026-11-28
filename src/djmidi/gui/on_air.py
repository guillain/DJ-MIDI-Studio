"""Studio-style "on air" lamps: a big red ● REC with the elapsed time.

Every recording the app can run (the live set, ● Rec of a controller's
setup, the Mix Together program) lights one lamp in the menu bar corner, so
it shows on every tab and can't be missed. A lamp blinks once a second and
counts the time; clicking it opens the tool that records. Nothing lit, the
row hides.

The main window tells the lamps what is on by polling (:meth:`OnAirLamps.update`
with a list of :class:`Lamp`), so a feature only has to say whether it
records, never to emit signals.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from djmidi.gui import theme

_RED = {"dark": "#e5484d", "light": "#c62828"}


@dataclass(frozen=True)
class Lamp:
    key: str  # stable id, e.g. "live_set"
    label: str  # translated, short: "REC set"
    tooltip: str
    started: float | None = None  # time.monotonic() of the start, for the counter


def elapsed_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60:02d}:{rest % 60:02d}"


class OnAirLamps(QWidget):
    lampClicked = Signal(str)

    def __init__(self, parent: QWidget | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(parent)
        self.setObjectName("onAirLamps")
        self._clock = clock
        self._buttons: dict[str, QPushButton] = {}
        self._lamps: dict[str, Lamp] = {}
        self._first_seen: dict[str, float] = {}
        self._lit = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(6)
        self._blink = QTimer(self)
        self._blink.setInterval(500)
        self._blink.timeout.connect(self._on_blink)
        self.setVisible(False)
        theme.signals.themeChanged.connect(self._restyle)

    @property
    def keys(self) -> list[str]:
        return list(self._lamps)

    def text_of(self, key: str) -> str:
        return self._buttons[key].text()

    def update_lamps(self, lamps: list[Lamp]) -> None:
        """The recordings running now; lamps of the others go out."""
        wanted = {lamp.key: lamp for lamp in lamps}
        for key in list(self._buttons):
            if key not in wanted:
                button = self._buttons.pop(key)
                self.layout().removeWidget(button)
                button.deleteLater()
                self._lamps.pop(key, None)
                self._first_seen.pop(key, None)
        for key, lamp in wanted.items():
            if key not in self._buttons:
                button = QPushButton(self)
                button.setObjectName("onAirLamp")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFixedHeight(28)
                button.clicked.connect(lambda _checked=False, k=key: self.lampClicked.emit(k))
                self.layout().addWidget(button)
                self._buttons[key] = button
                self._first_seen[key] = self._clock()
            self._lamps[key] = lamp
            self._buttons[key].setToolTip(lamp.tooltip)
        self.setVisible(bool(self._buttons))
        if self._buttons and not self._blink.isActive():
            self._lit = True
            self._blink.start()
        elif not self._buttons:
            self._blink.stop()
        self._restyle()
        self._refresh_texts()

    def _on_blink(self) -> None:
        self._lit = not self._lit
        self._restyle()
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        now = self._clock()
        for key, button in self._buttons.items():
            lamp = self._lamps[key]
            started = lamp.started if lamp.started is not None else self._first_seen[key]
            dot = "●" if self._lit else "○"
            button.setText(f"{dot} {lamp.label}  {elapsed_text(now - started)}")

    def _restyle(self) -> None:
        c = theme.colors()
        # The red of Stage Mode's warnings, per light/dark theme.
        on = _RED.get(theme.current_mode(), _RED["dark"])
        off = c["panel_bg"]
        text_on = "#ffffff"
        style = (
            f"QPushButton#onAirLamp {{ background: {on if self._lit else off}; color: {text_on if self._lit else on}; "
            f"border: 2px solid {on}; border-radius: 14px; padding: 2px 12px; font-weight: 800; "
            f"font-size: 13px; letter-spacing: 1px; }}"
        )
        self.setStyleSheet(style)


__all__ = ["Lamp", "OnAirLamps", "elapsed_text"]
