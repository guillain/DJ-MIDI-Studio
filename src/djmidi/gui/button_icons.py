"""An icon on every text button (UX review), without touching each of the
~230 buttons: when a button is first polished, its role is read from its
**English** text (or, in a dialog's button box, from its standard button)
and it gets that role's line icon (`gui/icons.py`).

Buttons are built with already translated text; the role is looked up on
the English source, found through the active catalogue (``djmidi_<lang>.ts``,
read once, translation → source). Purely cosmetic: a button whose text maps
to no role simply keeps no icon. Buttons that already have an icon, glyph
buttons (``compact``, or text starting with a symbol such as ▶ ■ ●) and the
grouped action chips are left as they are.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from functools import cache

from PySide6.QtCore import QEvent, QObject, QSize
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from djmidi.gui.icons import line_icon

_LOGGER = logging.getLogger(__name__)

# First match wins: English source text (lower case, no "&", no "…") → role.
ROLE_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"\bmove up\b", "up"),
    (r"\bmove down\b", "down"),
    (r"\b(delete|remove|discard|trash|forget|uninstall)\b", "delete"),
    (r"\b(undo|back to|go back|previous)\b", "undo"),
    (r"\b(redo|next)\b", "redo"),
    (r"\b(stop|cancel scan|halt)\b", "stop"),
    (r"\b(play|send|start|test|listen|preview|replay|light|probe|run)\b", "play"),
    (r"\b(save|keep)\b", "save"),
    (r"\b(export|submit|share|copy to|push)\b", "export"),
    (r"\b(import|load|install|download|fetch)\b", "import"),
    (r"\b(compare|diff|swap)\b", "compare"),
    (r"\b(add|new|create|insert|duplicate|record|learn|capture)\b", "add"),
    (r"\b(refresh|rescan|scan|sync|reload|retry|recompute|resync|detect)\b", "auto"),
    (r"\b(clear|reset|clean|restore)\b", "clean"),
    (r"\b(open|browse|choose|pick|show|reveal|locate|folder|file)\b", "files"),
    (r"\b(edit|rename|change|move|assign|map|write)\b", "edit"),
    (r"\b(apply|confirm|done|ok|accept|verify|check|validate|use|yes|ready)\b", "confirm"),
    (r"\b(images?|photos?|pictures?|cover|geometry)\b", "image"),
    (r"\b(generate|build|auto|propose|suggest|analy[sz]e|estimate|smart)\b", "smart"),
    (r"\b(help|guide|about|tips?|notes?)\b", "help"),
    (r"\b(list|report|history|log|statistics|stats|details|summary|copy)\b", "list"),
    (r"\b(up)\b", "up"),
    (r"\b(down)\b", "down"),
    (r"\b(close|done|quit|dismiss|skip|no)\b", "stop"),
    (r"\b(revert|back)\b", "revert"),
    (r"\b(fail|block|disable|exit|some didn't|odd)\b", "stop"),
    (r"\b(pass|enable|lit|tick|select)\b", "confirm"),
    (r"\b(place|paint|name|remap|merge|organi[sz]e|relink)\b", "edit"),
    (r"\b(find|duplicates)\b", "compare"),
    (r"\b(playlists?|crate|nml|xml)\b", "list"),
    (r"\bset\b", "edit"),
    # Last: a button naming a place goes there (the Dashboard's drill-downs).
    (r"\b(channel|deck|controller|library|music|monitor|routing|clock|metronome)\b", "redo"),
)
_COMPILED = tuple((re.compile(pattern), role) for pattern, role in ROLE_KEYWORDS)

_STANDARD_ROLES = {
    QDialogButtonBox.StandardButton.Ok: "confirm",
    QDialogButtonBox.StandardButton.Yes: "confirm",
    QDialogButtonBox.StandardButton.YesToAll: "confirm",
    QDialogButtonBox.StandardButton.Apply: "confirm",
    QDialogButtonBox.StandardButton.Save: "save",
    QDialogButtonBox.StandardButton.SaveAll: "save",
    QDialogButtonBox.StandardButton.Open: "files",
    QDialogButtonBox.StandardButton.Cancel: "stop",
    QDialogButtonBox.StandardButton.Close: "stop",
    QDialogButtonBox.StandardButton.No: "stop",
    QDialogButtonBox.StandardButton.NoToAll: "stop",
    QDialogButtonBox.StandardButton.Abort: "stop",
    QDialogButtonBox.StandardButton.Discard: "delete",
    QDialogButtonBox.StandardButton.Reset: "clean",
    QDialogButtonBox.StandardButton.RestoreDefaults: "clean",
    QDialogButtonBox.StandardButton.Help: "help",
    QDialogButtonBox.StandardButton.Retry: "auto",
}


def _clean(text: str) -> str:
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").replace("…", "").strip()


def role_for_text(english: str) -> str | None:
    text = _clean(english).lower()
    return next((role for pattern, role in _COMPILED if pattern.search(text)), None)


@cache
def _sources(language: str) -> dict[str, str]:
    """translation → English source for the active catalogue."""
    from djmidi.i18n import translation_file

    path = translation_file(language)
    if path is None:
        return {}
    ts = path.with_suffix(".ts")
    try:
        root = ET.parse(ts).getroot()
    except (OSError, ET.ParseError):
        _LOGGER.info("No %s catalogue to read button roles from", ts)
        return {}
    sources: dict[str, str] = {}
    for message in root.iter("message"):
        source, translation = message.findtext("source"), message.findtext("translation")
        if source and translation:
            sources.setdefault(_clean(translation), source)
    return sources


class ButtonIconDecorator(QObject):
    """Installed once on the application (``install``)."""

    def __init__(self, language: str = "en", colour: str = "#00c2e8", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.colour = colour

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Polish and isinstance(watched, QPushButton):
            self.decorate(watched)
        return False

    def role_for(self, button: QPushButton) -> str | None:
        box = button.parent()
        if isinstance(box, QDialogButtonBox):
            standard = box.standardButton(button)
            if standard in _STANDARD_ROLES:
                return _STANDARD_ROLES[standard]
        text = _clean(button.text())
        if not text or not text[0].isalnum():
            return None  # a glyph button: ▶ Play, ● Rec, ?, ⚙…
        english = text if self.language == "en" else _sources(self.language).get(text, "")
        return role_for_text(english) if english else None

    def decorate(self, button: QPushButton) -> bool:
        if not button.icon().isNull() or button.property("compact") or button.property("chip"):
            return False
        role = self.role_for(button)
        if role is None:
            return False
        button.setIcon(line_icon(role, self.colour))
        button.setIconSize(QSize(15, 15))
        return True


_INSTALLED: list[ButtonIconDecorator] = []  # kept alive for the app's lifetime


def install(app: QApplication, language: str, colour: str) -> ButtonIconDecorator:
    decorator = ButtonIconDecorator(language, colour, app if isinstance(app, QObject) else None)
    app.installEventFilter(decorator)
    _INSTALLED.append(decorator)
    return decorator


__all__ = ["ROLE_KEYWORDS", "ButtonIconDecorator", "install", "role_for_text"]
