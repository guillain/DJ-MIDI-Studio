"""Tests for the Music Library tab's audio preview bar (issue #192).

Offscreen CI may have no audio device, so the state logic runs against a
fake player; one test builds the real `QMediaPlayer` without playing.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QHideEvent

from djmidi.gui import audio_preview
from djmidi.gui.audio_preview import AudioPreviewBar, format_time, start_position_ms


class FakePlayer(QObject):
    durationChanged = Signal(int)
    positionChanged = Signal(int)
    playbackStateChanged = Signal(int)
    errorOccurred = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.source: QUrl | None = None
        self.playing = False
        self.positions: list[int] = []
        self.calls: list[str] = []

    def setSource(self, url: QUrl) -> None:
        self.source = url
        self.calls.append("setSource")

    def play(self) -> None:
        self.playing = True
        self.calls.append("play")

    def pause(self) -> None:
        self.playing = False
        self.calls.append("pause")

    def stop(self) -> None:
        self.playing = False
        self.calls.append("stop")

    def setPosition(self, position: int) -> None:
        self.positions.append(position)

    def isPlaying(self) -> bool:
        return self.playing


def _bar() -> tuple[AudioPreviewBar, list[FakePlayer]]:
    created: list[FakePlayer] = []

    def factory(parent: QObject) -> FakePlayer:
        player = FakePlayer(parent)
        created.append(player)
        return player

    return AudioPreviewBar(player_factory=factory), created


def _wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    return path


def test_pure_helpers():
    assert start_position_ms(200_000) == 60_000
    assert start_position_ms(0) == 0
    assert start_position_ms(1000, 2.0) == 1000
    assert format_time(0) == "0:00"
    assert format_time(83_400) == "1:23"
    assert format_time(3_725_000) == "1:02:05"


def test_player_is_created_lazily_on_first_play(tmp_path):
    bar, created = _bar()
    track = str(tmp_path / "a.wav")
    bar.set_source(track)
    assert created == []
    assert bar.play_button.isEnabled()
    bar.play()
    assert len(created) == 1
    assert created[0].source == QUrl.fromLocalFile(track)
    assert created[0].playing
    assert bar.play_button.text().endswith("Pause")


def test_no_source_disables_transport():
    bar, created = _bar()
    assert not bar.play_button.isEnabled()
    bar.play()
    assert created == []


def test_start_offset_applied_once_duration_is_known(tmp_path):
    bar, created = _bar()
    bar.offset_check.setChecked(True)
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    player = created[0]
    assert player.positions == []
    player.durationChanged.emit(200_000)
    assert player.positions == [60_000]
    assert bar.seek_slider.maximum() == 200_000
    # Not re-applied on a later duration update.
    player.durationChanged.emit(200_000)
    assert player.positions == [60_000]


def test_no_offset_when_unchecked(tmp_path):
    bar, created = _bar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    created[0].durationChanged.emit(200_000)
    assert created[0].positions == []


def test_changing_track_while_playing_keeps_auditioning(tmp_path):
    bar, created = _bar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    player = created[0]
    bar.set_source(str(tmp_path / "b.wav"))
    assert player.source == QUrl.fromLocalFile(str(tmp_path / "b.wav"))
    assert player.playing
    bar.pause()
    bar.set_source(str(tmp_path / "c.wav"))
    assert not player.playing


def test_clearing_source_stops(tmp_path):
    bar, created = _bar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    bar.set_source(None)
    assert not created[0].playing
    assert not bar.play_button.isEnabled()


def test_position_updates_slider_and_label(tmp_path):
    bar, created = _bar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    created[0].durationChanged.emit(125_000)
    created[0].positionChanged.emit(42_000)
    assert bar.seek_slider.value() == 42_000
    assert bar.time_label.text() == "0:42 / 2:05"
    bar.seek_slider.setValue(90_000)
    bar._on_slider_released()
    assert created[0].positions[-1] == 90_000


def test_player_error_is_shown(tmp_path):
    bar, created = _bar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    created[0].errorOccurred.emit(1, "Unsupported format")
    assert bar.time_label.text() == "Cannot play"
    assert bar.time_label.toolTip() == "Unsupported format"
    bar.set_source(str(tmp_path / "b.wav"))
    assert bar.time_label.text() != "Cannot play"


def test_degrades_when_multimedia_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_preview, "QMediaPlayer", None)
    monkeypatch.setattr(audio_preview, "QAudioOutput", None)
    assert not audio_preview.multimedia_available()
    bar = AudioPreviewBar()
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()  # no crash
    assert not bar.available
    assert not bar.play_button.isEnabled()
    assert not bar.offset_check.isEnabled()
    assert bar.play_button.toolTip() == audio_preview.UNAVAILABLE_TOOLTIP


def test_degrades_when_player_creation_fails(tmp_path):
    def factory(_parent):
        raise RuntimeError("no backend")

    bar = AudioPreviewBar(player_factory=factory)
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    assert not bar.available
    assert not bar.play_button.isEnabled()


@pytest.mark.skipif(not audio_preview.multimedia_available(), reason="QtMultimedia unavailable")
def test_real_player_accepts_a_wav_source(tmp_path):
    owner = QObject()
    player = audio_preview._default_player_factory(owner)
    path = _wav(tmp_path / "tone.wav")
    player.setSource(QUrl.fromLocalFile(str(path)))
    assert player.source() == QUrl.fromLocalFile(str(path))


# --- Music Library tab wiring --------------------------------------------


def _library_with_fake_player(tmp_path):
    from djmidi.gui.music_library_view import MusicLibraryView

    root = tmp_path / "music"
    root.mkdir()
    _wav(root / "one.wav")
    _wav(root / "two.wav")
    view = MusicLibraryView(db_path=":memory:")
    created: list[FakePlayer] = []

    def factory(parent):
        created.append(FakePlayer(parent))
        return created[-1]

    view.audio_preview._player_factory = factory
    view.ensure_open()
    view.add_root(root)
    view.start_scan()
    view.run_pending_job()
    return view, root, created


def test_selecting_a_track_sets_the_preview_source(tmp_path):
    view, root, _created = _library_with_fake_player(tmp_path)
    assert view.select_path(str(root / "one.wav"))
    assert view.audio_preview.source_path == str(root / "one.wav")
    view.close_db()


def test_hiding_the_tab_and_closing_stop_playback(tmp_path):
    view, root, created = _library_with_fake_player(tmp_path)
    view.select_path(str(root / "one.wav"))
    view.audio_preview.play()
    view.hideEvent(QHideEvent())
    assert not created[0].playing
    view.audio_preview.play()
    view.close_db()
    assert not created[0].playing
