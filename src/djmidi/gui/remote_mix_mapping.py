"""My mapping: every console control your controller drives, in one list, each one
with the control that drives it and a button to forget it (the knobs and buttons
taught in MIDI mode have no Learn button of their own)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.empty_state import EmptyState
from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.remote_mix import controls


class MappingDialog(QDialog):
    def __init__(
        self,
        mapping: controls.MixerControls,
        name_of: Callable[[str], str],
        on_forget: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("My mapping"))
        fit_to_screen(self, 560, 420)
        self._mapping = mapping
        self._name_of = name_of
        self._on_forget = on_forget
        hint = QLabel(
            self.tr("What your controller drives on the console. Teach more in MIDI mode; forget one here.")
        )
        hint.setWordWrap(True)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([self.tr("Console"), self.tr("Your controller"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.empty = EmptyState(
            self.table, "🎛", self.tr("Nothing assigned yet"),
            self.tr("Press MIDI on the console, click a knob or button, then move or press your controller."),
            is_empty=lambda: self.table.rowCount() == 0,
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)
        self.refresh()
        keep_wrapped_text_visible(self)

    def refresh(self) -> None:
        rows = [(target, self._mapping.bindings[target]) for target in controls.TARGETS if target in self._mapping.bindings]
        self.table.setRowCount(len(rows))
        for row, (target, trigger) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(self._name_of(target)))
            self.table.setItem(row, 1, QTableWidgetItem(trigger.label()))
            forget = QPushButton(self.tr("Forget"))
            forget.setToolTip(self.tr("Your controller stops driving this console control"))
            forget.clicked.connect(lambda _checked=False, t=target: self.forget(t))
            self.table.setCellWidget(row, 2, forget)
        self.empty.refresh()

    def forget(self, target: str) -> None:
        self._on_forget(target)
        self.refresh()


__all__ = ["MappingDialog"]
