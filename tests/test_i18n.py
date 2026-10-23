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


# --- Leftovers (issue #306) ----------------------------------------------------


def test_compiled_catalogue_translates_the_issue_306_leftovers():
    from djmidi.library.rename import RELINK_WARNING
    from djmidi.midi_latency import ECHO_WARNING

    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    for context, source in [
        ("MainWindow", "Sync controllers: send each connected controller its recorded initialization set"),
        ("MainWindow", "A controller sync recording is in progress. Save it before quitting?"),
        ("MainWindow", "Recording discarded: the stored sync set(s) were kept"),
        ("MidiLatencyDialog", ECHO_WARNING),
        ("RenameFilesDialog", RELINK_WARNING),
        ("SetPreparationPanel", "Add selection"),
        ("AudioPreviewBar", "Auto-advance"),
    ]:
        translated = translator.translate(context, source)
        assert translated and translated != source, (context, source)
    assert translator.translate("MainWindow", "Recording in progress") == "Enregistrement en cours"
    assert translator.translate("MusicLibraryView", "History") == "Historique"


def test_qt_free_warnings_stay_english_and_are_scanned():
    """The two warnings live in Qt-free modules: their own QT_TRANSLATE_NOOP
    returns the text unchanged, and update_translations.sh scans them."""
    from djmidi.library import rename
    from djmidi.midi_latency import ECHO_WARNING

    assert ECHO_WARNING.startswith("Only meaningful with a port")
    assert rename.RELINK_WARNING.startswith("Serato, Traktor and Rekordbox")
    sources = {path.name for path in _script_sources()}
    assert {"midi_latency.py", "rename.py", "set_preparation.py", "audio_preview.py"} <= sources


def test_main_window_sync_and_rec_show_french(french):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window._record_button.toolTip().startswith("Enregistrer la configuration des contrôleurs")
        assert window._sync_button.toolTip().startswith("Synchroniser les contrôleurs")
        assert window._sync_scene_combo.toolTip().startswith("Scène de synchro")
        combo = window._sync_scene_combo
        assert combo.itemText(combo.count() - 1) == "Nouvelle scène…"
    finally:
        window.close()
        window.deleteLater()


def test_library_tab_and_dialogs_show_french(french):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from djmidi.gui import music_library_view as mlv
    from djmidi.gui.midi_latency_dialog import MidiLatencyDialog
    from djmidi.gui.rename_files_dialog import RenameFilesDialog
    from djmidi.library import workspace
    from djmidi.library.rename import RenamePlan

    view = mlv.MusicLibraryView(db_path=":memory:")
    latency = MidiLatencyDialog(list_outputs=list, list_inputs=list)
    rename_dialog = RenameFilesDialog(lambda template: RenamePlan(template, ()), "{artist} - {title}")
    mix = mlv.MixPathDialog(workspace.MixPathOptions(direction="down"), 3)
    try:
        tabs = [view.side_tabs.tabText(index) for index in range(view.side_tabs.count())]
        assert tabs == ["Morceau", "Catégories", "Playlists", "Historique", "Set"]
        assert view.scan_button.text() == "Scanner et lire les tags"
        assert view.audio_preview.auto_advance_check.text() == "Enchaîner"
        assert view.set_panel.add_button.text() == "Ajouter la sélection"
        assert view.table_model.headerData(0, Qt.Orientation.Horizontal) == "Titre"
        # The filters still go by data, not by the translated label.
        view.ensure_open()
        assert view.category_filter.itemText(0) == "Toutes les catégories"
        assert view.category_filter.itemData(1) == mlv.UNCATEGORIZED
        warning = latency.findChild(QLabel, "latencyEchoWarning")
        assert "renvoie" in warning.text()
        assert any("relocalisiez" in label.text() for label in rename_dialog.findChildren(QLabel))
        # The mix-path direction is read from the item data, not its French text.
        assert mix.direction_combo.currentText() == "BPM décroissant"
        assert mix.options().direction == "down"
    finally:
        view.close_db()
        for window in (view, latency, rename_dialog, mix):
            window.close()
            window.deleteLater()


