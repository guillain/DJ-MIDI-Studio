from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from djmidi.model import Alias, Translation

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


OnGroupApplied = Callable[[], None]


class SetGroupAttrCommand(QUndoCommand):
    """Same as SetAttrCommand but applies to every member of a MappingGroup at
    once, so a group of duplicate triggers never drifts out of sync with itself."""

    def __init__(
        self,
        targets: list[object],
        attr: str,
        old_values: list[str | None],
        new_value: str | None,
        on_applied: OnGroupApplied,
        label: str | None = None,
    ) -> None:
        super().__init__(label or f"Edit {attr} ({len(targets)} linked)")
        self._targets = targets
        self._attr = attr
        self._old_values = old_values
        self._new_value = new_value
        self._on_applied = on_applied

    def redo(self) -> None:
        for target in self._targets:
            setattr(target, self._attr, self._new_value)
        self._on_applied()

    def undo(self) -> None:
        for target, old_value in zip(self._targets, self._old_values, strict=True):
            setattr(target, self._attr, old_value)
        self._on_applied()


class AddGroupAliasCommand(QUndoCommand):
    def __init__(self, translations: list[Translation], aliases: list[Alias], on_applied: OnGroupApplied) -> None:
        super().__init__(f"Add alias ({len(translations)} linked)")
        self._translations = translations
        self._aliases = aliases
        self._on_applied = on_applied

    def redo(self) -> None:
        for translation, alias in zip(self._translations, self._aliases, strict=True):
            translation.aliases.append(alias)
        self._on_applied()

    def undo(self) -> None:
        for translation, alias in zip(self._translations, self._aliases, strict=True):
            translation.aliases.remove(alias)
        self._on_applied()


class RemoveGroupAliasCommand(QUndoCommand):
    def __init__(self, translations: list[Translation], index: int, on_applied: OnGroupApplied) -> None:
        super().__init__(f"Remove alias ({len(translations)} linked)")
        self._translations = translations
        self._index = index
        self._aliases = [t.aliases[index] for t in translations]
        self._on_applied = on_applied

    def redo(self) -> None:
        for translation in self._translations:
            del translation.aliases[self._index]
        self._on_applied()

    def undo(self) -> None:
        for translation, alias in zip(self._translations, self._aliases, strict=True):
            translation.aliases.insert(self._index, alias)
        self._on_applied()
