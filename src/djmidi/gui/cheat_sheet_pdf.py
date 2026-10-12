"""Draws gui/cheat_sheet.py's sheets to a PDF (QPdfWriter + QPainter) --
the File -> Export -> Cheat Sheet (PDF) output (issue #182).

Every page is A4 landscape. A photo sheet draws the controller's clean
reference photo with each mapped control's function written on the control
itself, in a white label shrunk to fit its geometry box; a label that
won't fit at a legible size gets a numbered badge instead, explained in a
legend under the photo (and on a continuation page if that overflows).
Unmapped markers keep a faint outline so the page still reads as the
device. A table sheet (no geometry, or controls no marker shows) is a
section / control / function table, paginated.

paint_sheets() only needs a painter, a page rect and a new-page callback, so
render_sheet_image() can draw the very same page into a QImage for tests
and screenshots."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)

from djmidi.gui import layout_view
from djmidi.gui.cheat_sheet import Sheet, SheetEntry

_DPI = 150
_MARGIN_MM = 10.0
_INLINE_MAX_PT = 9.0
_INLINE_MIN_PT = 5.0
_LEGEND_PT = 7.0
_TABLE_PT = 8.0
_TITLE_PT = 14.0
_SMALL_PT = 7.0
_PHOTO_SHARE = 0.68  # of the content height, when a legend is needed
_TEXT = QColor("#1b1f24")
_MUTED = QColor("#6b7380")
_RULE = QColor("#c8ccd2")
_ZEBRA = QColor("#f2f4f7")
_BADGE = QColor("#c0392b")
_UNMAPPED_PEN = QPen(QColor(120, 128, 140, 110), 1.0)


@dataclass
class _Context:
    painter: QPainter
    page: QRectF  # the content rect, margins removed
    footer: str
    page_number: int = 0


def _font(points: float, bold: bool = False) -> QFont:
    font = QFont("Helvetica")
    font.setPointSizeF(points)
    font.setBold(bold)
    return font


def _mm(dpi: float, mm: float) -> float:
    return mm * dpi / 25.4


def _start_page(ctx: _Context, title: str, new_page: Callable[[], None]) -> float:
    """Begin a page (asking the device for a fresh one after the first),
    draw its title and footer, and return the y where content starts."""
    if ctx.page_number > 0:
        new_page()
    ctx.page_number += 1
    painter = ctx.painter
    painter.setPen(_TEXT)
    painter.setFont(_font(_TITLE_PT, bold=True))
    title_h = QFontMetricsF(painter.font(), painter.device()).height()
    painter.drawText(
        QRectF(ctx.page.left(), ctx.page.top(), ctx.page.width(), title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        title,
    )
    painter.setFont(_font(_SMALL_PT))
    painter.setPen(_MUTED)
    small_h = QFontMetricsF(painter.font(), painter.device()).height()
    footer_rect = QRectF(
        ctx.page.left(), ctx.page.bottom() - small_h, ctx.page.width(), small_h
    )
    painter.drawText(footer_rect, Qt.AlignmentFlag.AlignLeft, ctx.footer)
    painter.drawText(
        footer_rect, Qt.AlignmentFlag.AlignRight, f"Page {ctx.page_number}"
    )
    return ctx.page.top() + title_h * 1.4


def _content_bottom(ctx: _Context) -> float:
    small_h = QFontMetricsF(_font(_SMALL_PT), ctx.painter.device()).height()
    return ctx.page.bottom() - small_h * 1.6


def _fit_inline(painter: QPainter, text: str, box: QRectF) -> QFont | None:
    """The largest font (between _INLINE_MAX_PT and _INLINE_MIN_PT) at which
    `text` word-wraps inside `box`, or None when even the smallest won't."""
    flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
    points = _INLINE_MAX_PT
    while points >= _INLINE_MIN_PT:
        font = _font(points)
        bound = QFontMetricsF(font, painter.device()).boundingRect(box, flags, text)
        if bound.width() <= box.width() + 0.5 and bound.height() <= box.height() + 0.5:
            return font
        points -= 0.5
    return None


def _label_box(rect: QRectF, dpi: float) -> QRectF:
    """Where a control's inline label goes: its own geometry box, grown to a
    minimum readable footprint (small round buttons are tiny)."""
    min_w, min_h = _mm(dpi, 14.0), _mm(dpi, 6.0)
    w, h = max(rect.width(), min_w), max(rect.height(), min_h)
    return QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)


