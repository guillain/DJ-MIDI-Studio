"""Pad-mode-page tracking for the Controller Emulator (issue #9 phase 5).

A pad's raw MIDI trigger depends on which *pad mode* the deck is in (HOT
CUE vs BEAT LOOP vs ...), and `reverse_lookup()` collapses every mode's
bank into one schematic cell. `layout.pick_default_variant()` normally
resolves such a cell to a fixed documented default (the lowest-numbered
mode). This module lets the emulator do better: when the user clicks a
**pad-mode-select button** in an emulator instance, subsequent pad clicks
in that instance resolve against the chosen mode's bank instead.

The mechanism is a per-controller table mapping a mode button's cell label
to the substring its pad variants' names carry while that mode is active
(``prefer_token`` in ``pick_default_variant``). Only DDJ-XP2 and XDJ-XZ
have pad-mode-select buttons in the catalog; the other controllers'
mode-select buttons aren't modelled, so this is a no-op there.

DDJ-XP2's four physical PAD MODE buttons each double as two modes via
single vs. double click (PAD MODE 1/5, 2/6, ...); the emulator is
discrete-click only (phase 3), so clicking one always selects its
single-click mode (1-4), never 5-8.
"""

from __future__ import annotations

_RIGHT_SUFFIX = " (R)"

# controller -> {mode-button cell label: token that appears in a pad
# variant's ``name`` while that mode is active}.
_PAD_MODE_TOKENS: dict[str, dict[str, str]] = {
    "DDJ-XP2": {f"PAD MODE {n}": f"(PAD MODE {n})" for n in range(1, 9)},
    "XDJ-XZ": {
        "HOT CUE": "(HOT CUE mode)",
        "BEAT LOOP": "(BEAT LOOP mode)",
        "SLIP LOOP": "(SLIP LOOP mode)",
        "BEAT JUMP": "(BEAT JUMP mode)",
    },
}


def grid_side(label: str) -> str:
    """``" (R)"`` for a right-grid cell label, ``""`` for a left one -- the
    key this module's state dicts are keyed by, matching how a pad cell's
    own label carries the suffix."""
    return _RIGHT_SUFFIX if label.endswith(_RIGHT_SUFFIX) else ""


def mode_token_for_button(controller: str, label: str) -> str | None:
    """The pad-variant name substring the mode-select button ``label``
    selects, or ``None`` when ``label`` isn't a known pad-mode-select
    button for ``controller``."""
    base = label.removesuffix(_RIGHT_SUFFIX)
    return _PAD_MODE_TOKENS.get(controller, {}).get(base)


def is_pad_mode_button(controller: str, label: str) -> bool:
    return mode_token_for_button(controller, label) is not None


__all__ = ["grid_side", "is_pad_mode_button", "mode_token_for_button"]
