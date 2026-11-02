"""Translated ? help texts name buttons and labels by their translated UI names
(issue #325 for French, German since v0.48.176).

The help texts (context ``HelpTexts`` of ``djmidi_<language>.ts``) quote the
labels a DJ has to look for in bold. Once a widget is translated, its help
text must quote the translated label, or the DJ looks for a button that is
not on screen.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

import pytest

from djmidi import i18n

# Quoted on purpose in English or not a widget label at all.
_NOT_FRENCH_UI_LABELS = {
    # Serato function names (Live Ready warnings) and the controller's SHIFT key.
    "Play",
    "Cue",
    "Sync",
    "Load",
    "SHIFT",
    # Qt's own standard button (translated by Qt's catalogue, not ours).
    "Enregistrer",
    # A folder name on disk.
    "Snapshots",
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

_NOT_GERMAN_UI_LABELS = {
    # Serato function names (Live Ready warnings) and the controller's SHIFT key.
    "Play",
    "Load",
    "SHIFT",
    # Qt's own standard button and a folder name on disk.
    "Speichern",
    "Snapshots",
    # Keyboard keys and title-bar glyphs.
    "Cmd+K",
    "↑/↓",
    "Enter",
    "Esc",
    "Leertaste",
    "Links",
    "Rechts",
    "☰",
    "⟳",
    "—",
    # Emphasis, not labels.
    "Eingang",
    "Ebene",
    "alle",
    "Schritte",
    "Nur sinnvoll mit etwas, das ein Echo liefert",
}

_NOT_UI_LABELS = {"fr": _NOT_FRENCH_UI_LABELS, "de": _NOT_GERMAN_UI_LABELS}

_GLYPH_PREFIX = re.compile(r"^[⚙⟳●■▶◀]\s*")


def _plain(text: str, mnemonics: bool = True) -> str:
    """A label as a DJ reads it: no mnemonic, no HTML, no glyph prefix, no
    trailing colon or ellipsis (a menu entry ends in "..." or "…")."""
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    if mnemonics:  # a UI label's "&" marks a shortcut; in rich text it's literal
        text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    text = _GLYPH_PREFIX.sub("", text) or text
    return text.rstrip(".…:").strip()


def _ui_labels(language: str) -> tuple[set[str], list[re.Pattern[str]]]:
    """Every translated UI string outside the help texts, plus its usual
    shapes: the part before a colon, the part before a parenthesis, and each
    bold fragment; strings with ``{placeholders}`` become patterns."""
    root = ET.parse(i18n.translations_dir() / f"djmidi_{language}.ts").getroot()
    labels: set[str] = set()
    patterns: list[re.Pattern[str]] = []
    for context in root.iter("context"):
        if context.findtext("name") == "HelpTexts":
            continue
        for message in context.iter("message"):
            translation = message.findtext("translation") or ""
            for raw in [translation, *re.findall(r"<b>(.*?)</b>", translation)]:
                label = _plain(raw)
                labels.update({
                    label, label.split(" :")[0].strip(), label.split(":")[0].strip(), label.split(" (")[0].strip(),
                })  # fmt: skip
                # A label that is nothing but placeholders ("{name}") would
                # become ".+" and match any text: it isn't a label to look for.
                if "{" in label and re.search(r"[^\W\d_]", re.sub(r"\{\w+\}", "", label)):
                    patterns.append(re.compile(re.sub(r"\\\{\w+\\\}", r".+", re.escape(label))))
    return labels, patterns


def _help_quoted_labels(language: str) -> list[str]:
    """Every bold label of the help texts in `language`; a menu path is split on →."""
    root = ET.parse(i18n.translations_dir() / f"djmidi_{language}.ts").getroot()
    quoted: list[str] = []
    for context in root.iter("context"):
        if context.findtext("name") != "HelpTexts":
            continue
        for message in context.iter("message"):
            for bold in re.findall(r"<b>(.*?)</b>", message.findtext("translation") or "", re.DOTALL):
                quoted.extend(_plain(part, mnemonics=False) for part in bold.split("→"))
    return quoted


@pytest.mark.parametrize("language", sorted(_NOT_UI_LABELS))
def test_help_texts_quote_bold_labels(language):
    assert len(_help_quoted_labels(language)) > 100


@pytest.mark.parametrize("language", sorted(_NOT_UI_LABELS))
def test_help_texts_quote_the_translated_ui_labels(language):
    labels, patterns = _ui_labels(language)
    unknown = sorted(
        {
            label
            for label in _help_quoted_labels(language)
            if label not in _NOT_UI_LABELS[language]
            and label not in labels
            and not any(pattern.fullmatch(label) for pattern in patterns)
        }
    )
    assert not unknown, f"{language} help texts quote labels its UI does not show: {unknown}"


@pytest.mark.parametrize("language", sorted(_NOT_UI_LABELS))
def test_not_ui_labels_are_still_quoted(language):
    """Keep the exception lists honest: drop an entry once no help text quotes it."""
    assert _NOT_UI_LABELS[language] <= set(_help_quoted_labels(language))


def test_an_unknown_quoted_label_is_caught(monkeypatch):
    """Negative control: the check once matched everything through a
    placeholder-only translation ("{name}" -> ".+")."""
    import test_help_labels as module

    original = module._help_quoted_labels
    monkeypatch.setattr(module, "_help_quoted_labels", lambda language: [*original(language), "No such button"])
    for language in _NOT_UI_LABELS:
        with pytest.raises(AssertionError, match="No such button"):
            module.test_help_texts_quote_the_translated_ui_labels(language)


def test_every_translated_language_is_checked():
    assert set(_NOT_UI_LABELS) == {lang for lang in i18n.SUPPORTED_LANGUAGES if lang != i18n.SOURCE_LANGUAGE}
