"""Normalize controller reference images: transparent background, cropped
margin, common width.

    uv run --no-project --with pillow --with numpy --with scipy \
        python scripts/process_controller_images.py controllers/hardware/<vendor>/<Model>/reference.png ...

Each file is rewritten in place and its crop box is printed. Run it on a new
image *before* measuring its gui/geometry.CONTROL_GEOMETRY: the fractions
are relative to the processed image, and re-processing an already-measured
image would shift them (remap them from the printed crop box if you must).

- ``reference.png`` (the controller photo): the background connected to the
  image edges becomes transparent, with a soft edge, but only outside the
  device's filled silhouette, so a line drawing keeps its white inside.
- ``reference-midi.png`` (the MIDI picture): composited on white and kept
  opaque -- its titles and callouts are dark text that needs the background.
- Both are cropped to their content plus a 1 % margin and resized to
  2000 px wide (Lanczos), keeping their proportions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

TARGET_W = 2000
T_LOW, T_HIGH = 14.0, 60.0  # colour distance to the background: transparent below, opaque above
PAD = 0.01


def process(path: Path) -> dict:
    transparent = path.name == "reference.png"
    im = Image.open(path).convert("RGBA")
    if not transparent:
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
    a = np.asarray(im).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3]
    H, W = alpha.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    border_alpha = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
    opaque_border = border[border_alpha > 200]
    if len(opaque_border) < 0.5 * len(border):
        new_alpha, content = alpha, alpha > 8  # already transparent around
    else:
        bg = np.median(opaque_border, axis=0)
        dist = np.sqrt(((rgb - bg) ** 2).sum(axis=-1))
        near = dist < T_HIGH
        if not transparent:
            new_alpha, content = alpha, dist > T_HIGH
        else:
            k = max(3, round(max(W, H) / 400))
            solid = ndimage.binary_closing(~near, structure=np.ones((k, k)), iterations=2)
            silhouette = ndimage.binary_fill_holes(solid)
            labels, _ = ndimage.label(near)
            edges = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
            region = np.isin(labels, edges[edges > 0]) & ~silhouette
            soft = np.clip((dist - T_LOW) / (T_HIGH - T_LOW), 0, 1) * 255
            new_alpha = np.where(region, np.minimum(alpha, soft), alpha)
            content = new_alpha > 8
    ys, xs = np.nonzero(content)
    pad_x, pad_y = int(W * PAD), int(H * PAD)
    box = (
        max(int(xs.min()) - pad_x, 0),
        max(int(ys.min()) - pad_y, 0),
        min(int(xs.max()) + 1 + pad_x, W),
        min(int(ys.max()) + 1 + pad_y, H),
    )
    out = Image.fromarray(np.dstack([rgb, new_alpha]).astype(np.uint8), "RGBA").crop(box)
    out = out.resize((TARGET_W, round(out.height * TARGET_W / out.width)), Image.Resampling.LANCZOS)
    out.save(path, optimize=True)
    return {"original": (W, H), "crop": box, "size": out.size}


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, process(Path(arg)))
