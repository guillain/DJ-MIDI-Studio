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
attribute, never by guessing a tag's semantics.

``describe_output_aliases()`` (slice 1's immediate follow-up) covers the
case ``resolve_toggle_alias()`` explicitly declines: for a non-toggle
output mapping without tracked state, it surfaces the *entire* alias set
read-only, rather than guessing which one currently applies.

``is_radio_group()`` / ``radio_group_key()`` (v0.47.69) are phase 5's
other, larger piece for the Controller Emulator: an output mapping with a
``selected`` alias is one member of a mutually-exclusive set (every
``auto_loop_specific_length`` slot on a deck), so clicking one makes it
"selected" and every sibling "off". The emulator tracks the selected slot
per ``(deck_id, tag)`` and lights it -- see
``ControllerEmulatorView._selected_slot``."""

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


def is_radio_group(output_group: MappingGroup | None) -> bool:
    """True if `output_group`'s output translation carries a "selected"
    alias -- the marker that it's one member of a mutually-exclusive set
    (the confirmed `auto_loop_specific_length` shape, where "selected" and
    "off" share a raw value so only tracked state can say which member is
    the active one). A `behaviour="toggle"` mapping is handled by
    resolve_toggle_alias() instead; this is phase 5's other, larger half."""
    if output_group is None:
        return False
    translations = output_group.representative.translations
    if not translations:
        return False
    return any(alias.name == "selected" for alias in translations[0].aliases)


def radio_group_key(group: MappingGroup) -> tuple[str, str]:
    """The `(deck_id, tag)` identifying the mutually-exclusive set `group`
    belongs to: clicking any member makes it "selected" and every sibling
    "off"."""
    return (group.deck_id, group.tag)


def describe_output_aliases(output_group: MappingGroup | None) -> str:
    """A read-only "name=value, name=value, ..." summary of every alias on
    `output_group`'s representative translation, in file order -- "" if
    there is no output group or its translation carries no aliases at all.

    Deliberately makes no attempt to decide *which* alias currently
    applies (that's resolve_toggle_alias()'s job, and only for a
    behaviour="toggle" mapping): this is for the ambiguous case
    resolve_toggle_alias() explicitly declines to handle -- a mapping
    with a "selected" alias sharing its raw value with "off" (see the
    module docstring) has no way to know which one a given value means
    without real state this project doesn't track yet, so the Controller
    Emulator surfaces the whole alias set as information instead of
    guessing at one."""
    if output_group is None:
        return ""
    translations = output_group.representative.translations
    if not translations or not translations[0].aliases:
        return ""
    return ", ".join(f"{alias.name}={alias.value}" for alias in translations[0].aliases)


__all__ = [
    "describe_output_aliases",
    "find_output_group",
    "is_radio_group",
    "is_toggle_group",
    "radio_group_key",
    "resolve_toggle_alias",
]
