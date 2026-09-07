"""Controller Emulator roadmap phase 5, slice 1 (issue #9): resolves a
toggle-behaviour click mapping's paired ``<userio event="output">`` aliases
against a locally-tracked on/off state -- the first time this project's
already-parsed/edited/exported ``Alias``/``Translation`` data is actually
*consumed* by any resolution logic, rather than just round-tripped.

Deliberately the smallest safe slice, chosen by the maintainer over a full
alias-resolution research pass (see ``~/.claude/plans/purrfect-fluttering-
quail.md``'s Phase 5 section): only mappings whose **click** translation is
explicitly ``behaviour="toggle"`` are handled here -- a real, unambiguous
on/off flip on every press, with no state to disambiguate beyond "was it
already on". The confirmed real-world ambiguity where ``selected`` and
``off`` share the same raw value (e.g. ``auto_loop_specific_length``,
whose click translation is ``action_on="any"`` with no ``behaviour`` at
all) needs genuine state about *which of several slots is the active one*,
not just a flip, and is deliberately out of scope here -- a later slice's
job.

This module makes no claim about what any specific Serato function tag
*means* (e.g. whether a given toggle mapping is "a hot cue"): it is purely
mechanical, driven entirely by the loaded config's own ``behaviour``
attribute, never by guessing a tag's semantics."""

from __future__ import annotations

from djmidi.gui.mapping_group import MappingGroup
from djmidi.model import Alias

_TOGGLE_BEHAVIOUR = "toggle"


def is_toggle_group(group: MappingGroup) -> bool:
    """True if `group`'s representative mapping's first translation is
    explicitly `behaviour="toggle"` -- the one click shape this slice
    handles. A group with no translations at all (malformed/unusual XML)
    is never a toggle group."""
    translations = group.representative.translations
    if not translations:
        return False
    return translations[0].behaviour == _TOGGLE_BEHAVIOUR


def find_output_group(groups: list[MappingGroup], click_group: MappingGroup) -> MappingGroup | None:
    """The `event="output"` group sharing `click_group`'s (deck_id,
    slot_id, tag) -- the paired LED/output side of the same logical
    function, wherever it lives among `groups` (typically a different
    raw trigger/channel than the click side, e.g. a separate MIDI-OUT
    channel). Returns None if the config has no such output mapping (some
    controls are click-only)."""
    for group in groups:
        if (
            group.event == "output"
            and group.deck_id == click_group.deck_id
            and group.slot_id == click_group.slot_id
            and group.tag == click_group.tag
        ):
            return group
    return None


def resolve_toggle_alias(output_group: MappingGroup | None, active: bool) -> Alias | None:
    """The `Alias` (name="on" or "off") matching `active` from
    `output_group`'s representative translation -- None if there is no
    output group at all, its translation carries no aliases, or the
    requested state simply isn't one of the aliases present (e.g. an
    output mapping with only a "selected" alias, which this slice doesn't
    resolve -- see the module docstring)."""
    if output_group is None:
        return None
    translations = output_group.representative.translations
    if not translations:
        return None
    wanted = "on" if active else "off"
    for alias in translations[0].aliases:
        if alias.name == wanted:
            return alias
    return None


__all__ = ["find_output_group", "is_toggle_group", "resolve_toggle_alias"]