def _draw_photo_sheet(
    ctx: _Context, sheet: Sheet, dpi: float, new_page: Callable[[], None]
) -> list[tuple[int, SheetEntry]]:
    """Draw one photo page; returns the legend entries that didn't fit."""
    painter = ctx.painter
    pixmap = layout_view.reference_pixmap(sheet.controller)
    top = _start_page(ctx, sheet.title, new_page)
    bottom = _content_bottom(ctx)
    area = QRectF(ctx.page.left(), top, ctx.page.width(), bottom - top)

    # First pass: which labels fit inline, at the photo's full size? Only
    # if some don't does the photo shrink to make room for a legend.
    def place(
        photo: QRectF,
    ) -> tuple[list[tuple[SheetEntry, QRectF, QFont]], list[tuple[SheetEntry, QRectF]]]:
        inline, badges = [], []
        for entry in sheet.entries:
            geom = entry.geometry
            rect = QRectF(
                photo.left() + geom.x * photo.width(),
                photo.top() + geom.y * photo.height(),
                geom.w * photo.width(),
                geom.h * photo.height(),
            )
            box = _label_box(rect, dpi)
            font = _fit_inline(
                painter, "\n".join(entry.functions), box.adjusted(2, 2, -2, -2)
            )
            if font is None:
                badges.append((entry, rect))
            else:
                inline.append((entry, box, font))
        return inline, badges

    def photo_rect(height_limit: float) -> QRectF:
        aspect = pixmap.height() / pixmap.width()
        w = min(area.width(), height_limit / aspect)
        h = w * aspect
        return QRectF(area.left() + (area.width() - w) / 2, area.top(), w, h)

    photo = photo_rect(area.height())
    inline, badges = place(photo)
    if badges:
        photo = photo_rect(area.height() * _PHOTO_SHARE)
        inline, badges = place(photo)

    painter.drawPixmap(photo, pixmap, QRectF(pixmap.rect()))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_UNMAPPED_PEN)
    for geom in sheet.unmapped:
        rect = QRectF(
            photo.left() + geom.x * photo.width(),
            photo.top() + geom.y * photo.height(),
            geom.w * photo.width(),
            geom.h * photo.height(),
        )
        painter.drawEllipse(rect) if geom.shape == "circle" else painter.drawRect(rect)

    flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
    for entry, box, font in inline:
        accent = QColor(entry.geometry.color)
        painter.setPen(QPen(accent, _mm(dpi, 0.5)))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRoundedRect(box, _mm(dpi, 1.0), _mm(dpi, 1.0))
        painter.setPen(_TEXT)
        painter.setFont(font)
        painter.drawText(box.adjusted(2, 2, -2, -2), flags, "\n".join(entry.functions))

    numbered = list(enumerate((entry for entry, _ in badges), start=1))
    radius = _mm(dpi, 2.6)
    painter.setFont(_font(_LEGEND_PT, bold=True))
    for number, (entry, rect) in zip((n for n, _ in numbered), badges, strict=True):
        center = rect.center()
        painter.setPen(QPen(QColor("white"), _mm(dpi, 0.3)))
        painter.setBrush(_BADGE)
        painter.drawEllipse(center, radius, radius)
        painter.drawText(
            QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
            Qt.AlignmentFlag.AlignCenter,
            str(number),
        )
    if not numbered:
        return []
    return _draw_legend(
        ctx,
        numbered,
        QRectF(
            area.left(),
            photo.bottom() + _mm(dpi, 3),
            area.width(),
            bottom - photo.bottom() - _mm(dpi, 3),
        ),
    )


def _legend_text(number: int, entry: SheetEntry) -> str:
    return f"{number}. {entry.control}: " + "; ".join(entry.functions)


def _draw_legend(
    ctx: _Context, numbered: list[tuple[int, SheetEntry]], area: QRectF
) -> list[tuple[int, SheetEntry]]:
    """Numbered legend in three columns; returns what didn't fit."""
    painter = ctx.painter
    painter.setFont(_font(_LEGEND_PT))
    painter.setPen(_TEXT)
    metrics = QFontMetricsF(painter.font(), painter.device())
    columns, gap = 3, metrics.height()
    col_w = (area.width() - gap * (columns - 1)) / columns
    flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
    column, y = 0, area.top()
    for index, (number, entry) in enumerate(numbered):
        text = _legend_text(number, entry)
        height = metrics.boundingRect(QRectF(0, 0, col_w, 1e6), flags, text).height()
        if y + height > area.bottom():
            column, y = column + 1, area.top()
            if column >= columns:
                return numbered[index:]
        painter.drawText(
            QRectF(area.left() + column * (col_w + gap), y, col_w, height), flags, text
        )
        y += height + metrics.height() * 0.25
    return []


