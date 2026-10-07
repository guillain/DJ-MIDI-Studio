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
