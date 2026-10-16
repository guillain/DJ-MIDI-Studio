"""Window sizing that stays usable on small screens (issues #19, #282).

Two problems the small-window audit of issue #282 found in the windows of
the v0.48.90–v0.48.103 batch:

* A hard-coded default size (``resize(1100, 640)``) is larger than a
  1000x650 or 900x600 display, so the window opens with its edges, buttons
  included, off screen. `fit_to_screen` caps the default to the available
  screen area, the same rule `MainWindow._default_window_size` applies.
* A dialog's *minimum* size comes from its layout, and a table, list or
  chart reports a minimum of a few pixels: dragging the window small left
  a one-row sliver of table and clipped word-wrapped labels.
  `usable_minimum` gives such a view a floor, so the layout carries it up
  to the dialog's own minimum instead.
* Qt computes a window's minimum height without height-for-width: a
  word-wrapped label needs more lines at the minimum width than the
  layout accounted for, so dragging the window small squeezed the combo
  boxes and spin boxes beside it below their own minimum height (MIDI
  Latency Test, Smart playlist editor). `keep_wrapped_text_visible`
  re-derives the minimum height at the minimum width whenever the layout
  changes.

* On macOS a tab bar too narrow for its titles cuts every title to a
  few letters ("Pa…", "Pa…", "DD…"), so the tabs can't be told apart —
  the French labels made it common (issue #290). `keep_tab_titles_whole`
  keeps the titles whole and scrolls the tab bar instead.

`fit_size` is the Qt-free arithmetic, kept separate so it is testable on
plain numbers.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTabWidget, QWidget

# Share of the available screen a window may take by default, the same
# margins `MainWindow._default_window_size` keeps for its title bar/edges.
WIDTH_RATIO = 0.92
HEIGHT_RATIO = 0.90


def fit_size(
    preferred: tuple[int, int],
    available: tuple[int, int] | None,
    width_ratio: float = WIDTH_RATIO,
    height_ratio: float = HEIGHT_RATIO,
) -> tuple[int, int]:
    """``preferred`` capped to a share of the ``available`` screen area.

    ``available`` is ``None`` when no screen is known (the preferred size is
    kept). The result is never larger than ``preferred``; the window's own
    minimum size still wins over it, which Qt enforces on ``resize``.
    """
    width, height = preferred
    if available is None:
        return width, height
    return (
        min(width, max(1, int(available[0] * width_ratio))),
        min(height, max(1, int(available[1] * height_ratio))),
    )


def available_size(widget: QWidget) -> tuple[int, int] | None:
    """The usable area of the screen ``widget`` is (or will be) shown on."""
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    geometry = screen.availableGeometry()
    return geometry.width(), geometry.height()


def fit_to_screen(widget: QWidget, width: int, height: int) -> None:
    """Resize ``widget`` to ``width``x``height``, capped to its screen."""
    widget.resize(*fit_size((width, height), available_size(widget)))


def usable_minimum(view: QWidget, width: int, height: int) -> None:
    """Give a table/list/chart a minimum size it stays readable at.

    The view's layout turns this into the window's minimum, so a window
    dragged small stops while the view still shows a few rows instead of
    collapsing it (and the word-wrapped labels around it) to a sliver.
    """
    view.setMinimumSize(width, height)


def wrapped_minimum(window: QWidget, floor: tuple[int, int] = (0, 0)) -> tuple[int, int] | None:
    """The minimum size ``window``'s layout really needs, word-wrapped
    labels included, never below ``floor``; ``None`` when nothing in it
    wraps."""
    layout = window.layout()
    if layout is None or not layout.hasHeightForWidth():
        return None
    minimum = layout.totalMinimumSize()
    width = max(minimum.width(), floor[0])
    height = max(minimum.height(), layout.totalMinimumHeightForWidth(width), floor[1])
    return width, height


class _WrappedTextMinimum(QObject):
    """Re-applies `wrapped_minimum` each time the window's layout changes
    (a translated or updated label can need another line)."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        # A minimum the window set itself before its layout ran (e.g. a
        # fixed minimum width) stays a floor: from here on this object owns
        # the window's minimum size.
        self._floor = window.minimumSize().toTuple()

    def apply(self) -> None:
        minimum = wrapped_minimum(self._window, self._floor)
        if minimum is not None and self._window.minimumSize().toTuple() != minimum:
            self._window.setMinimumSize(*minimum)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.LayoutRequest:
            self.apply()
        return False


def keep_wrapped_text_visible(window: QWidget) -> None:
    """Keep ``window``'s minimum height large enough for its word-wrapped
    labels at its minimum width. Call once its layout is built."""
    keeper = _WrappedTextMinimum(window)
    window.installEventFilter(keeper)
    keeper.apply()


def keep_tab_titles_whole(tabs: QTabWidget, *, scroll: bool = True) -> None:
    """Never elide ``tabs``' titles; with ``scroll`` the tab bar shows
    scroll arrows when the titles don't fit, else the tab widget asks for
    their full width (inside a scroll area, which then scrolls)."""
    tabs.setElideMode(Qt.TextElideMode.ElideNone)
    tabs.setUsesScrollButtons(scroll)


__all__ = [
    "available_size",
    "fit_size",
    "fit_to_screen",
    "keep_tab_titles_whole",
    "keep_wrapped_text_visible",
    "usable_minimum",
    "wrapped_minimum",
]