# --- Remaining English (issue #313) --------------------------------------------


def test_qt_free_summaries_stay_english_by_default_and_are_scanned():
    """Without a `translate` argument the Qt-free modules keep their English
    text (scripts, CSV export, the English suite); their QT_TRANSLATE_NOOP
    marks are scanned by update_translations.sh."""
    from djmidi.controller_sync import SyncResult, summarize_results
    from djmidi.library import set_prep
    from djmidi.library.health import ISSUE_LABELS, ISSUE_LOW_BITRATE
    from djmidi.library.smart_playlist import SORT_LABELS, SORT_MIX, SmartRules

    assert summarize_results([SyncResult("XDJ-XZ", None, error="not connected")]) == (
        "Synced 0/1 controller(s): XDJ-XZ (not connected)"
    )
    assert SmartRules(bpm_min=170).describe() == "BPM ≥ 170"
    assert SORT_LABELS[SORT_MIX] == "Category, BPM range, then key"
    assert ISSUE_LABELS[ISSUE_LOW_BITRATE] == "Low bitrate"
    assert set_prep.SetSummary(3, 1, 1).text == (
        "3 track(s) · 1 incompatible transition(s) · 1 unchecked (missing BPM/key)"
    )
    sources = {path.name for path in _script_sources()}
    assert {
        "controller_sync.py",
        "set_prep.py",
        "smart_playlist.py",
        "health.py",
        "duplicates_dialog.py",
        "health_report_dialog.py",
    } <= sources


def test_compiled_catalogue_translates_the_live_monitor_lock_tooltip():
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    assert translator.translate(
        "MainWindow", "● Rec is recording: the Live Monitor keeps its current inputs until you click ■ Stop"
    ).startswith("● Enr enregistre")


def test_qt_free_summaries_show_french_through_a_translator(french):
    from djmidi.controller_sync import SyncResult, summarize_results
    from djmidi.gui.translation import translator
    from djmidi.library import set_prep
    from djmidi.library.smart_playlist import SmartRules

    sync = translator("ControllerSync")
    results = [SyncResult("DDJ-XP2", "DDJ-XP2", 12), SyncResult("XDJ-XZ", None, error="not connected")]
    assert summarize_results(results, sync) == (
        "1/2 contrôleur(s) synchronisé(s) : DDJ-XP2 (12 msg), XDJ-XZ (non connecté)"
    )
    assert summarize_results([], sync) == "Aucun jeu de synchronisation enregistré"
    # An exception's own message has no catalogue entry: shown as raised.
    assert "port busy" in summarize_results([SyncResult("DDJ-XP2", "DDJ-XP2", 0, "port busy")], sync)

    panel = translator("SetPreparationPanel")
    track = set_prep.SetTrack
    clash = set_prep.analyze_transition(0, track("a", bpm=140, camelot_key="8A"), track("b", bpm=160), translate=panel)
    assert clash.issues == ("Saut de BPM +14.3 % (tolérance ±6 %)", "Tonalité inconnue")
    assert set_prep.SetSummary(3, 1, 1).describe(panel) == (
        "3 morceau(x) · 1 transition(s) incompatible(s) · 1 non vérifiée(s) (BPM/tonalité manquant)"
    )

    rules = SmartRules(
        category="Tek%%PsyTrance", bpm_min=170, bpm_max=180, camelot_key="8A", not_played_days=90, limit=50
    )
    assert rules.describe(translator("SmartPlaylistDialog")) == (
        "catégorie Tek / PsyTrance · BPM 170–180 · tonalité compatible avec 8A · non joué depuis 90 jours"
        " · les 50 premiers"
    )
    assert SmartRules().describe(translator("SmartPlaylistDialog")) == "tous les morceaux"


