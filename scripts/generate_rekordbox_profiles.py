"""Regenerate the controller profile library from rekordbox's own mappings.

    uv run python scripts/generate_rekordbox_profiles.py \
        "/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings"

Reads every ``*.midi.csv`` in that folder (in place -- they are AlphaTheta's
files and are never copied into this repo) and writes one JSON profile per
device under ``controllers/library/rekordbox/``: its buttons and pads, named
and grouped as rekordbox names them. Built-in controllers are skipped; see
``djmidi.catalog.library`` for the rules. Prints one line per profile.
"""

from __future__ import annotations

import sys
from pathlib import Path

from djmidi import catalog
from djmidi.catalog.library import LIBRARY_DIR, build_rekordbox_profiles, write_library


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    folder = Path(argv[1])
    files = sorted(folder.glob("*.midi.csv"))
    if not files:
        print(f"No *.midi.csv in {folder}")
        return 1
    definitions = build_rekordbox_profiles(
        (path.read_text(encoding="utf-8") for path in files), skip_names=catalog.CONTROLLER_NAMES
    )
    written = write_library(definitions, LIBRARY_DIR / "rekordbox")
    for definition, path in zip(definitions, written, strict=True):
        print(f"{definition.name:20} {len(definition.static_entries):4} entries  {path.name}")
    print(f"{len(written)} profile(s) from {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
