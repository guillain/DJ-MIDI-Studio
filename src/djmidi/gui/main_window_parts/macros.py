"""MainWindow, part: The Macros menu: building it, reserved shortcuts, toggle sides and trigger listening.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

from PySide6.QtCore import (
    QCoreApplication,
    Qt,
)
from PySide6.QtGui import (
    QAction,
    QKeySequence,
)

from djmidi import (
    midi_macros,
    user_paths,
)
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.main_window_parts._shared import (
    _macro_translate,
)


class MacrosMixin:
    def _rebuild_macro_menu(self) -> None:
        menu = self._macro_menu
        menu.clear()
        self._macro_actions = []
        for macro in self.macros:
            action = QAction(macro.name, self)
            if macro.shortcut:
                action.setShortcut(QKeySequence(macro.shortcut))
                # Floating tool docks are separate windows: keep the shortcut
                # working while one of them has the focus.
                action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            steps = len(macro.steps)
            action.setToolTip(
                QCoreApplication.translate("MainWindow", "{count} message(s) to {port}").format(
                    count=steps, port=macro.output_port or QCoreApplication.translate("MainWindow", "no port")
                )
            )
            action.triggered.connect(lambda _checked=False, name=macro.name: self._play_macro(name))
            menu.addAction(action)
            self._macro_actions.append(action)
        if not self.macros:
            empty = menu.addAction(QCoreApplication.translate("MainWindow", "No macro yet"))
            empty.setEnabled(False)
        menu.addSeparator()
        manage = menu.addAction(QCoreApplication.translate("MainWindow", "Manage Macros…"))
        manage.triggered.connect(lambda: self._on_manage_macros())
        reveal = menu.addAction(QCoreApplication.translate("MainWindow", "Show Macros Folder"))
        reveal.triggered.connect(self._on_reveal_macros)

    def _reserved_shortcuts(self) -> list[str]:
        """The shortcuts of every menu action that isn't a macro."""
        macro_actions = set(self._macro_actions)
        shortcuts: list[str] = []
        stack = [action for action in self.menuBar().actions()]
        while stack:
            action = stack.pop()
            if action.menu() is not None:
                stack.extend(action.menu().actions())
            elif action not in macro_actions and not action.shortcut().isEmpty():
                shortcuts.append(action.shortcut().toString(QKeySequence.SequenceFormat.PortableText))
        return shortcuts

    def _macro_to_play(self, macro: midi_macros.MidiMacro) -> midi_macros.MidiMacro:
        """The side of a toggle macro due now, flipping it for next time
        (issue #367); any other macro as is."""
        if not macro.is_toggle:
            return macro
        alternate = self._macro_toggles.get(macro.name, False)
        self._macro_toggles[macro.name] = not alternate
        return macro.variant(alternate)

    def _ensure_macro_triggers_listening(self) -> None:
        """A controller-triggered macro only fires while its input is open:
        start the Live Monitor when one exists, if the user lets it auto-start."""
        if self.preferences.auto_start_live_monitor and any(macro.triggers for macro in self.macros):
            self.live_monitor_view.ensure_monitoring_started()

    def _on_macro_finished(self, result: midi_macros.MacroResult) -> None:
        self.statusBar().showMessage(result.summary(_macro_translate), 8000)

    def _on_reveal_macros(self) -> None:
        folder = user_paths.macros_dir()
        folder.mkdir(parents=True, exist_ok=True)
        reveal_in_file_manager(folder)

    def _on_reveal_installed_profiles(self) -> None:
        folder = user_paths.controllers_dir()
        folder.mkdir(parents=True, exist_ok=True)
        reveal_in_file_manager(folder)
