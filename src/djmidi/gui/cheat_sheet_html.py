"""The cheat sheet as one interactive web page (phase 6 item 6).

The same `cheat_sheet.Sheet`s the PDF prints, as a single self-contained
``.html`` file: each controller's reference photo is embedded (no network,
no other file), with a tappable box on every mapped control -- hover or tap
it to read what the mapping binds there -- plus the tables and the glossary.
Made to be opened on a phone or tablet beside the decks.

:func:`build_cheat_sheet_html` is Qt-free (it takes the photos as bytes and
the visible words as a mapping) so it is tested without a QApplication;
:func:`write_cheat_sheet_html` adds the Qt parts: encoding the photos and
translating the words.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from html import escape
from pathlib import Path

from djmidi.gui.cheat_sheet import Sheet
from djmidi.i18n import QT_TRANSLATE_NOOP

# Photos are shrunk to this width before embedding: plenty on a tablet,
# and it keeps a four-controller sheet to a few megabytes.
PHOTO_WIDTH = 1600

DEFAULT_WORDS = {
    "title": QT_TRANSLATE_NOOP("CheatSheetHtml", "DJ MIDI Studio cheat sheet"),
    "hint": QT_TRANSLATE_NOOP("CheatSheetHtml", "Tap or hover a highlighted control to see what it does."),
    "section": QT_TRANSLATE_NOOP("CheatSheetHtml", "Section"),
    "control": QT_TRANSLATE_NOOP("CheatSheetHtml", "Control"),
    "functions": QT_TRANSLATE_NOOP("CheatSheetHtml", "Functions"),
    "close": QT_TRANSLATE_NOOP("CheatSheetHtml", "Close"),
    "no_photo": QT_TRANSLATE_NOOP("CheatSheetHtml", "No picture of this controller: its mapped controls are listed below."),
}

_STYLE = """
:root { color-scheme: dark; --bg:#0d121b; --panel:#151e2b; --text:#e8eef7; --muted:#8fa7bd;
  --accent:#d33c72; --marker:rgba(0,194,232,.28); --marker-line:#00c2e8; --line:#2b3b53; }
* { box-sizing:border-box; }
body { margin:0; padding:16px; background:var(--bg); color:var(--text);
  font:15px/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
h1 { font-size:1.4rem; margin:0 0 4px; } h2 { font-size:1.15rem; margin:28px 0 8px; }
.meta, .hint { color:var(--muted); font-size:.9rem; margin:0 0 8px; }
nav { display:flex; flex-wrap:wrap; gap:6px; margin:12px 0; }
nav a { color:var(--text); background:var(--panel); border:1px solid var(--line); border-radius:6px;
  padding:4px 10px; text-decoration:none; font-size:.9rem; }
.photo { position:relative; max-width:100%; }
.photo img { display:block; width:100%; height:auto; border-radius:8px; }
.marker { position:absolute; border:2px solid var(--marker-line); background:var(--marker);
  border-radius:4px; padding:0; cursor:pointer; }
.marker.round { border-radius:50%; }
.marker.unmapped { border:1px dashed rgba(255,255,255,.25); background:transparent; cursor:default; }
.marker:hover, .marker:focus, .marker.active { background:rgba(211,60,114,.45); border-color:var(--accent);
  outline:none; }
#panel { position:fixed; left:12px; right:12px; bottom:12px; max-width:520px; margin:0 auto;
  background:var(--panel); border:1px solid var(--accent); border-radius:10px; padding:12px 14px;
  box-shadow:0 8px 30px rgba(0,0,0,.5); display:none; }
#panel.open { display:block; }
#panel h3 { margin:0 0 6px; font-size:1rem; }
#panel ul { margin:0; padding-left:18px; }
#panel button { float:right; background:none; border:1px solid var(--line); color:var(--text);
  border-radius:6px; padding:2px 8px; }
