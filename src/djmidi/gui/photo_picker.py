"""Turning clicks on a controller's photo (`EmulatorLayoutView`) into atelier
features, with the same small state the Controller Emulator keeps: a
pad-mode button picks the bank later pad clicks resolve to (per grid side),
and SHIFT latches the SHIFT layer. The picked control, the active mode
buttons and SHIFT stay lit.

Shared by the macro step dialog and the Atelier tab (issue #413); it says
what a click did (`Pick`) and leaves the wording to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from djmidi.atelier.features import Feature, feature_for_message
from djmidi.gui import layout as layout_mod
from djmidi.gui import pad_mode as pad_mode_mod
from djmidi.gui.layout import CellKey

SHIFT = "shift"
PAD_MODE = "pad_mode"
FEATURE = "feature"
NO_FEATURE = "no_feature"
_EVENT_TYPE_FOR_KIND = {"NOTE": "Note On", "CC": "Control Change"}


@dataclass(frozen=True)
class Pick:
    """What one click did: SHIFT toggled (`shift_held`), a pad mode set
    (`mode` = the button's label), a feature picked, or no feature."""

    kind: str
    key: CellKey
    feature: Feature | None = None
    shift_held: bool = False
    mode: str = ""


class PhotoPicker:
    def __init__(self, photo) -> None:
        self.photo = photo  # an EmulatorLayoutView (only set_active is used)
        self._pad_mode: dict[str, str] = {}
        self._pad_mode_key: dict[str, CellKey] = {}
        self.shift_held = False
        self._shift_key: CellKey | None = None
        self.picked_key: CellKey | None = None

    def click(self, key: CellKey) -> Pick:
        if key[2].removesuffix(" (R)") == "SHIFT":
            return self._toggle_shift(key)
        token = pad_mode_mod.mode_token_for_button(key[0], key[2], self.shift_held)
        if token is not None:
            return self._set_pad_mode(key, token)
        feature = self.feature_for_key(key)
        if feature is None:
            return Pick(NO_FEATURE, key)
        return Pick(FEATURE, key, feature)

    def mark_picked(self, key: CellKey | None) -> None:
        """Lights `key` as the picked control (None: just unlights the last)."""
        held = (self._shift_key, *self._pad_mode_key.values())
        if self.picked_key is not None and self.picked_key not in held:
            self.photo.set_active(self.picked_key, False)
        self.picked_key = key
        if key is not None:
            self.photo.set_active(key, True)

    def feature_for_key(self, key: CellKey) -> Feature | None:
        """The feature `key` stands for now: this side's deck, the latched
        pad mode and SHIFT -- the variant the Controller Emulator picks."""
        prefer_token = self._pad_mode.get(pad_mode_mod.grid_side(key[2])) if key[1] == "PAD" else None
        entry = layout_mod.resolve_side_aware_variant(key[0], key, prefer_token, self.shift_held)
        if entry is None or not entry.channels or not entry.channels[0].isdigit() or not entry.data1.isdigit():
            return None
        return feature_for_message(
            key[0], _EVENT_TYPE_FOR_KIND[entry.note_or_cc], int(entry.channels[0]), int(entry.data1)
        )

    def _toggle_shift(self, key: CellKey) -> Pick:
        self.shift_held = not self.shift_held
        previous = self._shift_key
        self._shift_key = key if self.shift_held else None
        if previous is not None and previous != key:
            self.photo.set_active(previous, False)
        self.photo.set_active(key, self.shift_held)
        return Pick(SHIFT, key, shift_held=self.shift_held)

    def _set_pad_mode(self, key: CellKey, token: str) -> Pick:
        side = pad_mode_mod.grid_side(key[2])
        previous = self._pad_mode_key.get(side)
        if previous is not None and previous != key:
            self.photo.set_active(previous, False)
        self._pad_mode[side] = token
        self._pad_mode_key[side] = key
        self.photo.set_active(key, True)
        return Pick(PAD_MODE, key, mode=key[2].removesuffix(" (R)"))


__all__ = ["FEATURE", "NO_FEATURE", "PAD_MODE", "SHIFT", "PhotoPicker", "Pick"]
