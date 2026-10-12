"""The "Find function" panel (issue #185): a search field over the loaded
mapping's functions and the list of what it found. A thin wrapper over the
Qt-free `djmidi.function_search`; MainWindow owns what selecting a result
does (layout highlight + navigation), this widget only emits it.

It sits at the top of the narrow editing column, so each result is a
word-wrapped two-line row (function · deck/slot, then trigger → physical
control) rather than a four-column table, which a ~200 px column would
truncate to nothing (checked on an offscreen MainWindow grab at 1100x700)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.function_search import (
    FunctionResult,
    index_functions,
    physical_names,
    search_functions,
)
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.model import MidiConfig

RESULT_ROLE = Qt.ItemDataRole.UserRole + 1


def result_lines(result: FunctionResult) -> tuple[str, str, str]:
    """(first line, second line, full tooltip) for one result row. The
    second line names only the first physical control (a merged config can
    resolve one trigger on several controllers); the tooltip lists them all."""
    event = "" if result.event == "click" else f" [{result.event}]"
    first = f"{result.label}{event} · {result.location()}"
    triggers = ", ".join(trigger.describe() for trigger in result.triggers)
    # Catalog order, not alphabetical: it lists controllers as registered.
    physical = list(dict.fromkeys(name for trigger in result.triggers for name in physical_names(trigger)))
    shown = physical[0] if physical else "unknown physical control"
    if len(physical) > 1:
        shown += f" (+{len(physical) - 1})"
    second = f"{triggers} → {shown}"
    tooltip = "\n".join([f"{result.tag} ({result.event}) · {result.location()}", triggers, *physical])
    return first, second, tooltip


class FunctionSearchView(QWidget):
    """Emits `resultSelected(FunctionResult)` when a result row is picked."""

    resultSelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index: list[FunctionResult] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Find function: loop roll, deck 2…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setToolTip(
            "Which control triggers this function? Matches function names, deck and slot."
        )
        self.search_field.textChanged.connect(self._refresh)
        row.addWidget(self.search_field, 1)
        row.addWidget(help_button(self, *help_texts.FUNCTION_SEARCH))
        layout.addLayout(row)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.setSpacing(2)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setMinimumHeight(90)
        self.results.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.results, 1)
        self._refresh()

    def set_config(self, config: MidiConfig | None) -> None:
        self._index = index_functions(config) if config is not None else []
        self._refresh()

    def set_query(self, text: str) -> None:
        self.search_field.setText(text)

    def result_count(self) -> int:
        return self.results.count()

    def result_at(self, row: int) -> FunctionResult:
        return self.results.item(row).data(RESULT_ROLE)

    def select_row(self, row: int) -> None:
        self.results.setCurrentRow(row)

    def _refresh(self) -> None:
        self.results.clear()
        query = self.search_field.text()
        if not self._index:
            self.summary.setText("Open a mapping to search its functions.")
            self.results.setVisible(False)
            return
        matches = search_functions(self._index, query)
        # Hidden until there's something to list, so the panel stays one
        # line tall above the edit panel the rest of the time.
        self.results.setVisible(bool(matches))
        if not query.strip():
            self.summary.setText(f"{len(self._index)} functions in this mapping.")
        elif not matches:
            self.summary.setText(f"No function matches “{query.strip()}”.")
        else:
            self.summary.setText(f"{len(matches)} match(es): select one to show its controls.")
        for result in matches:
            first, second, tooltip = result_lines(result)
            item = QListWidgetItem(f"{first}\n{second}")
            item.setData(RESULT_ROLE, result)
            item.setToolTip(tooltip)
            self.results.addItem(item)

    def _on_selection_changed(self) -> None:
        items = self.results.selectedItems()
        if items:
            self.resultSelected.emit(items[0].data(RESULT_ROLE))


__all__ = ["RESULT_ROLE", "FunctionSearchView", "result_lines"]
