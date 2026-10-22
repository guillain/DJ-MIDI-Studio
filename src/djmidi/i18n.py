"""Interface language choice (issue #263), independent of Qt.

The preference stores ``"system"``, ``"en"`` or ``"fr"``; ``resolve_language``
turns it into the language actually shown, given the OS locale name Qt reports
(``QLocale.system().name()``, e.g. ``"fr_FR"``).  English is the source
language of every string, so it needs no translation file; any other
supported language has a compiled ``djmidi_<code>.qm`` beside its editable
``.ts`` catalogue in ``translations/`` (see ``scripts/update_translations.sh``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

Translate = Callable[[str], str]
"""Turns an English text marked with ``QT_TRANSLATE_NOOP`` into the interface
language (issue #313).  Qt-free modules that build a sentence from a template
take one as an optional argument; the GUI passes
``gui.translation.translator(context)``, tests and scripts keep the default."""


def untranslated(text: str) -> str:
    """The default `Translate`: English, as written in the code."""
    return text


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:
    """Marks `text` for the interface catalogue under `context` without
    importing Qt: pyside6-lupdate finds the call by its name (the module must be
    listed in ``scripts/update_translations.sh``) and the GUI translates the
    text with ``QCoreApplication.translate(context, text)``."""
    return text

LanguagePreference = Literal["system", "en", "fr"]

#: Source language of every user-visible string in the code.
SOURCE_LANGUAGE = "en"

#: Languages with a translation (plus the source language), in menu order.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "fr")

#: Preference values and the label each one shows in Preferences.  The
#: language names are written in their own language, so a user who cannot
#: read the current interface still finds theirs.
LANGUAGE_CHOICES: tuple[tuple[LanguagePreference, str], ...] = (
    ("system", "System"),
    ("en", "English"),
    ("fr", "Français"),
)

LANGUAGE_PREFERENCES: tuple[str, ...] = tuple(value for value, _label in LANGUAGE_CHOICES)


def resolve_language(preference: str, system_locale: str = "") -> str:
    """The language to show for ``preference`` on a system whose locale is ``system_locale``.

    An explicit supported language wins; ``"system"`` takes the locale's
    language part (``"fr_CA"`` → ``"fr"``) when it is supported; anything
    else falls back to English rather than guessing.
    """
    if preference in SUPPORTED_LANGUAGES:
        return preference
    if preference == "system":
        code = system_locale.replace("-", "_").split("_", 1)[0].strip().lower()
        if code in SUPPORTED_LANGUAGES:
            return code
    return SOURCE_LANGUAGE


def translations_dir() -> Path:
    """Folder holding the ``.ts`` catalogues and their compiled ``.qm`` files.

    Inside the package, so a wheel ships it and a PyInstaller build finds it at
    the same relative place (``scripts/build.sh`` adds it as data)."""
    return Path(__file__).resolve().parent / "translations"


def translation_file(language: str) -> Path | None:
    """The compiled catalogue for ``language``, or None for the source language."""
    if language == SOURCE_LANGUAGE or language not in SUPPORTED_LANGUAGES:
        return None
    return translations_dir() / f"djmidi_{language}.qm"


__all__ = [
    "LANGUAGE_CHOICES",
    "LANGUAGE_PREFERENCES",
    "QT_TRANSLATE_NOOP",
    "SOURCE_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "LanguagePreference",
    "Translate",
    "resolve_language",
    "translation_file",
    "translations_dir",
    "untranslated",
]