table { border-collapse:collapse; width:100%; margin:8px 0; }
th, td { text-align:left; vertical-align:top; padding:6px 8px; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; }
"""

_SCRIPT = """
const panel = document.getElementById('panel');
const title = panel.querySelector('h3');
const list = panel.querySelector('ul');
let active = null;
function show(marker) {
  if (active) active.classList.remove('active');
  active = marker; marker.classList.add('active');
  title.textContent = marker.dataset.control;
  list.replaceChildren(...JSON.parse(marker.dataset.functions).map(t => {
    const li = document.createElement('li'); li.textContent = t; return li; }));
  panel.classList.add('open');
}
document.querySelectorAll('.marker[data-functions]').forEach(m => {
  m.addEventListener('click', () => show(m));
});
panel.querySelector('button').addEventListener('click', () => {
  panel.classList.remove('open'); if (active) active.classList.remove('active'); active = null;
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') panel.querySelector('button').click(); });
"""


def _anchor(index: int) -> str:
    return f"sheet-{index + 1}"


def _marker(entry_control: str, functions: Sequence[str], geometry, mapped: bool) -> str:
    style = (
        f"left:{geometry.x * 100:.3f}%;top:{geometry.y * 100:.3f}%;"
        f"width:{geometry.w * 100:.3f}%;height:{geometry.h * 100:.3f}%"
    )
    classes = "marker" + (" round" if geometry.shape == "circle" else "")
    if not mapped:
        return f'<span class="{classes} unmapped" style="{style}" aria-hidden="true"></span>'
    tooltip = escape(f"{entry_control}: " + " / ".join(functions), quote=True)
    data = escape(json.dumps(list(functions), ensure_ascii=False), quote=True)
    return (
        f'<button class="{classes}" style="{style}" title="{tooltip}" aria-label="{tooltip}" '
        f'data-control="{escape(entry_control, quote=True)}" data-functions="{data}"></button>'
    )


def _table(sheet: Sheet, words: Mapping[str, str]) -> str:
    rows = "".join(
        f"<tr><td>{escape(entry.section)}</td><td>{escape(entry.control)}</td>"
        f"<td>{'<br>'.join(escape(line) for line in entry.functions)}</td></tr>"
        for entry in sheet.entries
    )
    return (
        f"<table><thead><tr><th>{escape(words['section'])}</th><th>{escape(words['control'])}</th>"
        f"<th>{escape(words['functions'])}</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def build_cheat_sheet_html(
    sheets: Sequence[Sheet],
    photo_for: Callable[[str], tuple[bytes, str] | None],
    source_name: str | None = None,
    words: Mapping[str, str] | None = None,
    today: str | None = None,
) -> str:
    """The whole page. `photo_for(controller)` returns (image bytes, MIME
    type) or None; `words` overrides the English page words."""
    words = {**DEFAULT_WORDS, **(words or {})}
    photos: dict[str, str | None] = {}
    sections = []
    for index, sheet in enumerate(sheets):
        parts = [f'<section id="{_anchor(index)}"><h2>{escape(sheet.title)}</h2>']
        if sheet.kind == "photo":
            if sheet.controller not in photos:
                photo = photo_for(sheet.controller)
                photos[sheet.controller] = (
                    f"data:{photo[1]};base64,{base64.b64encode(photo[0]).decode('ascii')}" if photo else None
                )
            source = photos[sheet.controller]
            if source is None:
                parts.append(f'<p class="hint">{escape(words["no_photo"])}</p>')
                parts.append(_table(sheet, words))
            else:
                markers = [_marker("", (), geometry, mapped=False) for geometry in sheet.unmapped]
                markers += [
                    _marker(entry.control, entry.functions, entry.geometry, mapped=True)
                    for entry in sheet.entries
                    if entry.geometry is not None
                ]
                parts.append(
                    f'<div class="photo"><img src="{source}" alt="{escape(sheet.controller, quote=True)}">'
                    + "".join(markers)
                    + "</div>"
                )
                loose = [entry for entry in sheet.entries if entry.geometry is None]
                if loose:
                    parts.append(_table(Sheet(sheet.controller, sheet.title, "table", tuple(loose)), words))
        else:
            parts.append(_table(sheet, words))
        parts.append("</section>")
        sections.append("".join(parts))
    nav = "".join(f'<a href="#{_anchor(index)}">{escape(sheet.title)}</a>' for index, sheet in enumerate(sheets))
    stamp = today or datetime.now().astimezone().date().isoformat()
    meta = " — ".join(part for part in (source_name, stamp) if part)
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(words['title'])}</title><style>{_STYLE}</style></head><body>"
        f"<h1>{escape(words['title'])}</h1><p class=\"meta\">{escape(meta)}</p>"
        f"<p class=\"hint\">{escape(words['hint'])}</p><nav>{nav}</nav>"
        + "".join(sections)
        + f'<div id="panel" role="dialog" aria-live="polite"><button type="button">{escape(words["close"])}</button>'
        "<h3></h3><ul></ul></div>"
        f"<script>{_SCRIPT}</script></body></html>\n"
    )


def _photo_bytes(controller: str) -> tuple[bytes, str] | None:
    """The controller's clean reference photo, shrunk and JPEG-encoded on a
    dark background (the processed photos are transparent around the
    device)."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    from djmidi.gui import layout_view

    pixmap = layout_view.reference_pixmap(controller)
    if pixmap is None or pixmap.isNull():
        return None
    image = pixmap.toImage()
    if image.width() > PHOTO_WIDTH:
        image = image.scaledToWidth(PHOTO_WIDTH, Qt.TransformationMode.SmoothTransformation)
    flat = QImage(image.size(), QImage.Format.Format_RGB32)
    flat.fill(QColor("#0d121b"))
    painter = QPainter(flat)
    painter.drawImage(0, 0, image)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    flat.save(buffer, "JPEG", 85)
    buffer.close()
    return bytes(data.data()), "image/jpeg"


def translated_words() -> dict[str, str]:
    from PySide6.QtCore import QCoreApplication

    return {key: QCoreApplication.translate("CheatSheetHtml", text) for key, text in DEFAULT_WORDS.items()}


def write_cheat_sheet_html(path: str | Path, sheets: Sequence[Sheet], source_name: str | None = None) -> int:
    """Writes the page; returns its size in bytes."""
    text = build_cheat_sheet_html(sheets, _photo_bytes, source_name, translated_words())
    Path(path).write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


__all__ = ["DEFAULT_WORDS", "PHOTO_WIDTH", "build_cheat_sheet_html", "write_cheat_sheet_html"]
