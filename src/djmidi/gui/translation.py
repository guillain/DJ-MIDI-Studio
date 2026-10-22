"""Installs the interface translation chosen in Preferences (issue #263).

Called once by ``gui.app.run`` before the main window is built: Qt resolves
``tr()`` when a widget sets its text, so a language change applies at the next
launch.  Tests never call it, so the suite always runs in English.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from djmidi.i18n import SOURCE_LANGUAGE, resolve_language, translation_file

_LOGGER = logging.getLogger(__name__)


def install_translators(app: QCoreApplication, preference: str) -> str:
    """Load the app catalogue (and Qt's own, for standard buttons) for ``preference``.

    Returns the language in use.  A missing or unreadable catalogue is logged
    and the interface stays in English rather than failing to start.
    """
    language = resolve_language(preference, QLocale.system().name())
    if language == SOURCE_LANGUAGE:
        return language
    path = translation_file(language)
    translator = QTranslator(app)
    if path is None or not translator.load(str(path)):
        _LOGGER.warning("No %s translation found at %s; using English", language, path)
        return SOURCE_LANGUAGE
    app.installTranslator(translator)
    # Qt's own strings (OK/Cancel, Undo %1, file dialogs) ship with PySide6.
    qt_translator = QTranslator(app)
    if qt_translator.load(f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_translator)
    _LOGGER.info("Interface language: %s", language)
    return language


def translator(context: str) -> Callable[[str], str]:
    """A `djmidi.i18n.Translate` for the strings a Qt-free module marked with
    ``QT_TRANSLATE_NOOP(context, ...)`` (issue #313)."""
    return lambda text: QCoreApplication.translate(context, text)


__all__ = ["install_translators", "translator"]
