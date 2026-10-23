"""Library statistics window of the Music Library tab (issue #258).

Shows a `djmidi.library.stats.LibraryStats` snapshot as simple bar charts,
one tab each: categories, genres, BPM histogram, Camelot keys, files added
per month and -- once play history is loaded -- the most-played tracks.
Charts are drawn with `QPainter` (`BarChart`), no charting dependency.

A snapshot: the window doesn't follow later scans or filter changes;
reopening it recomputes. Read-only like the rest of the library tools.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QHelpEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library.stats import (
    NO_GENRE_LABEL,
    UNCATEGORIZED_LABEL,
    Bucket,
    LibraryStats,
)

_ROW_HEIGHT = 20
_COLUMN_WIDTH = 30
_LABEL_MAX = 260
_ROTATED_LABEL_MAX = 90
_PAD = 6


class BarChart(QWidget):
    """Bars for a list of `Bucket`s: horizontal rows (label, bar, count) by
    default, vertical columns with rotated labels when `vertical` is set
    (histograms, wheel order, months). Its minimum size grows with the
    number of buckets, so it is meant to sit in a `QScrollArea`."""

    bucketActivated = Signal(int)
    """Index of the double-clicked bucket."""

    def __init__(
        self,
        buckets: Sequence[Bucket] = (),
        *,
        vertical: bool = False,
        empty_text: str = "Nothing to show.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.vertical = vertical
        self.empty_text = empty_text
        self.buckets: tuple[Bucket, ...] = ()
        self.setMouseTracking(True)
        self.set_buckets(buckets)

    def set_buckets(self, buckets: Sequence[Bucket]) -> None:
        self.buckets = tuple(buckets)
        self.updateGeometry()
        self.update()

    def _label_extent(self) -> int:
        metrics = self.fontMetrics()
        cap = _ROTATED_LABEL_MAX if self.vertical else _LABEL_MAX
        widest = max(
            (metrics.horizontalAdvance(b.label) for b in self.buckets), default=0
        )
        # Room for the gap after the label plus font-metrics rounding, so a
        # label that fits is never elided.
        return min(widest, cap) + 2 * _PAD

    def _count_extent(self) -> int:
        widest = max((b.count for b in self.buckets), default=0)
        return self.fontMetrics().horizontalAdvance(str(widest)) + _PAD

    def minimumSizeHint(self) -> QSize:
        if not self.buckets:
            return QSize(200, 60)
        if self.vertical:
            text_height = self.fontMetrics().height()
            return QSize(
                len(self.buckets) * _COLUMN_WIDTH + 2 * _PAD,
                120 + self._label_extent() + text_height + 2 * _PAD,
            )
        return QSize(
            self._label_extent() + self._count_extent() + 120,
            len(self.buckets) * _ROW_HEIGHT + 2 * _PAD,
        )

    def sizeHint(self) -> QSize:
        hint = self.minimumSizeHint()
        return QSize(
            max(hint.width(), 480),
            max(hint.height(), 240 if self.vertical else hint.height()),
        )

    def bucket_rect(self, index: int) -> QRect:
        """The slot (whole row or column) of bucket `index`."""
        if self.vertical:
            return QRect(_PAD + index * _COLUMN_WIDTH, 0, _COLUMN_WIDTH, self.height())
        return QRect(0, _PAD + index * _ROW_HEIGHT, self.width(), _ROW_HEIGHT)

    def bucket_at(self, pos: QPoint) -> int | None:
        for index in range(len(self.buckets)):
            if self.bucket_rect(index).contains(pos):
                return index
        return None

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        palette = self.palette()
        painter.setPen(palette.text().color())
        if not self.buckets:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        peak = max(b.count for b in self.buckets) or 1
        bar_color = palette.highlight().color()
        metrics = self.fontMetrics()
        if self.vertical:
            label_extent = self._label_extent()
            text_height = metrics.height()
            base = self.height() - _PAD - label_extent
            room = max(base - _PAD - text_height, 1)
            for index, bucket in enumerate(self.buckets):
                x = _PAD + index * _COLUMN_WIDTH
                height = round(room * bucket.count / peak)
                painter.fillRect(
                    QRect(x + 3, base - height, _COLUMN_WIDTH - 6, height), bar_color
                )
                if bucket.count:
                    painter.drawText(
                        QRect(
                            x, base - height - text_height, _COLUMN_WIDTH, text_height
                        ),
                        Qt.AlignmentFlag.AlignCenter,
                        str(bucket.count),
                    )
                painter.save()
                # Rotated 90°, a glyph's ascent points right: centre it.
                painter.translate(
                    x + (_COLUMN_WIDTH - metrics.ascent() + metrics.descent()) / 2,
                    base + 4,
                )
                painter.rotate(90)
                painter.drawText(
                    0,
                    0,
                    metrics.elidedText(
                        bucket.label, Qt.TextElideMode.ElideRight, label_extent
                    ),
                )
                painter.restore()
            return
        label_extent = self._label_extent()
        count_extent = self._count_extent()
        room = max(self.width() - label_extent - count_extent - 2 * _PAD, 1)
        for index, bucket in enumerate(self.buckets):
            y = _PAD + index * _ROW_HEIGHT
            label = metrics.elidedText(
                bucket.label, Qt.TextElideMode.ElideMiddle, label_extent - _PAD
            )
            painter.drawText(
                QRect(_PAD, y, label_extent - _PAD, _ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                label,
            )
            width = round(room * bucket.count / peak)
            bar_x = _PAD + label_extent
            painter.fillRect(QRect(bar_x, y + 3, width, _ROW_HEIGHT - 6), bar_color)
            painter.drawText(
                QRect(bar_x + width + 4, y, count_extent, _ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(bucket.count),
            )

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            index = self.bucket_at(event.pos())
            if index is None:
                QToolTip.hideText()
            else:
                bucket = self.buckets[index]
                QToolTip.showText(
                    event.globalPos(), f"{bucket.label}: {bucket.count}", self
                )
            return True
        return super().event(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        index = self.bucket_at(event.position().toPoint())
        if index is not None:
            self.bucketActivated.emit(index)
        super().mouseDoubleClickEvent(event)


def _relabel(buckets: tuple[Bucket, ...], labels: dict[str, str]) -> tuple[Bucket, ...]:
    """The buckets with the stats module's English placeholder labels
    ("Uncategorized", "(no genre)") swapped for their translations."""
    return tuple(Bucket(labels.get(b.label, b.label), b.count) for b in buckets)


def _percent(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)} %" if whole else "0 %"


class LibraryStatsDialog(QDialog):
    showTrackRequested = Signal(str)
    """Path of a most-played track to select in the Music Library table."""

    def __init__(
        self, stats: LibraryStats, scope: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Library statistics"))
        fit_to_screen(self, 820, 560)
        self.stats = stats
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        summary = self.tr("{count} track(s)").format(count=stats.total)
        if scope:
            summary += f" — {scope}"
        if stats.missing:
            summary += ". " + self.tr("{count} missing file(s) not counted").format(count=stats.missing)
        self.summary_label = QLabel(summary + ".")
        self.summary_label.setWordWrap(True)
        header.addWidget(self.summary_label, 1)
        header.addWidget(
            help_button(self, *help_texts.LIBRARY_STATS), 0, Qt.AlignmentFlag.AlignTop
        )
        box.addLayout(header)

        self.tabs = QTabWidget()
        self.charts: dict[str, BarChart] = {}
        self.notes: dict[str, QLabel] = {}
        uncategorized = next(
            (b.count for b in stats.by_category if b.label == UNCATEGORIZED_LABEL), 0
        )
        self._add_tab(
            "categories",
            self.tr("Categories"),
            BarChart(
                _relabel(stats.by_category, {UNCATEGORIZED_LABEL: self.tr("Uncategorized")}),
                empty_text=self.tr("No tracks."),
            ),
            self.tr("{count} track(s) without a confirmed category ({percent}).").format(
                count=uncategorized, percent=_percent(uncategorized, stats.total)
            ),
        )
        self._add_tab(
            "genres",
            self.tr("Genres"),
            BarChart(
                _relabel(stats.by_genre, {NO_GENRE_LABEL: self.tr("(no genre)")}),
                empty_text=self.tr("No tracks."),
            ),
            self.tr(
                "{count} distinct genre tag(s); spelling variants differing only by case or spaces are grouped."
            ).format(count=len(stats.by_genre)),
        )
        self._add_tab(
            "bpm",
            self.tr("BPM"),
            BarChart(
                stats.bpm_histogram, vertical=True, empty_text=self.tr("No track has a BPM tag.")
            ),
            self.tr("{count} track(s) without a BPM ({percent}).").format(
                count=stats.no_bpm, percent=_percent(stats.no_bpm, stats.total)
            ),
        )
        self._add_tab(
            "keys",
            self.tr("Keys"),
            BarChart(stats.by_camelot, vertical=True, empty_text=self.tr("Nothing to show.")),
            self.tr("Camelot wheel order. {count} track(s) without a recognised key ({percent}).").format(
                count=stats.no_key, percent=_percent(stats.no_key, stats.total)
            ),
        )
        self._add_tab(
            "added",
            self.tr("Added per month"),
            BarChart(
                stats.added_per_month,
                vertical=True,
                empty_text=self.tr("No file dates in the index."),
            ),
            self.tr(
                "By file modification date (the index has no “date added”; a tag edit can move a file to a "
                "later month)."
            ),
        )
        if stats.most_played is None:
            played_chart = BarChart(
                empty_text=self.tr("Load DJ history in the History panel to see play counts.")
            )
            played_note = self.tr("No play history loaded.")
        else:
            played_chart = BarChart(
                [Bucket(track.label, track.play_count) for track in stats.most_played],
                empty_text=self.tr("No track of this list appears in the loaded history."),
            )
            played_note = self.tr(
                "{played} track(s) played at least once, {never} never played ({percent}). "
                "Double-click a track to show it."
            ).format(
                played=stats.played,
                never=stats.never_played,
                percent=_percent(stats.never_played or 0, stats.total),
            )
            played_chart.bucketActivated.connect(self._on_played_activated)
        self._add_tab("plays", self.tr("Most played"), played_chart, played_note)
        # Wide enough for every tab title: a scrolling tab bar hides tabs
        # behind arrows too narrow for their own minimum (issue #282).
        usable_minimum(self.tabs, max(420, self.tabs.tabBar().sizeHint().width() + 8), 260)
        box.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        keep_wrapped_text_visible(self)

    def _add_tab(self, key: str, title: str, chart: BarChart, note: str) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(chart)
        layout.addWidget(scroll, 1)
        label = QLabel(note)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.charts[key] = chart
        self.notes[key] = label
        self.tabs.addTab(page, title)

    def _on_played_activated(self, index: int) -> None:
        if self.stats.most_played and 0 <= index < len(self.stats.most_played):
            self.showTrackRequested.emit(self.stats.most_played[index].path)
