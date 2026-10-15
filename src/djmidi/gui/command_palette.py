"""The command palette popup (issue #222): a search field over a
`djmidi.command_palette.PaletteIndex` and the list of what it found.

Keyboard-only by design: the field keeps the focus, Up/Down/PageUp/PageDown
move the highlighted row, Enter runs it, Escape closes. The dialog only
*chooses* an entry (`chosen_entry()` after `exec()` / the `entryChosen`
signal); MainWindow runs it, since only it knows what a QAction, a tab, a
function or a track payload means. `menu_entries` turns a menu bar into
action entries ("File › Export › Cheat Sheet (PDF)")."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMenuBar,
    QVBoxLayout,
    QWidget,
)

from djmidi.command_palette import (
    KIND_ACTION,
    KIND_LABELS,
    PaletteEntry,
    PaletteIndex,
    clean_menu_text,
)
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.window_size import fit_to_screen, usable_minimum

ENTRY_ROLE = Qt.ItemDataRole.UserRole + 7
_PATH_SEPARATOR = " › "


def _menu_actions(menu: QMenu, path: list[str], skip: set[QAction]) -> list[PaletteEntry]:
    entries: list[PaletteEntry] = []
    for action in menu.actions():
        if action.isSeparator() or not action.isVisible() or action in skip:
            continue
        submenu = action.menu()
        label = clean_menu_text(action.text())
        if submenu is not None:
            entries.extend(_menu_actions(submenu, [*path, label], skip))
            continue
        # A disabled action (Save with nothing open) can't run: leave it out
        # rather than list something Enter would silently ignore.
        if not label or not action.isEnabled():
            continue
        title = label
        if action.isCheckable():
            title += " (on)" if action.isChecked() else " (off)"
        shortcut = action.shortcut().toString(action.shortcut().SequenceFormat.NativeText)
        detail = _PATH_SEPARATOR.join(path)
        if shortcut:
            detail += f"   {shortcut}"
        entries.append(
            PaletteEntry(
                KIND_ACTION,
                title,
                detail=detail,
                keywords=" ".join([*path, action.toolTip() if action.toolTip() != action.text() else ""]),
                payload=action,
            )
        )
    return entries


def menu_entries(menu_bar: QMenuBar, skip: set[QAction] | None = None) -> list[PaletteEntry]:
    """Every enabled leaf action of `menu_bar`, in menu order."""
    entries: list[PaletteEntry] = []
    for action in menu_bar.actions():
        submenu = action.menu()
        if submenu is not None and action.isVisible():
            entries.extend(_menu_actions(submenu, [clean_menu_text(action.text())], skip or set()))
    return entries


class CommandPaletteDialog(QDialog):
    entryChosen = Signal(object)

    def __init__(self, index: PaletteIndex, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        fit_to_screen(self, 620, 420)
        self._index = index
        self._chosen: PaletteEntry | None = None

        layout = QVBoxLayout(self)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Type an action, a tab, a function or a track…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._refresh)
        self.search_field.installEventFilter(self)
        row = QHBoxLayout()
        row.addWidget(self.search_field, 1)
        row.addWidget(help_button(self, *help_texts.COMMAND_PALETTE))
        layout.addLayout(row)

        self.results = QListWidget()
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.itemActivated.connect(self._on_item_activated)
        self.results.itemClicked.connect(self._on_item_activated)
        usable_minimum(self.results, 360, 140)
        layout.addWidget(self.results, 1)

        self.hint = QLabel("↑↓ to move · Enter to run · Esc to close")
        self.hint.setEnabled(False)
        layout.addWidget(self.hint)
        self._refresh()

    # --- public API used by MainWindow and tests -------------------------

    def set_query(self, text: str) -> None:
        self.search_field.setText(text)

    def result_count(self) -> int:
        return self.results.count()

    def entry_at(self, row: int) -> PaletteEntry:
        return self.results.item(row).data(ENTRY_ROLE)

    def current_entry(self) -> PaletteEntry | None:
        item = self.results.currentItem()
        return item.data(ENTRY_ROLE) if item is not None else None

    def chosen_entry(self) -> PaletteEntry | None:
        return self._chosen

    def choose_current(self) -> None:
        entry = self.current_entry()
        if entry is None:
            return
        self._chosen = entry
        self.accept()
        self.entryChosen.emit(entry)

    # --- internals -----------------------------------------------------------

    def _refresh(self) -> None:
        self.results.clear()
        for entry in self._index.search(self.search_field.text()):
            kind = KIND_LABELS.get(entry.kind, entry.kind)
            text = f"{entry.title}\n{kind}" + (f" · {entry.detail}" if entry.detail else "")
            item = QListWidgetItem(text)
            item.setData(ENTRY_ROLE, entry)
            item.setToolTip(entry.detail or entry.title)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
            self.hint.setText("↑↓ to move · Enter to run · Esc to close")
        else:
            self.hint.setText("Nothing matches." if self.search_field.text().strip() else "Nothing to list yet.")

    def _move(self, delta: int) -> None:
        count = self.results.count()
        if not count:
            return
        row = min(max(self.results.currentRow() + delta, 0), count - 1)
        self.results.setCurrentRow(row)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.search_field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            page = max(1, self.results.height() // 40)
            moves = {
                Qt.Key.Key_Down: 1,
                Qt.Key.Key_Up: -1,
                Qt.Key.Key_PageDown: page,
                Qt.Key.Key_PageUp: -page,
            }
            if key in moves:
                self._move(moves[key])
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose_current()
                return True
        return super().eventFilter(watched, event)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        self.results.setCurrentItem(item)
        self.choose_current()


__all__ = ["ENTRY_ROLE", "CommandPaletteDialog", "menu_entries"]
