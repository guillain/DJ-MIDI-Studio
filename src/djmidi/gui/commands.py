from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
from PySide6.QtGui import QUndoCommand

from djmidi.model import Alias, Control, MidiConfig, Translation

OnApplied = Callable[[object], None]

_CONTEXT = "Commands"


def _texts(template: str, **fields: object) -> tuple[str, str]:
    """``(English, interface language)`` for a command marked with
    ``QT_TRANSLATE_NOOP("Commands", ...)``: Edit → Undo/Redo shows the
    translation, `summary` keeps the English (issue #337)."""
    return template.format(**fields), QCoreApplication.translate(_CONTEXT, template).format(**fields)


def _library_texts(summary: str) -> tuple[str, str]:
    """Same for a Music Library write, whose English `summary` is what the
    persistent change log records. Shown through the Change history window's
    own wording, so the Undo menu and that window always agree."""
    from djmidi.gui.change_history_dialog import describe_summary

    return summary, describe_summary(summary)


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
        if label:
            self.summary, text = label, label
        else:
            self.summary, text = _texts(QT_TRANSLATE_NOOP("Commands", "Edit {attr}"), attr=attr)
        super().__init__(text)
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
        self.summary, text = _texts(QT_TRANSLATE_NOOP("Commands", "Add alias"))
        super().__init__(text)
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
        self.summary, text = _texts(QT_TRANSLATE_NOOP("Commands", "Remove alias"))
        super().__init__(text)
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
        if label:
            self.summary, text = label, label
        else:
            self.summary, text = _texts(
                QT_TRANSLATE_NOOP("Commands", "Edit {attr} ({count} linked)"), attr=attr, count=len(targets)
            )
        super().__init__(text)
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
        self.summary, text = _texts(
            QT_TRANSLATE_NOOP("Commands", "Add alias ({count} linked)"), count=len(translations)
        )
        super().__init__(text)
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
        self.summary, text = _texts(
            QT_TRANSLATE_NOOP("Commands", "Remove alias ({count} linked)"), count=len(translations)
        )
        super().__init__(text)
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


class ReplaceControlsCommand(QUndoCommand):
    """Swaps the mapping's whole control list for another (a structural edit
    such as copying a deck's mappings): one undo step whatever its size."""

    def __init__(
        self,
        config: MidiConfig,
        controls: list[Control],
        summary: str,
        text: str,
        on_applied: Callable[[], None],
    ) -> None:
        super().__init__(text)
        self.summary = summary
        self._config = config
        self._old = list(config.controls)
        self._new = list(controls)
        self._on_applied = on_applied

    def redo(self) -> None:
        self._config.controls = list(self._new)
        self._on_applied()

    def undo(self) -> None:
        self._config.controls = list(self._old)
        self._on_applied()


# Logs a tag write in the persistent change history (issue #261):
# (summary, {path: (old values, new values)}) for the files written.
ChangeRecorder = Callable[[str, dict[str, tuple[dict[str, object], dict[str, object]]]], None]
# Same for a cover write (issue #279): (summary, path, old cover, new cover).
CoverRecorder = Callable[[str, str, object | None, object | None], None]
# Same for renames (issue #279): (summary, [(old path, new path)]).
RenameRecorder = Callable[[str, list[tuple[str, str]]], None]


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
        recorder: ChangeRecorder | None = None,
    ) -> None:
        changed = sorted(new_values)
        self.summary, text = _library_texts(f"Edit {', '.join(changed)} of {path.rsplit('/', 1)[-1]}")
        super().__init__(text)
        self._path = path
        self._old = {name: old_values.get(name) for name in changed}
        self._new = dict(new_values)
        self._on_applied = on_applied
        if writer is None:
            from djmidi.library.metadata import write_metadata as writer
        self._writer = writer
        self._recorder = recorder

    def redo(self) -> None:
        self._writer(self._path, **self._new)
        if self._recorder is not None:
            self._recorder(self.summary, {self._path: (self._old, self._new)})
        self._on_applied(self._path)

    def undo(self) -> None:
        self._writer(self._path, **self._old)
        if self._recorder is not None:
            self._recorder(f"Undo: {self.summary}", {self._path: (self._new, self._old)})
        self._on_applied(self._path)


class WriteTrackCoverCommand(QUndoCommand):
    """Undoable set/removal of one audio file's front cover (Music Library
    Track panel, issue #256). The previous front cover is read once, when
    the command is built, and undo writes it back (or removes the new one
    when there was none) through the same surgical `write_cover_art`, so
    other pictures, tags and Serato/Traktor frames stay untouched.

    An optional `recorder(summary, path, old cover, new cover)` logs every
    pass (the write, an undo, a redo) in the persistent change history
    (issue #279)."""

    def __init__(
        self,
        path: str,
        new_cover: object | None,
        on_applied: Callable[[str], None],
        writer: Callable[[str, object | None], None] | None = None,
        reader: Callable[[str], object | None] | None = None,
        recorder: CoverRecorder | None = None,
    ) -> None:
        verb = "Set" if new_cover is not None else "Remove"
        self.summary, text = _library_texts(f"{verb} cover of {path.rsplit('/', 1)[-1]}")
        super().__init__(text)
        if writer is None or reader is None:
            from djmidi.library.cover_art import read_front_cover, write_cover_art

            writer = writer or write_cover_art
            reader = reader or read_front_cover
        self._path = path
        self._old = reader(path)
        self._new = new_cover
        self._writer = writer
        self._on_applied = on_applied
        self._recorder = recorder

    def redo(self) -> None:
        self._writer(self._path, self._new)
        if self._recorder is not None:
            self._recorder(self.summary, self._path, self._old, self._new)
        self._on_applied(self._path)

    def undo(self) -> None:
        self._writer(self._path, self._old)
        if self._recorder is not None:
            self._recorder(f"Undo: {self.summary}", self._path, self._new, self._old)
        self._on_applied(self._path)


