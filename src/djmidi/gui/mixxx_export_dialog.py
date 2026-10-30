"""File → Export → Mixxx Mapping from Profile…: pick a Mixxx function for
each button of a controller profile and save a ``.midi.xml``.

The table lists every button/pad trigger of the chosen profile (SHIFT
layers left out); the Function and Deck columns are edited in place. Rows
start with :func:`mixxx_export.suggest_function`'s guess, which the user
reviews; only rows with a function are written."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.mixxx_export import (
    FUNCTIONS,
    MAX_DECKS,
    Assignment,
    ProfileButton,
    build_mixxx_mapping,
    function_label,
    profile_buttons,
    suggest_function,
)

SECTION, CONTROL, MIDI, DECK, FUNCTION = range(5)
_translate = translator("MixxxExport")
_KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class _FunctionDelegate(QStyledItemDelegate):
    """A combo of the Mixxx functions (plus "none") as the cell editor."""

    def __init__(self, none_label: str, parent=None) -> None:
        super().__init__(parent)
        self._none_label = none_label

    def createEditor(self, parent, _option, _index):
        combo = QComboBox(parent)
        combo.addItem(self._none_label, None)
        for function in FUNCTIONS:
            combo.addItem(function_label(function, _translate), function.key)
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        editor.setCurrentIndex(max(editor.findData(index.data(_KEY_ROLE)), 0))

    def setModelData(self, editor: QComboBox, model, index: QModelIndex) -> None:
        key = editor.currentData()
        model.setData(index, key, _KEY_ROLE)
        model.setData(index, editor.currentText() if key else "", Qt.ItemDataRole.DisplayRole)


class _DeckDelegate(QStyledItemDelegate):
    def createEditor(self, parent, _option, _index):
        spin = QSpinBox(parent)
        spin.setRange(1, MAX_DECKS)
        return spin

    def setEditorData(self, editor: QSpinBox, index: QModelIndex) -> None:
        editor.setValue(int(index.data(Qt.ItemDataRole.DisplayRole) or 1))

    def setModelData(self, editor: QSpinBox, model, index: QModelIndex) -> None:
        model.setData(index, str(editor.value()), Qt.ItemDataRole.DisplayRole)


class MixxxExportDialog(QDialog):
    def __init__(
        self,
        controllers: Sequence[str],
        initial: str | None = None,
        parent: QWidget | None = None,
        save_dir: str | Path = "",
        choose_path: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export a Mixxx Mapping"))
        self._save_dir = Path(save_dir) if save_dir else Path.home()
        self._choose_path = choose_path or self._ask_path
        self.buttons: list[ProfileButton] = []

        intro = QLabel(
            self.tr(
                "Pick a Mixxx function for the buttons and pads you want; the guesses from their names "
                "are only suggestions. Rows without a function are left out. Knobs, faders and jog "
                "wheels aren't in profiles, so map those in Mixxx."
            )
        )
        intro.setWordWrap(True)
        self.controller_combo = QComboBox()
        for name in controllers:
            self.controller_combo.addItem(name)
        if initial in controllers:
            self.controller_combo.setCurrentText(initial)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("Filter controls…"))
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.mapped_only = QCheckBox(self.tr("Only rows with a function"))
        self.mapped_only.toggled.connect(self._apply_filter)
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Controller:")))
        top.addWidget(self.controller_combo, 1)
        top.addWidget(self.filter_edit, 1)
        top.addWidget(self.mapped_only)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Section"), self.tr("Control"), self.tr("MIDI"), self.tr("Deck"), self.tr("Mixxx function")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        header = self.table.horizontalHeader()
        for column in (SECTION, MIDI, DECK):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(CONTROL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(FUNCTION, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(FUNCTION, _FunctionDelegate(self.tr("— none —"), self.table))
        self.table.setItemDelegateForColumn(DECK, _DeckDelegate(self.table))
        self.table.itemChanged.connect(lambda _item: self._update_count())
        usable_minimum(self.table, 480, 160)

        self.note_off_box = QCheckBox(self.tr("Also bind Note Off (for a controller that releases buttons with Note Off)"))
        self.count_label = QLabel("")
        self.save_button = QPushButton(self.tr("Save Mixxx mapping…"))
        self.save_button.clicked.connect(self.save)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *help_texts.MIXXX_EXPORT))
        bottom.addWidget(self.count_label, 1)
        bottom.addWidget(self.save_button)
        bottom.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.note_off_box)
        layout.addLayout(bottom)

        self.controller_combo.currentTextChanged.connect(self.load_controller)
        self.load_controller(self.controller_combo.currentText())
        fit_to_screen(self, 900, 620)
        keep_wrapped_text_visible(self)

    # --- table ---------------------------------------------------------------

    def load_controller(self, controller: str) -> None:
        self.buttons = profile_buttons(controller) if controller else []
        labels = {function.key: function_label(function, _translate) for function in FUNCTIONS}
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row, button in enumerate(self.buttons):
            self.table.insertRow(row)
            midi = self.tr("ch {channel} {kind} {number}").format(
                channel=button.channel, kind=self.tr("note") if button.kind == "NOTE" else "CC", number=button.data1
            )
            cells = [button.section, button.name, midi, str(button.deck), ""]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column not in (DECK, FUNCTION):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            key = suggest_function(button)
            if key:
                function_item = self.table.item(row, FUNCTION)
                function_item.setData(_KEY_ROLE, key)
                function_item.setText(labels[key])
        self.table.blockSignals(False)
        self._apply_filter()
        self._update_count()

    def set_function(self, row: int, key: str | None) -> None:
        item = self.table.item(row, FUNCTION)
        item.setData(_KEY_ROLE, key)
        label = next((function_label(function, _translate) for function in FUNCTIONS if function.key == key), "")
        item.setText(label if key else "")

    def assignments(self) -> list[Assignment]:
        found = []
        for row, button in enumerate(self.buttons):
            key = self.table.item(row, FUNCTION).data(_KEY_ROLE)
            if key:
                deck = int(self.table.item(row, DECK).text() or button.deck)
                found.append(Assignment(button, key, max(1, min(deck, MAX_DECKS))))
        return found

    def _apply_filter(self) -> None:
        needle = self.filter_edit.text().casefold()
        only_mapped = self.mapped_only.isChecked()
        for row, button in enumerate(self.buttons):
            mapped = bool(self.table.item(row, FUNCTION).data(_KEY_ROLE))
            text = f"{button.section} {button.name}".casefold()
            self.table.setRowHidden(row, bool(needle and needle not in text) or (only_mapped and not mapped))

    def _update_count(self) -> None:
        count = len(self.assignments())
        self.count_label.setText(self.tr("{count} control(s) get a Mixxx function.").format(count=count))
        self.save_button.setEnabled(count > 0)

    # --- saving ----------------------------------------------------------------

    def _ask_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save Mixxx mapping"), str(self._save_dir / suggested), self.tr("Mixxx mappings (*.midi.xml)")
        )
        return path

    def save(self, path: str | Path | None = None) -> Path | None:
        assignments = self.assignments()
        if not assignments:
            return None
        controller = self.controller_combo.currentText()
        if path is None:
            chosen = self._choose_path(f"{controller}.midi.xml")
            if not chosen:
                return None
            path = chosen
        target = Path(path)
        if not target.name.endswith(".midi.xml"):
            target = target.with_name(target.name.removesuffix(".xml") + ".midi.xml")
        text = build_mixxx_mapping(controller, assignments, note_off=self.note_off_box.isChecked())
        try:
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, self.tr("Save Mixxx mapping"), str(exc))
            return None
        self.count_label.setText(
            self.tr("Saved {path}: copy it to Mixxx's controllers folder, then pick it in Preferences → Controllers.").format(
                path=target.name
            )
        )
        return target


__all__ = ["MixxxExportDialog"]
