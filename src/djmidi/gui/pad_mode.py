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
(``prefer_token`` in ``pick_default_variant``). DDJ-XP2, XDJ-XZ, the
Hercules DJControl Inpulse 500 and (issue #350) DDJ-FLX4, DDJ-800 and
DDJ-REV5 have pad-mode-select buttons in the catalog; the other
controllers' mode-select buttons aren't modelled, so this is a no-op
there. The Inpulse 500's SHIFT+mode-button modes 5-8 send their own notes,
so the catalog lists them as eight separate PAD MODE cells, each selecting
its own bank.

On DDJ-FLX4 and DDJ-REV5, SHIFT + a mode button selects a second mode
(its own, uncatalogued note), so with the emulator's SHIFT latched a mode
button click selects that SHIFT-layer bank instead (``_SHIFT_PAD_MODE_TOKENS``):
FLX4's KEYBOARD / PAD FX 2 / BEAT LOOP / KEY SHIFT as catalog/ddj_flx4.py
names them, REV5's PITCH PLAY / PIANO PLAY / STEMS / SCRATCH BANK as its
MIDI Message List prints beside P1-P4. DDJ-800's PDF gives SHIFT + P9-P12
their own notes too but never says which mode they select, so it has no
SHIFT layer here. DDJ-800's pad names also carry a page ("HOT CUE PAGE
1"); its token stops before the page number, so a mode button lands on
PAGE 1, the lower bank, like ``pick_default_variant``'s own default.

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
    "Hercules DJControl Inpulse 500": {f"PAD MODE {n}": f"(PAD MODE {n})" for n in range(1, 9)},
    # issue #350: the catalog's mode-button names -> its pad names' bank.
    "DDJ-FLX4": {
        "HOT CUE MODE": "(HOT CUE)",
        "PAD FX 1 MODE": "(PAD FX 1)",
        "BEAT JUMP MODE": "(BEAT JUMP)",
        "SAMPLER MODE": "(SAMPLER)",
    },
    "DDJ-800": {
        "HOT CUE MODE": "(HOT CUE PAGE ",
        "PAD FX MODE": "(PAD FX 1 PAGE ",
        "BEAT JUMP MODE": "(BEAT JUMP PAGE ",
        "SAMPLER MODE": "(SAMPLER PAGE ",
    },
    "DDJ-REV5": {
        name: f"({name})"
        for name in ("HOT CUE MODE", "ROLL MODE", "SAVED LOOP MODE", "SAMPLER MODE")
    },
}

# The mode SHIFT + a mode button selects, where the catalog names it.
_SHIFT_PAD_MODE_TOKENS: dict[str, dict[str, str]] = {
    "DDJ-FLX4": {
        "HOT CUE MODE": "(KEYBOARD)",
        "PAD FX 1 MODE": "(PAD FX 2)",
        "BEAT JUMP MODE": "(BEAT LOOP)",
        "SAMPLER MODE": "(KEY SHIFT)",
    },
    "DDJ-REV5": {
        "HOT CUE MODE": "(PITCH PLAY MODE)",
        "ROLL MODE": "(PIANO PLAY MODE)",
        "SAVED LOOP MODE": "(STEMS MODE)",
        "SAMPLER MODE": "(SCRATCH BANK MODE)",
    },
}


def grid_side(label: str) -> str:
    """``" (R)"`` for a right-grid cell label, ``""`` for a left one -- the
    key this module's state dicts are keyed by, matching how a pad cell's
    own label carries the suffix."""
    return _RIGHT_SUFFIX if label.endswith(_RIGHT_SUFFIX) else ""


def mode_token_for_button(controller: str, label: str, shift: bool = False) -> str | None:
    """The pad-variant name substring the mode-select button ``label``
    selects, or ``None`` when ``label`` isn't a known pad-mode-select
    button for ``controller``. With ``shift``, the SHIFT-layer mode when
    the catalog names one, else the plain mode."""
    base = label.removesuffix(_RIGHT_SUFFIX)
    plain = _PAD_MODE_TOKENS.get(controller, {}).get(base)
    if shift and plain is not None:
        return _SHIFT_PAD_MODE_TOKENS.get(controller, {}).get(base, plain)
    return plain


def is_pad_mode_button(controller: str, label: str) -> bool:
    return mode_token_for_button(controller, label) is not None


__all__ = ["grid_side", "is_pad_mode_button", "mode_token_for_button"]
