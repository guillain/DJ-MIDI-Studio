"""Short, readable names for Serato mapping tags (issue #209).

Serato names a mapped function by its XML tag (`auto_loop_roll_specific_length`),
which is what every view used to print verbatim. This table gives the tags
that actually occur in real files a short label for the cheat sheet, the
function search, the mapping diff and the tree tabs.

The table only covers the tags found in the repository's real Serato exports
(`data/xdj_xz-ddj_xp2-4decks.xml`, `data/serato/*.xml.zip`; the inventory is
also recorded in `software/traktor/README.md`): those four tags are the only
ones any real file uses. Each label is derived from nothing but the tag's own
words -- this project has never confirmed what a slot number stands for (which
loop length an `auto_loop_specific_length` slot is, see CLAUDE.md) nor what
Serato's `codfather_*` functions do, so a slot stays a slot number ("Loop roll
· slot 3", never "Loop roll 1/4") and the `codfather` tags are only re-cased
("Codfather ST"). Alias values are not used either: on real files they carry
LED values (`on=127`, `on=20`, `selected=0`), which say nothing about which
function an element is.

Any other tag -- a Traktor command name, a tag from a file this table has
never seen -- falls back to the raw tag unchanged, and every caller keeps the
raw tag visible (tooltip, secondary text or the cheat sheet's glossary page),
so nothing is hidden behind a label.

Qt-free, like `function_search.py` and `mapping_diff.py`, which use it.
"""

from __future__ import annotations

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

# Raw Serato tag -> short label. Only tags seen in real exports belong here.
FUNCTION_NAMES: dict[str, str] = {
    # "auto loop" of a "specific length" -- the slot picks the length.
    "auto_loop_specific_length": "Auto loop",
    # The same, as a loop *roll* (momentary loop).
    "auto_loop_roll_specific_length": "Loop roll",
    # Meaning unconfirmed: re-cased only, nothing inferred.
    "codfather_st": "Codfather ST",
    "codfather_fx": "Codfather FX",
}

_NO_SLOT = ("", "(none)")

#: The slot suffix of a label, translated by the GUI (issue #326).
SLOT_SUFFIX = QT_TRANSLATE_NOOP("FunctionNames", "{name} · slot {slot}")


def is_known(tag: str) -> bool:
    """Whether `tag` has a readable name (otherwise it is shown raw)."""
    return tag in FUNCTION_NAMES


def function_name(tag: str) -> str:
    """The short label for `tag`, or `tag` itself when it has none."""
    return FUNCTION_NAMES.get(tag, tag)


def function_label(tag: str, slot_id: str | None = None, translate: Translate = untranslated) -> str:
    """The short label with its slot, when the element has one:
    `("auto_loop_roll_specific_length", "3")` -> "Loop roll · slot 3".
    The GUI passes a `translate` for the slot suffix's language."""
    name = function_name(tag)
    if slot_id is None or slot_id in _NO_SLOT:
        return name
    return translate(SLOT_SUFFIX).format(name=name, slot=slot_id)


def label_with_raw(tag: str, slot_id: str | None = None, translate: Translate = untranslated) -> str:
    """The short label followed by the raw tag in parentheses, for a
    tooltip or secondary text; just the raw label for an unknown tag."""
    label = function_label(tag, slot_id, translate)
    return f"{label} ({tag})" if is_known(tag) else label


__all__ = [
    "FUNCTION_NAMES",
    "SLOT_SUFFIX",
    "function_label",
    "function_name",
    "is_known",
    "label_with_raw",
]