def test_duplicates_health_and_smart_playlist_windows_show_french(french):
    from PySide6.QtCore import Qt

    from djmidi.gui.duplicates_dialog import DuplicatesDialog, format_size
    from djmidi.gui.health_report_dialog import HealthReportDialog
    from djmidi.gui.music_library_view import SmartPlaylistDialog
    from djmidi.library.duplicates import TIER_EXACT, DuplicateGroup
    from djmidi.library.health import (
        DETAIL_ZERO_BYTES,
        ISSUE_EMPTY_TITLE,
        ISSUE_ZERO_LENGTH,
        HealthIssue,
        HealthReport,
    )
    from djmidi.library.smart_playlist import SORT_BPM, SmartRules

    duplicates = DuplicatesDialog([DuplicateGroup(TIER_EXACT, "abc", ("/x/a.mp3", "/x/b.mp3"), 10)])
    report = HealthReport(
        2, (HealthIssue("/x/a.mp3", ISSUE_ZERO_LENGTH, DETAIL_ZERO_BYTES), HealthIssue("/x/b.mp3", ISSUE_EMPTY_TITLE))
    )
    health = HealthReportDialog(report)
    smart = SmartPlaylistDialog("Tek", SmartRules(sort=SORT_BPM), has_history=False)
    try:
        assert duplicates.windowTitle() == "Morceaux en double"
        assert duplicates.tree.headerItem().text(0) == "Morceau / fichier"
        assert duplicates.tree.topLevelItem(0).text(0) == "Copies exactes (fichiers identiques) — 1 groupe(s)"
        assert duplicates.trash_button.text() == "Mettre les cochés à la corbeille…"
        # The tier title spans every column instead of being cut at the first.
        assert duplicates.tree.topLevelItem(0).isFirstColumnSpanned()
        assert format_size(2048) == "2.0 Ko"

        assert health.windowTitle() == "Bilan de santé de la bibliothèque"
        assert health.model.headerData(0, Qt.Orientation.Horizontal) == "Problème"
        shown = {health.model.index(row, 2).data(): row for row in range(health.model.rowCount())}
        assert health.model.index(shown["/x/a.mp3"], 0).data() == "Longueur nulle"
        assert health.model.index(shown["/x/a.mp3"], 1).data() == "0 octet"
        assert health.kind_checkboxes[ISSUE_EMPTY_TITLE].text() == "Titre vide (1)"
        # The free-text filter matches what the window shows, in French.
        health.filter_edit.setText("titre vide")
        assert [issue.path for issue in health.visible_issues()] == ["/x/b.mp3"]
        assert health.count_label.text() == "1 problème(s) affiché(s) sur 2"

        # The sort combo is read by item data, not by its translated label.
        assert smart.sort_combo.currentText() == "BPM (le plus lent d'abord)"
        assert smart.rules().sort == SORT_BPM
    finally:
        for window in (duplicates, health, smart):
            window.close()
            window.deleteLater()


# --- Mapping tabs, Controller Images, Controller Setup, Dashboard (issue #318) --

_SAMPLE_MAPPING = _ROOT / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _conflicting_rows():
    from djmidi.catalog._registry import ControlInfo

    return [
        ControlInfo("Pad", "PAD", "PAD 1", "NOTE", ("1",), "0"),
        ControlInfo("Pad", "PAD", "PAD 2", "NOTE", ("1",), "0"),
    ]


def test_qt_free_mapping_helpers_stay_english_and_are_scanned():
    from djmidi.catalog.codegen import find_trigger_conflicts
    from djmidi.function_search import index_functions
    from djmidi.parser import parse_file

    assert find_trigger_conflicts(_conflicting_rows())[0].startswith(
        "Trigger (channel=1, type=NOTE, data1=0) is claimed by 2"
    )
    results = index_functions(parse_file(_SAMPLE_MAPPING))
    assert any(result.location().startswith("Deck ") for result in results)
    sources = {path.name for path in _script_sources()}
    assert {
        "layout_view.py",
        "layer_toggles.py",
        "live_send.py",
        "tree_model.py",
        "deck_tree.py",
        "controller_tree.py",
        "edit_panel.py",
        "midi_learn.py",
        "function_search_view.py",
        "function_search.py",
        "controller_image_view.py",
        "controller_setup.py",
        "controller_submission_dialog.py",
        "codegen.py",
        "introduction_view.py",
    } <= sources


