"""Regenerate the Mixxx part of the controller profile library.

    uv run python scripts/generate_mixxx_profiles.py <mixxx checkout>/res/controllers

Reads every ``*.midi.xml`` in that folder (in place -- Mixxx's mappings are
GPL and are never copied into this repo) and writes one JSON profile per
device under ``controllers/library/mixxx/``: its buttons, named after the
Mixxx function they drive. Built-in controllers and devices the rekordbox
part of the library already covers are skipped; see
``djmidi.catalog.library``. Prints one line per profile.
"""

from __future__ import annotations

import sys
from pathlib import Path

from djmidi import catalog
from djmidi.catalog.library import (
    LIBRARY_DIR,
    SOURCE_MIXXX,
    build_mixxx_profiles,
    list_library_profiles,
    write_library,
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    files = sorted(Path(argv[1]).glob("*.midi.xml"))
    if not files:
        print(f"No *.midi.xml in {argv[1]}")
        return 1
    rekordbox = [profile.name for profile in list_library_profiles(LIBRARY_DIR / "rekordbox")]
    definitions = build_mixxx_profiles(
        (path.read_text(encoding="utf-8") for path in files), skip_names=[*catalog.CONTROLLER_NAMES, *rekordbox]
    )
    written = write_library(definitions, LIBRARY_DIR / SOURCE_MIXXX, SOURCE_MIXXX)
    for definition, path in zip(definitions, written, strict=True):
        print(f"{definition.name:40} {len(definition.static_entries):4} entries  {path.name}")
    print(f"{len(written)} profile(s) from {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
