"""French ? help texts name buttons and labels by their French UI names (issue #325).

The help texts (context ``HelpTexts`` of ``djmidi_fr.ts``) quote the labels a
DJ has to look for in bold. Once a widget is translated, its help text must
quote the French label, or the DJ looks for a button that is not on screen.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from djmidi import i18n

# Quoted on purpose in English or not a widget label at all.
_NOT_UI_LABELS = {
    # Serato function names (Live Ready warnings) and the controller's SHIFT key.
    "Play",
    "Cue",
    "Sync",
    "Load",
    "SHIFT",
    # Windows and dialogs not translated yet: the macro editor, the mapping
    # comparison report (mapping_diff.py) and the Stage mode Exit button.
    "Output port",
    "Steps",
    "Add sync set",
    "Shortcut",
    "Trigger",
    "Learn",
    "Test",
    "Re-assigned",
    "Added",
    "Removed",
    "Changed values",
    "Duplicate count",
    "Exit",
    # Keyboard keys and title-bar glyphs.
    "Cmd+K",
    "↑/↓",
    "Entrée",
    "Échap",
    "Espace",
    "Gauche",
    "Droite",
    "☰",
    "⟳",
    "—",
    # Emphasis, not labels.
    "sortie",
    "entrée",
    "couche",
    "toutes",
    "N'a de sens qu'avec un appareil qui renvoie l'écho",
}

_GLYPH_PREFIX = re.compile(r"^[⚙⟳●■]\s*")


def _plain(text: str) -> str:
    """A label as a DJ reads it: no mnemonic, no HTML, no glyph prefix, no
    trailing colon or ellipsis (a menu entry ends in "..." or "…")."""
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    text = re.sub(r"<[^>]+>", "", text).strip()
    text = _GLYPH_PREFIX.sub("", text) or text
    return text.rstrip(".…:").strip()


def _french_ui_labels() -> tuple[set[str], list[re.Pattern[str]]]:
    """Every French UI string outside the help texts, plus its usual shapes:
    the part before a colon, the part before a parenthesis, and each bold
    fragment; strings with ``{placeholders}`` become patterns."""
    root = ET.parse(i18n.translations_dir() / "djmidi_fr.ts").getroot()
    labels: set[str] = set()
    patterns: list[re.Pattern[str]] = []
    for context in root.iter("context"):
        if context.findtext("name") == "HelpTexts":
            continue
        for message in context.iter("message"):
            translation = message.findtext("translation") or ""
            for raw in [translation, *re.findall(r"<b>(.*?)</b>", translation)]:
                label = _plain(raw)
                labels.update({label, label.split(" :")[0].strip(), label.split(" (")[0].strip()})
                if "{" in label:
                    patterns.append(re.compile(re.sub(r"\\\{\w+\\\}", r".+", re.escape(label))))
    return labels, patterns


def _help_quoted_labels() -> list[str]:
    """Every bold label of the French help texts; a menu path is split on →."""
    root = ET.parse(i18n.translations_dir() / "djmidi_fr.ts").getroot()
    quoted: list[str] = []
    for context in root.iter("context"):
        if context.findtext("name") != "HelpTexts":
            continue
        for message in context.iter("message"):
            for bold in re.findall(r"<b>(.*?)</b>", message.findtext("translation") or "", re.DOTALL):
                quoted.extend(_plain(part) for part in bold.split("→"))
    return quoted


def test_help_texts_quote_bold_labels():
    assert len(_help_quoted_labels()) > 100


def test_french_help_texts_quote_the_french_ui_labels():
    labels, patterns = _french_ui_labels()
    unknown = sorted(
        {
            label
            for label in _help_quoted_labels()
            if label not in _NOT_UI_LABELS
            and label not in labels
            and not any(pattern.fullmatch(label) for pattern in patterns)
        }
    )
    assert not unknown, f"French help texts quote labels the French UI does not show: {unknown}"


def test_not_ui_labels_are_still_quoted():
    """Keep the exception list honest: drop an entry once no help text quotes it."""
    assert _NOT_UI_LABELS <= set(_help_quoted_labels())