def test_mapping_tabs_and_controller_views_show_french(french):
    from PySide6.QtGui import QUndoStack

    from djmidi.catalog.codegen import find_trigger_conflicts
    from djmidi.function_search import index_functions
    from djmidi.gui.controller_image_view import ControllerImageView
    from djmidi.gui.controller_setup import ControllerSetupView
    from djmidi.gui.controller_submission_dialog import ControllerSubmissionDialog
    from djmidi.gui.deck_tree import build_deck_columns
    from djmidi.gui.edit_panel import EditPanel
    from djmidi.gui.function_search_view import FunctionSearchView, result_lines
    from djmidi.gui.introduction_view import IntroductionView
    from djmidi.gui.layout_view import ControllerLayoutView
    from djmidi.gui.translation import translator
    from djmidi.gui.tree_model import build_channel_columns
    from djmidi.parser import parse_file

    config = parse_file(_SAMPLE_MAPPING)
    layout = ControllerLayoutView(show_deck_filter=True)
    images = ControllerImageView()
    setup = ControllerSetupView()
    submission = ControllerSubmissionDialog()
    panel = EditPanel(QUndoStack(), lambda _node: None)
    search = FunctionSearchView()
    dashboard = IntroductionView()
    try:
        # By Channel / By Deck trees and the layout views.
        _channel, channel_model, _items = build_channel_columns(config)[0]
        assert channel_model.horizontalHeaderItem(0).text().startswith("Canal ")
        _deck, deck_model = build_deck_columns(config)[0]
        assert deck_model.horizontalHeaderItem(0).text() == "Platine 0"
        layout.set_usage({("DDJ-XP2", "PAD", "Pad 1"): {"0": {"codfather_st"}, "2": {"play"}}})
        combo = layout._deck_combo
        assert [combo.itemText(i) for i in range(combo.count())] == ["Toutes les platines", "Platine 0", "Platine 2"]
        # The deck filter goes by item data, not by the translated label.
        combo.setCurrentIndex(2)
        assert layout._selected_deck_filter() == "2"
        assert layout._layers.layout_box.text() == "Disposition"
        assert layout._live_send._toggle_button.text() == "Envoi live : inactif"

        # Edit / validation column.
        assert panel._prompt_label.text() == "Sélectionnez un élément de l'arbre pour le modifier."
        search.set_config(config)
        assert search.summary.text().endswith("fonctions dans ce mapping.")
        assert any("Platine " in result_lines(result)[0] for result in index_functions(config))

        # Controller Images.
        assert images._documentation_button.text() == "Ouvrir la documentation"

        # Controller Setup: table, status, submission dialog and the Qt-free conflict text.
        headers = [setup._table.horizontalHeaderItem(i).text() for i in range(setup._table.columnCount())]
        assert headers[:2] == ["Section", "Nom"]
        assert setup._learn_status.text() == "Arrêté"
        assert find_trigger_conflicts(_conflicting_rows(), translator("ControllerSetupView"))[0].startswith(
            "Le déclencheur (canal=1, type=NOTE, data1=0) est revendiqué par 2"
        )
        assert submission.windowTitle() == "Proposer le contrôleur au catalogue communautaire"

        # Dashboard cards.
        assert dashboard._loaded_file_label.text() == "Fichier chargé : aucun"
        assert dashboard._files_buttons["open"].text() == "Ouvrir un mapping…"
        assert dashboard._known_count_label.text().endswith("contrôleur(s) enregistré(s)")
    finally:
        for widget in (layout, images, setup, submission, panel, search, dashboard):
            widget.close()
            widget.deleteLater()
