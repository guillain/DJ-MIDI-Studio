"""Real per-control geometry (position + shape + a semantic resting color)
for overlaying on top of a controller's actual reference photo
(``assets/controllers/``, see ``controller_image_view.py``) instead of the
abstract uniform-card schematic in ``layout_view.py``.

Coordinates are fractions (0..1) of the *full* reference image's width/height,
measured by eye against ``assets/controllers/<file>.png`` at full resolution.
A uniform fixed-size schematic card, as used elsewhere in the app, can't
represent a giant jog wheel and a small button at their true relative scale
without overlapping neighbours once real spacing is honoured -- overlaying
directly on the real photo sidesteps that entirely, since the photo already
encodes correct proportions and spacing.

Start of the "DJ layout visual fidelity" chantier (CLAUDE.md / TODO.md /
issue #13): only the "transport" cluster (PLAY/PAUSE, CUE, SYNC, jog wheel,
tempo fader) is modelled so far, and only for XDJ-XZ -- DDJ-XP2 is a pad/FX
companion controller with no deck transport section at all (its DECK section
is BEAT SYNC/SILENT CUE/QUANTIZE/KEY, not PLAY/CUE/SYNC), so it has no
transport geometry to model. Extending this to the rest of a controller's
physical layout is future work, one verified batch at a time (see the
project's rule against building visual-polish features blind -- every entry
here was checked by cropping the region of the real image it claims to
describe and screenshotting the rendered overlay against it, not guessed from
the PDF callout numbers alone).

XDJ-XZ has two mirrored deck sides (left tray = deck 1, right tray = deck 2);
only the left side's coordinates are recorded here. ``gui/layout.py``'s
schematic already collapses a control to one cell regardless of how many
decks map to it, so one set of coordinates -- picked arbitrarily as the left
deck's -- is consistent with that existing simplification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Shape = Literal["rect", "circle"]


@dataclass(frozen=True)
class ControlGeometry:
    """A control's bounding box, as fractions of the reference image's full
    width/height, plus a semantic resting color for the transport overlay."""

    x: float
    y: float
    w: float
    h: float
    shape: Shape
    color: str


# controller -> base label (matches gui.layout.cell_key()'s label for a real
# catalog entry, or a display-only label for a continuous control with no
# catalog entry, e.g. "Jog wheel"/"Tempo") -> geometry.
TRANSPORT_GEOMETRY: dict[str, dict[str, ControlGeometry]] = {
    "XDJ-XZ": {
        # Green: play state, matching the PLAY/PAUSE LED's real color.
        "PLAY/PAUSE": ControlGeometry(0.1497, 0.8420, 0.0296, 0.0484, "circle", "#3ea86b"),
        # Amber: matches the CUE LED's real color.
        "CUE": ControlGeometry(0.1521, 0.7726, 0.0249, 0.0408, "circle", "#e0954a"),
        # Blue: the conventional DJ-gear "sync" accent color.
        "SYNC": ControlGeometry(0.3532, 0.5312, 0.0187, 0.0306, "circle", "#4a90d9"),
        # Display-only (continuous, not a discrete catalog trigger): the
        # jog wheel and the tempo fader still deserve a place in the overlay.
        "Jog wheel": ControlGeometry(0.1439, 0.4268, 0.1944, 0.3185, "circle", "#586b82"),
        "Tempo": ControlGeometry(0.3560, 0.6911, 0.0156, 0.1911, "rect", "#6fa8c9"),
    },
}


__all__ = ["TRANSPORT_GEOMETRY", "ControlGeometry", "Shape"]