# A progress callback: (files done, total) -> False to stop after the
# current file. Made fresh by a factory for every redo/undo pass, so each
# pass (the first write, an undo hours later, a redo) gets its own dialog.
Progress = Callable[[int, int], bool]
ProgressFactory = Callable[[str, int], Progress]


class WriteTracksMetadataCommand(QUndoCommand):
    """Undoable write of managed tags to several audio files at once (Music
    Library tab, "Write tags to selection…"). One undo step for the whole
    batch. A file that fails to write is recorded in `failures` and skipped
    (also on undo) instead of aborting the rest; if nothing at all could be
    written the command marks itself obsolete so `QUndoStack.push` drops it.

    Writing thousands of files takes a while, so an optional
    `progress_factory(label, total)` is called at the start of every redo and
    undo and its callback after each file. When the callback returns False
    the pass stops there (`cancelled` is set): files already written stay
    written and are exactly the ones an undo restores."""

    def __init__(
        self,
        changes: dict[str, tuple[dict[str, object], dict[str, object]]],
        on_applied: Callable[[list[str]], None],
        writer: Callable[..., None] | None = None,
        progress_factory: ProgressFactory | None = None,
        recorder: ChangeRecorder | None = None,
    ) -> None:
        fields = sorted({name for _old, new in changes.values() for name in new})
        self.summary, text = _library_texts(f"Edit {', '.join(fields)} of {len(changes)} tracks")
        super().__init__(text)
        self._changes = {path: (dict(old), dict(new)) for path, (old, new) in changes.items()}
        self._on_applied = on_applied
        if writer is None:
            from djmidi.library.metadata import write_metadata as writer
        self._writer = writer
        self._progress_factory = progress_factory
        self._recorder = recorder
        self.written: list[str] = []
        self.failures: dict[str, str] = {}
        self.cancelled = False

    def _write_all(self, label: str, items: list[tuple[str, dict[str, object]]]) -> list[str]:
        progress = self._progress_factory(label, len(items)) if self._progress_factory else None
        done: list[str] = []
        self.cancelled = False
        for index, (path, fields) in enumerate(items):
            if progress is not None and not progress(index, len(items)):
                self.cancelled = True
                break
            try:
                self._writer(path, **fields)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
                self.failures[path] = str(exc)
            else:
                done.append(path)
        if progress is not None:
            progress(len(items), len(items))
        return done

    def redo(self) -> None:
        self.failures = {}
        self.written = self._write_all(QCoreApplication.translate("Commands", "Writing tags…"), [(path, new) for path, (_old, new) in self._changes.items()])
        if not self.written:
            self.setObsolete(True)
            return
        if self._recorder is not None:
            self._recorder(self.summary, {path: self._changes[path] for path in self.written})
        self._on_applied(self.written)

    def undo(self) -> None:
        restored = self._write_all(QCoreApplication.translate("Commands", "Restoring tags…"), [(path, self._changes[path][0]) for path in self.written])
        if self._recorder is not None and restored:
            self._recorder(
                f"Undo: {self.summary}", {path: (self._changes[path][1], self._changes[path][0]) for path in restored}
            )
        self._on_applied(restored)


class RenameFilesCommand(QUndoCommand):
    """Undoable rename of audio files from a tag template (Music Library
    tab, issue #260). `apply(pairs)` renames ``(old, new)`` pairs and returns
    a `library.rename.RenameResult`; undo calls it again with every pair it
    actually renamed swapped back. A pair that fails (on redo or undo) is
    recorded in `failures` instead of aborting the rest; if nothing at all
    was renamed the command marks itself obsolete so `QUndoStack.push`
    drops it. An optional `recorder(summary, pairs)` logs the pairs each
    pass actually renamed in the persistent change history (issue #279)."""

    def __init__(
        self,
        pairs: list[tuple[str, str]],
        apply: Callable[[list[tuple[str, str]]], object],
        on_applied: Callable[[list[tuple[str, str]]], None],
        recorder: RenameRecorder | None = None,
    ) -> None:
        self.summary, text = _library_texts(f"Rename {len(pairs)} file(s)")
        super().__init__(text)
        self._pairs = list(pairs)
        self._apply = apply
        self._on_applied = on_applied
        self._recorder = recorder
        self.renamed: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []

    def redo(self) -> None:
        result = self._apply(self._pairs)
        self.renamed = list(result.renamed)
        self.failures = list(result.failed)
        if not self.renamed:
            self.setObsolete(True)
            return
        # A later redo (after an undo) replays only what this one renamed.
        self._pairs = list(self.renamed)
        if self._recorder is not None:
            self._recorder(self.summary, list(self.renamed))
        self._on_applied(self.renamed)

    def undo(self) -> None:
        result = self._apply([(new, old) for old, new in reversed(self.renamed)])
        self.failures = list(result.failed)
        restored = list(result.renamed)
        if self._recorder is not None and restored:
            self._recorder(f"Undo: {self.summary}", restored)
        self._on_applied(restored)
