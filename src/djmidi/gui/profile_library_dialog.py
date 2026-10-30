"""File → Controller Profile → Install from Library…: pick ready-made
controller profiles (``djmidi.catalog.library``) and install them.

Thin by design: listing and installing live in the Qt-free library module;
the dialog filters the list, shows what is already installed, and emits
:attr:`ProfileLibraryDialog.installed` with each newly installed name so the
main window refreshes its controller lists (and :attr:`uninstalled` for
each one removed).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from djmidi.catalog.library import LibraryProfile, install_library_profile
from djmidi.catalog.profile import uninstall_user_profile
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import PROFILE_LIBRARY
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.i18n import QT_TRANSLATE_NOOP

_COLUMNS = (
    QT_TRANSLATE_NOOP("ProfileLibraryDialog", "Controller"),
    QT_TRANSLATE_NOOP("ProfileLibraryDialog", "Vendor"),
    QT_TRANSLATE_NOOP("ProfileLibraryDialog", "Source"),
    QT_TRANSLATE_NOOP("ProfileLibraryDialog", "Controls"),
    QT_TRANSLATE_NOOP("ProfileLibraryDialog", "Status"),
)


class ProfileLibraryDialog(QDialog):
    installed = Signal(str)
    uninstalled = Signal(str)

    def __init__(
        self,
        profiles: Sequence[LibraryProfile],
        controllers_dir: str | Path,
        parent=None,
        install: Callable[[LibraryProfile, str | Path], object] = install_library_profile,
        uninstall: Callable[[str, str | Path], object] = uninstall_user_profile,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Controller Profile Library"))
        self._profiles = list(profiles)
        self._controllers_dir = controllers_dir
        self._install = install
        self._uninstall = uninstall

        intro = QLabel(
            self.tr(
                "Ready-made profiles built from existing MIDI mappings: Pioneer DJ / AlphaTheta devices from "
                "rekordbox's (buttons and pads, named as rekordbox names them), many other brands from the "
                "Mixxx project's (buttons, named after the Mixxx function they drive). Install the ones you "
                "use; they then work like a profile made in Controller Setup."
            )
        )
        intro.setWordWrap(True)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("Filter by name, e.g. DDJ-400"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([self.tr(column) for column in _COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self.install_selected())
        usable_minimum(self.table, 360, 200)

        self.install_button = QPushButton(self.tr("Install"))
        self.install_button.clicked.connect(self.install_selected)
        self.uninstall_button = QPushButton(self.tr("Uninstall"))
        self.uninstall_button.setToolTip(self.tr("Remove the selected installed profiles from your Controllers folder"))
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *PROFILE_LIBRARY))
        bottom.addWidget(self.install_button)
        bottom.addWidget(self.uninstall_button)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

        self._fill()
        fit_to_screen(self, 640, 560)
        keep_wrapped_text_visible(self)

    def _status_text(self, profile: LibraryProfile) -> str:
        if profile.is_built_in:
            return self.tr("Built-in")
        if profile.is_installed:
            return self.tr("Installed")
        return ""

    def _fill(self) -> None:
        self.table.setRowCount(0)
        for profile in self._profiles:
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = {"rekordbox": "rekordbox", "mixxx": "Mixxx"}.get(profile.source, profile.source)
            values = (profile.name, profile.vendor, source, str(profile.entries), self._status_text(profile))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column == 0 and profile.port_names:
                    item.setToolTip(self.tr("MIDI ports: {ports}").format(ports=", ".join(profile.port_names)))
                self.table.setItem(row, column, item)
        self._apply_filter(self.filter_edit.text())

    def _apply_filter(self, text: str) -> None:
        needle = "".join(char for char in text.casefold() if char.isalnum())
        for row, profile in enumerate(self._profiles):
            names = (profile.name, *profile.port_names)
            haystack = " ".join("".join(char for char in name.casefold() if char.isalnum()) for name in names)
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)
        self._update_buttons()

    def _selected_profiles(self) -> list[LibraryProfile]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self._profiles[row] for row in rows if not self.table.isRowHidden(row)]

    def _update_buttons(self) -> None:
        selected = self._selected_profiles()
        self.install_button.setEnabled(any(not p.is_built_in for p in selected))
        self.uninstall_button.setEnabled(any(p.is_installed for p in selected))

    def select_profile(self, name: str) -> None:
        for row, profile in enumerate(self._profiles):
            if profile.name == name:
                self.table.selectRow(row)
                return

    def install_selected(self) -> list[str]:
        """Installs the selected profiles; returns the names installed."""
        done: list[str] = []
        errors: list[str] = []
        for profile in self._selected_profiles():
            if profile.is_built_in:
                continue
            try:
                self._install(profile, self._controllers_dir)
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"{profile.name}: {exc}")
                continue
            done.append(profile.name)
            self.installed.emit(profile.name)
        self._fill()
        if errors:
            self.status.setText(errors[0])
        elif done:
            self.status.setText(self.tr("Installed: {names}").format(names=", ".join(done)))
        return done

    def uninstall_selected(self) -> list[str]:
        """Uninstalls the selected installed profiles; returns their names."""
        done: list[str] = []
        errors: list[str] = []
        for profile in self._selected_profiles():
            if not profile.is_installed:
                continue
            try:
                self._uninstall(profile.name, self._controllers_dir)
            except (OSError, ValueError) as exc:
                errors.append(f"{profile.name}: {exc}")
                continue
            done.append(profile.name)
            self.uninstalled.emit(profile.name)
        self._fill()
        if errors:
            self.status.setText(errors[0])
        elif done:
            self.status.setText(self.tr("Uninstalled: {names}").format(names=", ".join(done)))
        return done
