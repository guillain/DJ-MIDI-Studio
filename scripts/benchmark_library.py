"""Time the Music Library tab on a large synthetic collection.

    uv run python scripts/benchmark_library.py [--tracks 85000]

Builds a throwaway index (made-up paths and tags, nothing on disk is read),
then times what opening the tab and typing a filter do: the index read
(`consolidate`), the table and set-panel fill, the filter combos and a few
filter changes. Used for phase 5 item 7; re-run it before and after a
change to the library's load path.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJMIDI_DISABLE_MIDI", "1")

GENRES = ["Techno", "House", "Psytrance", "Drum & Bass", "Dub", "Hardtek", "Tribe", "Breakbeat", "Other", ""]
FOLDERS = ["Tek/HardTek", "Tek/Tribe", "Tek/PsyTrance", "Electro/Dub", "Electro/Drum & Bass", "Misc", "Incoming"]
KEYS = ["Am", "C", "8A", "9B", "F#m", "Ebm", "7m", "", "G", "Dm"]


def build_index(db_path: Path, count: int, seed: int = 7) -> None:
    from djmidi.library.db import LibraryDB
    from djmidi.library.metadata import TrackMetadata

    rng = random.Random(seed)
    db = LibraryDB(db_path)
    root = db.add_root("/Music")
    for index in range(count):
        folder = rng.choice(FOLDERS)
        path = f"/Music/{folder}/Artist {index % 4000}/Track {index}.mp3"
        db.upsert_track(root.id, path, 5_000_000 + index, 1_700_000_000.0 + index)
    db.commit()
    for record in db.list_tracks():
        metadata = TrackMetadata(
            title=f"Title {record.id}",
            artist=f"Artist {record.id % 4000}",
            genre=rng.choice(GENRES) or None,
            bpm=round(rng.uniform(80, 190), 1) if rng.random() > 0.05 else None,
            key=rng.choice(KEYS) or None,
        )
        db.set_cached_metadata(record.id, record.mtime, metadata)
    db.commit()
    db.close()


def _timed(label: str, action, results: dict[str, float]):
    start = time.perf_counter()
    value = action()
    results[label] = (time.perf_counter() - start) * 1000
    return value


def run(count: int) -> dict[str, float]:
    from PySide6.QtWidgets import QApplication

    from djmidi.gui.music_library_view import MusicLibraryView
    from djmidi.library import workspace
    from djmidi.library.db import LibraryDB

    app = QApplication.instance() or QApplication(sys.argv)
    results: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "library.sqlite3"
        _timed("build synthetic index", lambda: build_index(db_path, count), results)
        db = LibraryDB(db_path)
        _timed("consolidate (index -> rows)", lambda: workspace.consolidate(db), results)
        db.close()
        view = MusicLibraryView(db_path=db_path)
        _timed("open the tab (ensure_open)", view.ensure_open, results)
        _timed("reload rows", view.reload, results)
        _timed("filter: text 'artist 12'", lambda: view.filter_edit.setText("artist 12"), results)
        _timed("filter: text cleared", lambda: view.filter_edit.setText(""), results)
        _timed("filter: BPM 120-130", lambda: view.proxy.set_bpm_range(120, 130), results)
        app.processEvents()
        view.close_db()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tracks", type=int, default=85_000)
    args = parser.parse_args()
    for label, ms in run(args.tracks).items():
        print(f"{label:32s} {ms:9.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
