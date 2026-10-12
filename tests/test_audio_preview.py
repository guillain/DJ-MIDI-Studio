"""Tests for the Music Library tab's audio preview bar (issue #192).

Offscreen CI may have no audio device, so the state logic runs against a
fake player; one test builds the real `QMediaPlayer` without playing.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QHideEvent, QKeyEvent

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


# --- volume, keyboard, auto-advance (issue #210) ---------------------------


class FakeOutput:
    def __init__(self) -> None:
        self.volumes: list[float] = []

    def setVolume(self, volume: float) -> None:
        self.volumes.append(volume)


class FakeOutputPlayer(FakePlayer):
    mediaStatusChanged = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.output = FakeOutput()

    def audioOutput(self) -> FakeOutput:
        return self.output


class FakeSettings:
    def __init__(self, values: dict | None = None) -> None:
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value) -> None:
        self.values[key] = value


def _bar_with_output() -> tuple[AudioPreviewBar, list[FakeOutputPlayer]]:
    created: list[FakeOutputPlayer] = []

    def factory(parent: QObject) -> FakeOutputPlayer:
        created.append(FakeOutputPlayer(parent))
        return created[-1]

    return AudioPreviewBar(player_factory=factory), created


def test_issue_210_pure_helpers():
    assert audio_preview.clamp_volume("55") == 55
    assert audio_preview.clamp_volume(150) == 100
    assert audio_preview.clamp_volume(-3) == 0
    assert audio_preview.clamp_volume(None) == audio_preview.DEFAULT_VOLUME
    assert audio_preview.clamp_volume("loud") == audio_preview.DEFAULT_VOLUME
    assert audio_preview.parse_bool("true") is True
    assert audio_preview.parse_bool("false") is False
    assert audio_preview.parse_bool(1) is True
    assert audio_preview.parse_bool(None) is False
    assert audio_preview.parse_bool("??", default=True) is True
    assert audio_preview.relative_seek_target(5_000, -10_000, 60_000) == 0
    assert audio_preview.relative_seek_target(55_000, 10_000, 60_000) == 60_000
    assert audio_preview.relative_seek_target(20_000, 10_000, 60_000) == 30_000


def test_defaults_without_settings():
    bar, _created = _bar_with_output()
    assert bar.volume() == audio_preview.DEFAULT_VOLUME
    assert not bar.auto_advance


def test_volume_is_applied_to_the_output(tmp_path):
    bar, created = _bar_with_output()
    bar.volume_slider.setValue(40)
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    assert created[0].output.volumes[-1] == pytest.approx(0.40)
    bar.volume_slider.setValue(75)
    assert created[0].output.volumes[-1] == pytest.approx(0.75)


def test_settings_are_loaded_and_saved():
    settings = FakeSettings(
        {audio_preview.VOLUME_SETTINGS_KEY: "30", audio_preview.AUTO_ADVANCE_SETTINGS_KEY: "true"}
    )
    bar, _created = _bar_with_output()
    bar.set_settings(settings)
    assert bar.volume() == 30
    assert bar.auto_advance
    bar.volume_slider.setValue(65)
    bar.auto_advance_check.setChecked(False)
    assert settings.values[audio_preview.VOLUME_SETTINGS_KEY] == 65
    assert settings.values[audio_preview.AUTO_ADVANCE_SETTINGS_KEY] is False


def test_no_settings_means_nothing_is_persisted():
    bar, _created = _bar_with_output()
    bar.set_settings(None)
    bar.volume_slider.setValue(10)  # no crash, nothing to write to
    assert bar.volume() == 10


def test_main_window_in_tests_has_no_preview_settings():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window.music_library_view.audio_preview._settings is None
    finally:
        window.close()


def test_space_toggles_and_arrows_seek(tmp_path):
    bar, created = _bar_with_output()
    assert not bar.handle_key(Qt.Key.Key_Space)  # no track: the table keeps the key
    bar.set_source(str(tmp_path / "a.wav"))
    assert bar.handle_key(Qt.Key.Key_Space)
    player = created[0]
    assert player.playing
    # Arrows only seek once the duration is known.
    assert not bar.handle_key(Qt.Key.Key_Right)
    player.durationChanged.emit(60_000)
    player.positionChanged.emit(25_000)
    assert bar.handle_key(Qt.Key.Key_Right)
    assert player.positions[-1] == 35_000
    assert bar.handle_key(Qt.Key.Key_Left)
    assert player.positions[-1] == 25_000
    player.positionChanged.emit(3_000)
    bar.handle_key(Qt.Key.Key_Left)
    assert player.positions[-1] == 0
    # Modified keys stay with the table (Shift+arrow extends the selection).
    assert not bar.handle_key(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert bar.handle_key(Qt.Key.Key_Space)
    assert not player.playing


@pytest.mark.skipif(not audio_preview.multimedia_available(), reason="QtMultimedia unavailable")
def test_end_of_media_requests_advance_only_when_enabled(tmp_path):
    from PySide6.QtMultimedia import QMediaPlayer

    bar, created = _bar_with_output()
    requests: list[bool] = []
    bar.advanceRequested.connect(lambda: requests.append(True))
    bar.set_source(str(tmp_path / "a.wav"))
    bar.play()
    created[0].mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
    assert requests == []
    bar.auto_advance_check.setChecked(True)
    created[0].mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)
    assert requests == []
    created[0].mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
    assert requests == [True]


def _select_proxy_row(view, proxy_row: int) -> None:
    from PySide6.QtCore import QItemSelectionModel

    view.table.selectionModel().setCurrentIndex(
        view.proxy.index(proxy_row, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )


def test_table_keys_drive_the_preview(tmp_path):
    view, _root, created = _library_with_fake_player(tmp_path)
    _select_proxy_row(view, 0)
    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")
    assert view.eventFilter(view.table, press)
    assert created[0].playing
    view.close_db()


def test_auto_advance_plays_the_next_row(tmp_path):
    view, _root, created = _library_with_fake_player(tmp_path)
    _select_proxy_row(view, 0)
    first = view.audio_preview.source_path
    view.audio_preview.play()
    created[0].stop()  # the track ended
    assert view._advance_preview()
    assert view.audio_preview.source_path not in (None, first)
    assert view.table.selectionModel().currentIndex().row() == 1
    assert created[0].playing
    # Nothing below the last row: stays put.
    assert not view._advance_preview()
    view.close_db()
