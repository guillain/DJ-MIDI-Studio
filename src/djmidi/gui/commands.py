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


class WriteTrackMetadataCommand(QUndoCommand):
    """Undoable write of managed tags to one real audio file (Music Library
    tab, issue #132). Undo writes the previous values back through the same
    surgical `write_metadata` path, so Serato/Traktor frames stay untouched
    either way."""

    def __init__(
        self,
        path: str,
        old_values: dict[str, object],
        new_values: dict[str, object],
        on_applied: Callable[[str], None],
        writer: Callable[..., None] | None = None,
    ) -> None:
        changed = sorted(new_values)
        super().__init__(f"Edit {', '.join(changed)} of {path.rsplit('/', 1)[-1]}")
        self._path = path
        self._old = {name: old_values.get(name) for name in changed}
        self._new = dict(new_values)
        self._on_applied = on_applied
        if writer is None:
            from djmidi.library.metadata import write_metadata as writer
        self._writer = writer

    def redo(self) -> None:
        self._writer(self._path, **self._new)
        self._on_applied(self._path)

    def undo(self) -> None:
        self._writer(self._path, **self._old)
        self._on_applied(self._path)


class WriteTracksMetadataCommand(QUndoCommand):
    """Undoable write of managed tags to several audio files at once (Music
    Library tab, "Write tags to selection…"). One undo step for the whole
    batch. A file that fails to write is recorded in `failures` and skipped
    (also on undo) instead of aborting the rest; if nothing at all could be
    written the command marks itself obsolete so `QUndoStack.push` drops it."""

    def __init__(
        self,
        changes: dict[str, tuple[dict[str, object], dict[str, object]]],
        on_applied: Callable[[list[str]], None],
        writer: Callable[..., None] | None = None,
    ) -> None:
        fields = sorted({name for _old, new in changes.values() for name in new})
        super().__init__(f"Edit {', '.join(fields)} of {len(changes)} tracks")
        self._changes = {path: (dict(old), dict(new)) for path, (old, new) in changes.items()}
        self._on_applied = on_applied
        if writer is None:
            from djmidi.library.metadata import write_metadata as writer
        self._writer = writer
        self.written: list[str] = []
        self.failures: dict[str, str] = {}

    def redo(self) -> None:
        self.written, self.failures = [], {}
        for path, (_old, new) in self._changes.items():
            try:
                self._writer(path, **new)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
                self.failures[path] = str(exc)
            else:
                self.written.append(path)
        if not self.written:
            self.setObsolete(True)
            return
        self._on_applied(self.written)

    def undo(self) -> None:
        restored: list[str] = []
        for path in self.written:
            try:
                self._writer(path, **self._changes[path][0])
            except Exception as exc:  # noqa: BLE001
                self.failures[path] = str(exc)
            else:
                restored.append(path)
        self._on_applied(restored)