# --- Tool windows (issue #317) -------------------------------------------------


def test_tool_window_sources_are_scanned():
    sources = {path.name for path in _script_sources()}
    assert {
        "live_monitor.py",
        "midi_routing_view.py",
        "midi_route_transform_dialog.py",
        "metronome_view.py",
        "controller_emulator.py",
        "pad_colour_panel.py",
    } <= sources


def test_tool_windows_show_french(french):
    from PySide6.QtWidgets import QGroupBox, QPushButton

    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.gui.live_monitor import LiveMonitorView
    from djmidi.gui.metronome_view import MetronomeView
    from djmidi.gui.midi_route_transform_dialog import MidiRouteTransformDialog
    from djmidi.gui.midi_routing_view import MidiRoutingView

    monitor = LiveMonitorView()
    routing = MidiRoutingView()
    metronome = MetronomeView()
    transform = MidiRouteTransformDialog(None)
    emulator = ControllerEmulatorView(config_provider=lambda: None)
    try:
        assert monitor._start_button.text() == "Démarrer la surveillance"
        assert monitor._log.horizontalHeaderItem(0).text() == "Heure"
        assert monitor._conflict_label.text() == "Conflits : aucun dans le mapping chargé"
        assert monitor._sync_button.text() == "Synchroniser les contrôleurs"

        assert routing._routing_button.text() == "Démarrer le routage"
        assert routing._routes_table.horizontalHeaderItem(3).text() == "État"
        assert routing.take_clock_panel().title() == "Horloge MIDI"
        assert routing._clock_status.text() == "Relais de l'horloge désactivé"
        routing.set_routing_enabled(False)
        assert routing._routing_button.toolTip() == "Activez d'abord le routage MIDI dans les Préférences"

        assert "Source de la session" in [box.title() for box in metronome.findChildren(QGroupBox)]
        assert "Arrêter la boucle" in [button.text() for button in metronome.findChildren(QPushButton)]
        assert metronome._status.text() == "Prêt."
        assert metronome._session_summary.text().startswith("Session de configuration actuelle")

        assert transform.windowTitle() == "Modifier la transformation de la route"
        assert transform._channel.itemText(0) == "(inchangé)"
        # The channel is read from item data, not from the translated label.
        assert transform._channel.currentData() is None

        assert emulator._status_label.text() == "Cliquez sur une commande pour voir à quoi elle correspond."
        assert emulator._pad_colours._paint_button.text() == "Peindre"
    finally:
        routing.shutdown()
        monitor.shutdown()
        metronome.shutdown()
        for window in (monitor, routing, metronome, transform, emulator):
            window.close()
            window.deleteLater()


def test_tool_dock_title_bars_and_window_menu_show_french(french):
    from PySide6.QtWidgets import QLabel, QPushButton

    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        titles = {key: dock.windowTitle() for key, dock in window._tool_docks.items()}
        assert titles == {
            "monitor": "Live Monitor",
            "routing": "Routage MIDI",
            "clock": "Horloge MIDI",
            "metronome": "Métronome",
        }
        bar = window._tool_docks["routing"].titleBarWidget()
        assert bar.findChild(QLabel).text() == "Routage MIDI"
        buttons = {button.text(): button for button in bar.findChildren(QPushButton)}
        assert "Détacher" in buttons
        menu = buttons["☰"].menu()
        assert [action.text() for action in menu.actions() if action.text()] == [
            "Réduire à la barre de titre",
            "Agrandir",
            "Ancrer à gauche",
            "Ancrer à droite",
            "Ancrer en haut",
            "Ancrer en bas",
        ]
        emulator = window._create_emulator_instance()
        assert emulator.windowTitle() == "Émulateur de contrôleur"
        assert emulator.titleBarWidget().findChild(QLabel).text() == "Émulateur de contrôleur"
    finally:
        window.close()
        window.deleteLater()
