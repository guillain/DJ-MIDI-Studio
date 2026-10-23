"""Contextual "?" help: every tab and tool window carries at least one, each
one opens its own text, and every guide it links to is really bundled."""

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from djmidi.gui import help_button as help_module
from djmidi.gui import help_texts
from djmidi.gui.help_button import guide_path, help_button

ENTRIES = {name: value for name, value in vars(help_texts).items() if name.isupper() and isinstance(value, tuple)}


def _help_buttons(widget: QWidget) -> list[QPushButton]:
    return [b for b in widget.findChildren(QPushButton) if b.property("help") and b.isVisible()]


def test_every_help_entry_has_a_title_a_text_and_a_bundled_guide():
    assert len(ENTRIES) >= 15
    for name, (title, text, doc) in ENTRIES.items():
        assert title and len(text) > 40, name
        assert doc is None or guide_path(doc).exists(), (name, doc)


def test_clicking_a_help_button_opens_its_own_text(monkeypatch):
    shown = []
    monkeypatch.setattr(help_module, "show_help", lambda *args: shown.append(args))
    parent = QWidget()
    button = help_button(parent, *help_texts.LIVE_MONITOR)
    assert button.text() == "?" and button.toolTip() == "Help: Live Monitor"
    button.click()
    assert shown == [(parent, *help_texts.LIVE_MONITOR)]


def test_every_tab_and_tool_window_has_a_help_button():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    window.resize(1600, 1000)
    window.show()
    QApplication.processEvents()
    try:
        for key, index in window._tab_indexes.items():
            window.left_tabs.setCurrentIndex(index)
            QApplication.processEvents()
            assert _help_buttons(window.left_tabs.widget(index)), key
        window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
        QApplication.processEvents()
        assert _help_buttons(window.edit_panel), "edit panel"
        for key, dock in window._tool_docks.items():
            window._show_tool_dock(key)
            QApplication.processEvents()
            assert _help_buttons(dock), key
            dock.hide()
        emulator = window._create_emulator_instance()
        QApplication.processEvents()
        assert _help_buttons(emulator), "emulator"
    finally:
        window.close()


# --- French (issue #320) -------------------------------------------------------


def _french_catalogue() -> dict[tuple[str, str], tuple[str | None, str]]:
    import xml.etree.ElementTree as ET

    from djmidi import i18n

    root = ET.parse(i18n.translations_dir() / "djmidi_fr.ts").getroot()
    messages = {}
    for context in root.iter("context"):
        name = context.find("name").text
        for message in context.iter("message"):
            translation = message.find("translation")
            messages[(name, message.find("source").text)] = (translation.get("type"), translation.text or "")
    return messages


def test_every_help_entry_has_a_finished_french_translation():
    catalogue = _french_catalogue()
    for name, (title, text, _doc) in ENTRIES.items():
        for source in (title, text):
            assert (help_texts.CONTEXT, source) in catalogue, (name, source[:60])
            state, translation = catalogue[(help_texts.CONTEXT, source)]
            assert state is None and translation.strip(), (name, source[:60])
        # A body is never left in English, and keeps its markup.
        french = catalogue[(help_texts.CONTEXT, text)][1]
        assert french != text, name
        for tag in ("<b>", "<ul>", "<li>", "<br>", "<tt>", "<i>", "<ol>"):
            assert french.count(tag) == text.count(tag), (name, tag)


def test_help_popup_and_tooltip_show_french_with_the_french_catalogue(monkeypatch):
    from PySide6.QtCore import QCoreApplication, QTranslator
    from PySide6.QtWidgets import QMessageBox

    from djmidi import i18n

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda box: shown.append(box) or 0)
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    QCoreApplication.instance().installTranslator(translator)
    try:
        parent = QWidget()
        button = help_button(parent, *help_texts.EDIT_PANEL)
        assert button.toolTip() == "Aide : Modifier et valider"
        button.click()
        box = shown[-1]
        assert box.text() == "<b>Modifier et valider</b>"
        assert box.informativeText().startswith("Modifie l'élément sélectionné")
        assert "<b>Édition → Annuler</b>" in box.informativeText()
        assert "Ouvrir le guide complet" in [b.text() for b in box.buttons()]
        # Controller Setup's own panels go through the same catalogue.
        help_module.show_help(parent, *help_texts.CONTROLLER_SETUP_CAPTURE)
        assert shown[-1].text() == "<b>MIDI input (apprendre depuis le contrôleur)</b>"
        # A text outside the catalogue shows as written.
        help_module.show_help(parent, "Untranslated", "Some text nobody translated, kept as written.")
        assert shown[-1].informativeText() == "Some text nobody translated, kept as written."
    finally:
        QCoreApplication.instance().removeTranslator(translator)
