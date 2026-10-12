"""Helpers of scripts/capture_docs_screenshots.py (issue #213). The script
itself takes minutes and writes into docs/images, so only its building
blocks are checked here."""

import importlib.util
from pathlib import Path

from djmidi.gui.audio_preview import AudioPreviewBar

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_docs_screenshots.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("capture_docs_screenshots", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_player_drives_the_preview_bar(tmp_path):
    script = _load_script()
    track = tmp_path / "track.mp3"
    track.write_bytes(b"")
    bar = AudioPreviewBar(player_factory=script._DemoPlayer)
    bar.set_source(track)
    bar.play()
    bar._player.durationChanged.emit(360_000)
    bar._player.positionChanged.emit(132_000)
    assert bar.is_playing()
    assert bar.time_label.text() == "2:12 / 6:00"
    bar.stop()
    assert not bar.is_playing()


def test_demo_music_dir_is_removed_afterwards():
    script = _load_script()
    with script._demo_music_dir() as music:
        music.mkdir(parents=True)
        (music / "a.mp3").write_bytes(b"x")
        assert music.is_dir()
    assert not music.exists()


def test_demo_library_has_one_file_per_track(tmp_path):
    script = _load_script()
    script._write_demo_library(tmp_path)
    assert len(list(tmp_path.rglob("*.mp3"))) == len(script.DEMO_TRACKS)
