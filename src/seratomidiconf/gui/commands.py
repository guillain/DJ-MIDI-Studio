from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from seratomidiconf.model import Alias, Translation

OnApplied = Callable[[object], None]


class SetAttrCommand(QUndoCommand):
    """Undoable change of a single attribute on a model object (Control, UserIO,
    MappingElement, Translation or Alias)."""

    def __init__(
        self,
        target: object,
        attr: str,
        old_value: str | None,
        new_value: str | None,
        relabel_node: object,
        on_applied: OnApplied,
        label: str | None = None,
    ) -> None:
        super().__init__(label or f"Edit {attr}")
        self._target = target
        self._attr = attr
        self._old = old_value
        self._new = new_value
        self._relabel_node = relabel_node
        self._on_applied = on_applied

    def redo(self) -> None:
        setattr(self._target, self._attr, self._new)
        self._on_applied(self._relabel_node)

    def undo(self) -> None:
        setattr(self._target, self._attr, self._old)
        self._on_applied(self._relabel_node)


class AddAliasCommand(QUndoCommand):
    def __init__(self, translation: Translation, alias: Alias, relabel_node: object, on_applied: OnApplied) -> None:
        super().__init__("Add alias")
        self._translation = translation
        self._alias = alias
        self._relabel_node = relabel_node
        self._on_applied = on_applied

    def redo(self) -> None:
        self._translation.aliases.append(self._alias)
        self._on_applied(self._relabel_node)

    def undo(self) -> None:
        self._translation.aliases.remove(self._alias)
        self._on_applied(self._relabel_node)


class RemoveAliasCommand(QUndoCommand):
    def __init__(self, translation: Translation, index: int, relabel_node: object, on_applied: OnApplied) -> None:
        super().__init__("Remove alias")
        self._translation = translation
        self._index = index
        self._alias = translation.aliases[index]
        self._relabel_node = relabel_node
        self._on_applied = on_applied

    def redo(self) -> None:
        del self._translation.aliases[self._index]
        self._on_applied(self._relabel_node)

    def undo(self) -> None:
        self._translation.aliases.insert(self._index, self._alias)
        self._on_applied(self._relabel_node)
