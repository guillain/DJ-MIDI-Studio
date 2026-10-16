"""Interface language (issue #263): preference, resolution, catalogue and translator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from djmidi import i18n
from djmidi.plugins import PluginPreferences

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "update_translations.sh"


def _script_sources() -> list[Path]:
    """The SOURCES array of scripts/update_translations.sh, so the test and the
    pipeline can never disagree about which files carry tr() strings."""
    text = _SCRIPT.read_text(encoding="utf-8")
    block = text.split("SOURCES=(", 1)[1].split(")", 1)[0]
    return [_ROOT / line.strip() for line in block.splitlines() if line.strip()]


def _qt_tool(name: str) -> str | None:
    found = shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))
    return found


# --- Qt-free core --------------------------------------------------------------


@pytest.mark.parametrize(
    ("preference", "locale", "expected"),
    [
        ("en", "fr_FR", "en"),
        ("fr", "en_US", "fr"),
        ("system", "fr_FR", "fr"),
        ("system", "fr-CA", "fr"),
        ("system", "FR", "fr"),
        ("system", "en_GB", "en"),
        ("system", "de_DE", "en"),
        ("system", "", "en"),
        ("klingon", "fr_FR", "en"),
    ],
)
def test_resolve_language(preference, locale, expected):
    assert i18n.resolve_language(preference, locale) == expected


def test_translation_file_only_for_translated_languages():
    assert i18n.translation_file("en") is None
    assert i18n.translation_file("de") is None
    assert i18n.translation_file("fr") == i18n.translations_dir() / "djmidi_fr.qm"


def test_every_translated_language_ships_a_catalogue():
    for language in i18n.SUPPORTED_LANGUAGES:
        if language == i18n.SOURCE_LANGUAGE:
            continue
        assert i18n.translation_file(language).is_file()
        assert i18n.translation_file(language).with_suffix(".ts").is_file()


def test_language_choices_cover_every_supported_language():
    assert set(i18n.SUPPORTED_LANGUAGES) | {"system"} == set(i18n.LANGUAGE_PREFERENCES)


# --- Preference ----------------------------------------------------------------


def test_language_preference_defaults_to_english():
    assert PluginPreferences().language == "en"
    assert PluginPreferences.from_json(json.dumps({"enabled": {}})).language == "en"


def test_language_preference_roundtrips():
    preferences = PluginPreferences(language="fr")
    assert PluginPreferences.from_json(preferences.to_json()).language == "fr"


def test_unknown_language_falls_back_without_losing_other_preferences():
    loaded = PluginPreferences.from_json(json.dumps({"enabled": {}, "language": "de", "theme": "dark"}))
    assert loaded.language == "en"
    assert loaded.theme == "dark"


# --- Catalogue -----------------------------------------------------------------


def test_french_catalogue_is_complete():
    root = ET.parse(i18n.translations_dir() / "djmidi_fr.ts").getroot()
    messages = list(root.iter("message"))
    assert len(messages) > 50
    for message in messages:
        translation = message.find("translation")
        source = message.find("source").text
        assert translation.get("type") is None, f"untranslated: {source!r}"
        assert (translation.text or "").strip(), f"empty translation: {source!r}"


def test_catalogue_lists_every_wrapped_string(tmp_path):
    """Running lupdate over the sources finds nothing new: every tr() string
    added to main_window.py / preferences_dialog.py has been translated."""
    lupdate = _qt_tool("pyside6-lupdate")
    if lupdate is None:
        pytest.skip("pyside6-lupdate not installed")
    catalogue = tmp_path / "djmidi_fr.ts"
    shutil.copy(i18n.translations_dir() / "djmidi_fr.ts", catalogue)
    subprocess.run(
        [lupdate, "-no-obsolete", "-locations", "none", *map(str, _script_sources()), "-ts", str(catalogue)],
        check=True,
        capture_output=True,
    )
    unfinished = [
        message.find("source").text
        for message in ET.parse(catalogue).getroot().iter("message")
        if message.find("translation").get("type") == "unfinished"
    ]
    assert unfinished == [], "run scripts/update_translations.sh and translate: " + repr(unfinished)


def test_compiled_catalogue_matches_its_source(tmp_path):
    lrelease = _qt_tool("pyside6-lrelease")
    if lrelease is None:
        pytest.skip("pyside6-lrelease not installed")
    compiled = tmp_path / "djmidi_fr.qm"
    subprocess.run(
        [lrelease, str(i18n.translations_dir() / "djmidi_fr.ts"), "-qm", str(compiled)],
        check=True,
        capture_output=True,
    )
    assert compiled.read_bytes() == (i18n.translations_dir() / "djmidi_fr.qm").read_bytes(), (
        "djmidi_fr.qm is stale: run scripts/update_translations.sh"
    )


def test_compiled_catalogue_translates_menus():
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    assert translator.translate("MainWindow", "&File") == "&Fichier"
    assert translator.translate("MainWindow", "Music Library") == "Bibliothèque"
    assert translator.translate("PreferencesDialog", "Language:") == "Langue :"


# --- GUI -----------------------------------------------------------------------


def test_main_window_is_english_without_a_translator():
    """No translator is installed by the test session: the suite stays English."""
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        titles = [action.text() for action in window.menuBar().actions()]
        assert "&File" in titles
        assert window.left_tabs.tabText(window._tab_indexes["library"]) == "Music Library"
    finally:
        window.close()
        window.deleteLater()


def test_install_translators_french_then_back_to_english(monkeypatch):
    from djmidi.gui import translation

    app = QCoreApplication.instance()
    installed: list[QTranslator] = []
    monkeypatch.setattr(app, "installTranslator", lambda t: installed.append(t) or True)
    assert translation.install_translators(app, "en") == "en"
    assert installed == []
    assert translation.install_translators(app, "fr") == "fr"
    assert installed and installed[0].translate("MainWindow", "&Help") == "Aid&e"


def test_install_translators_survives_a_missing_catalogue(monkeypatch, tmp_path):
    from djmidi.gui import translation

    app = QCoreApplication.instance()
    monkeypatch.setattr(translation, "translation_file", lambda _language: tmp_path / "missing.qm")
    monkeypatch.setattr(app, "installTranslator", lambda _t: pytest.fail("nothing to install"))
    assert translation.install_translators(app, "fr") == "en"


def test_preferences_dialog_saves_language_and_keeps_tab_keys():
    from djmidi.gui.preferences_dialog import PreferencesDialog

    preferences = PluginPreferences()
    dialog = PreferencesDialog(preferences)
    try:
        assert dialog._language.currentData() == "en"
        dialog._language.setCurrentIndex(dialog._language.findData("fr"))
        assert dialog._language.currentText() == "Français"
        keys = [dialog.tabs.tabBar().tabData(index) for index in range(dialog.tabs.count())]
        assert keys == ["General", "Plugins", "Controller sync"]
        dialog._save()
        assert preferences.language == "fr"
    finally:
        dialog.deleteLater()


# --- Follow-up windows (issue #281) --------------------------------------------


def test_compiled_catalogue_translates_the_follow_up_menu_entries():
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    assert translator.translate("MainWindow", "Ready for &Live…") == "Prêt pour le &live…"
    assert translator.translate("MainWindow", "MIDI Latency Test…") == "Test de latence MIDI…"
    assert translator.translate("MainWindow", "Layer Map…") == "Carte des couches…"
    assert translator.translate("MainWindow", "First-Run &Setup...") == "Configuration &initiale..."
    assert translator.translate("MusicLibraryView", "Statistics…") == "Statistiques…"


def test_every_formatted_translation_keeps_its_placeholders():
    """A `{name}` placeholder renamed or dropped in French would raise (or
    print a wrong value) when the code calls .format() on the translation."""
    import re

    root = ET.parse(i18n.translations_dir() / "djmidi_fr.ts").getroot()
    for message in root.iter("message"):
        source = message.find("source").text
        translation = message.find("translation").text or ""
        placeholders = sorted(re.findall(r"\{\w*\}", source))
        assert sorted(re.findall(r"\{\w*\}", translation)) == placeholders, source


@pytest.fixture
def french():
    """Installs the French catalogue for one test (the suite is English otherwise)."""
    app = QCoreApplication.instance()
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    app.installTranslator(translator)
    try:
        yield
    finally:
        app.removeTranslator(translator)


def test_follow_up_windows_show_french_under_the_french_catalogue(french, tmp_path):
    from djmidi.gui.first_run_wizard import FirstRunWizard
    from djmidi.gui.layer_map_dialog import LayerMapDialog
    from djmidi.gui.live_ready_dialog import LiveReadyDialog
    from djmidi.gui.midi_latency_dialog import MidiLatencyDialog
    from djmidi.live_ready import ReadyReport
    from djmidi.model import MidiConfig

    wizard = FirstRunWizard(list, home=tmp_path)
    latency = MidiLatencyDialog(list_outputs=list, list_inputs=list)
    layer_map = LayerMapDialog(lambda: MidiConfig(), [("DDJ-XP2", 0)], "DDJ-XP2")
    live_ready = LiveReadyDialog(ReadyReport(findings=[], decks=()))
    try:
        assert wizard.windowTitle() == "Bienvenue dans DJ MIDI Studio"
        # Wizard pages are their own classes: their own tr() context.
        assert wizard.controllers_page.title() == "Vos contrôleurs"
        assert wizard.mapping_page.title() == "Votre mapping Serato"
        assert latency.windowTitle() == "Test de latence MIDI"
        assert latency.start_button.text() == "Démarrer"
        assert live_ready.windowTitle() == "Prêt pour le live"
        assert layer_map.windowTitle() == "Carte des couches"
        # The section filter goes by index, so a translated "All sections" still shows every row.
        assert layer_map.section_combo.itemText(0) == "Toutes les sections"
        assert layer_map.table.rowCount() == len(layer_map.layer_map.rows)
        assert "combinaison(s) libre(s)" in layer_map.summary_label.text()
    finally:
        for window in (wizard, latency, layer_map, live_ready):
            window.close()
            window.deleteLater()