def _draw_table(
    ctx: _Context,
    title: str,
    rows: Sequence[tuple[str, str, str]],
    dpi: float,
    new_page: Callable[[], None],
) -> None:
    """A section / control / function table, as many pages as it needs
    (always at least one, so an empty sheet still says so)."""
    painter = ctx.painter
    remaining = list(rows)
    first = True
    while first or remaining:
        top = _start_page(ctx, title if first else f"{title} (continued)", new_page)
        first = False
        bottom = _content_bottom(ctx)
        width = ctx.page.width()
        col_x = [
            ctx.page.left(),
            ctx.page.left() + width * 0.14,
            ctx.page.left() + width * 0.46,
        ]
        col_w = [width * 0.14, width * 0.32, width * 0.54]
        pad = _mm(dpi, 1.0)
        painter.setFont(_font(_TABLE_PT, bold=True))
        metrics = QFontMetricsF(painter.font(), painter.device())
        painter.setPen(_TEXT)
        for x, w, heading in zip(
            col_x, col_w, ("Section", "Control", "Function"), strict=True
        ):
            painter.drawText(
                QRectF(x + pad, top, w - 2 * pad, metrics.height()),
                Qt.AlignmentFlag.AlignLeft,
                heading,
            )
        y = top + metrics.height() * 1.3
        painter.setPen(QPen(_RULE, 1.0))
        painter.drawLine(
            QPointF(ctx.page.left(), y - metrics.height() * 0.15),
            QPointF(ctx.page.right(), y - metrics.height() * 0.15),
        )
        if not remaining:
            painter.setFont(_font(_TABLE_PT))
            painter.setPen(_MUTED)
            painter.drawText(
                QRectF(ctx.page.left(), y, width, metrics.height() * 2),
                Qt.AlignmentFlag.AlignLeft,
                "No control of this controller is mapped in this file.",
            )
            return
        painter.setFont(_font(_TABLE_PT))
        metrics = QFontMetricsF(painter.font(), painter.device())
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
        zebra = False
        while remaining:
            row = remaining[0]
            height = (
                max(
                    metrics.boundingRect(
                        QRectF(0, 0, w - 2 * pad, 1e6), flags, text
                    ).height()
                    for w, text in zip(col_w, row, strict=True)
                )
                + pad
            )
            if y + height > bottom and y > top + metrics.height() * 2:
                break
            if zebra:
                painter.fillRect(QRectF(ctx.page.left(), y, width, height), _ZEBRA)
            zebra = not zebra
            painter.setPen(_TEXT)
            for x, w, text in zip(col_x, col_w, row, strict=True):
                painter.drawText(
                    QRectF(x + pad, y + pad / 2, w - 2 * pad, height), flags, text
                )
            y += height
            remaining.pop(0)


def _entry_rows(entries: Sequence[SheetEntry]) -> list[tuple[str, str, str]]:
    return [(e.section, e.control, "\n".join(e.functions)) for e in entries]


def paint_sheets(
    painter: QPainter,
    page: QRectF,
    dpi: float,
    sheets: Sequence[Sheet],
    footer: str,
    new_page: Callable[[], None],
) -> int:
    """Draw every sheet, calling `new_page` between pages; returns the page
    count."""
    ctx = _Context(painter, page, footer)
    for sheet in sheets:
        if (
            sheet.kind == "photo"
            and layout_view.reference_pixmap(sheet.controller) is not None
        ):
            leftover = _draw_photo_sheet(ctx, sheet, dpi, new_page)
            if leftover:
                rows = [
                    (e.section, f"{n}. {e.control}", "\n".join(e.functions))
                    for n, e in leftover
                ]
                _draw_table(ctx, f"{sheet.title} — legend", rows, dpi, new_page)
        else:
            _draw_table(ctx, sheet.title, _entry_rows(sheet.entries), dpi, new_page)
    return ctx.page_number


def default_footer(source_name: str | None) -> str:
    source = f" — {source_name}" if source_name else ""
    return f"DJ MIDI Studio cheat sheet{source} — {datetime.now().astimezone().date().isoformat()}"


def write_cheat_sheet_pdf(
    path: str | Path, sheets: Sequence[Sheet], source_name: str | None = None
) -> int:
    """Write `sheets` to a PDF at `path`; returns the number of pages."""
    writer = QPdfWriter(str(path))
    writer.setResolution(_DPI)
    writer.setTitle("DJ MIDI Studio cheat sheet")
    writer.setCreator("DJ MIDI Studio")
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
            QPageLayout.Unit.Millimeter,
        )
    )
    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        page = QRectF(writer.pageLayout().paintRectPixels(_DPI))
        page.moveTo(0, 0)
        return (
            paint_sheets(
                painter, page, _DPI, sheets, default_footer(source_name), writer.newPage
            )
            or 0
        )
    finally:
        painter.end()


def render_sheet_image(sheet: Sheet, dpi: int = _DPI) -> QImage:
    """One sheet's first page as an A4-landscape QImage, drawn by the same
    code as the PDF (for tests and doc screenshots)."""
    width, height = round(297 / 25.4 * dpi), round(210 / 25.4 * dpi)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.setDotsPerMeterX(round(dpi / 0.0254))
    image.setDotsPerMeterY(round(dpi / 0.0254))
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        margin = _mm(dpi, _MARGIN_MM)
        page = QRectF(margin, margin, width - 2 * margin, height - 2 * margin)

        class _Stop(Exception):
            pass

        def stop() -> None:
            raise _Stop

        try:
            paint_sheets(painter, page, dpi, [sheet], default_footer(None), stop)
        except _Stop:
            pass
    finally:
        painter.end()
    return image


__all__ = [
    "default_footer",
    "paint_sheets",
    "render_sheet_image",
    "write_cheat_sheet_pdf",
]
