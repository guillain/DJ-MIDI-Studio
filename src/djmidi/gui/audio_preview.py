"""Quick audio preview for the Music Library tab (issue #192).

`AudioPreviewBar` is a small transport row — play/pause, stop, a seek
slider, a position/duration label and a "Start at 30%" box — that plays the
track selected in the library table, so a category or key can be checked by
ear without opening the DJ software. Playback goes through
`PySide6.QtMultimedia` (`QMediaPlayer` + `QAudioOutput`).

QtMultimedia is imported defensively: it is a separate Qt module with its
own native backend (FFmpeg/AVFoundation/WMF plugins), and a missing system
library on some Linux setups makes the import fail. When it can't be
loaded, the bar stays visible but disabled, with a tooltip saying why —
never a crash. The player itself is only created on the first Play, so
building the tab (and every test that constructs `MainWindow`) never opens
an audio device. Tests inject a fake through `player_factory`.

Read-only by construction: the bar only ever hands a file path to the
player, it never writes anything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button

try:  # pragma: no cover - exercised by whether the platform ships QtMultimedia
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError as error:  # pragma: no cover
    QAudioOutput = None  # type: ignore[assignment,misc]
    QMediaPlayer = None  # type: ignore[assignment,misc]
    _IMPORT_ERROR: str | None = str(error)
else:
    _IMPORT_ERROR = None

_LOGGER = logging.getLogger(__name__)

#: Where "Start at 30%" jumps to, as a fraction of the track's duration —
#: past most intros, where the groove (and the key) is established.
START_OFFSET_FRACTION = 0.30

UNAVAILABLE_TOOLTIP = "Audio preview unavailable: PySide6's QtMultimedia module could not be loaded."


def multimedia_available() -> bool:
    """Whether QtMultimedia imported, i.e. whether the default player can exist."""
    return QMediaPlayer is not None


def start_position_ms(duration_ms: int, fraction: float = START_OFFSET_FRACTION) -> int:
    """The position to jump to for a start offset; 0 for an unknown duration."""
    if duration_ms <= 0:
        return 0
    return int(duration_ms * min(max(fraction, 0.0), 1.0))


def format_time(ms: int) -> str:
    """`m:ss` (or `h:mm:ss` for a mix over an hour) for a position in ms."""
    seconds = max(ms, 0) // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _default_player_factory(parent: QObject) -> Any:
    """A `QMediaPlayer` wired to the default audio output."""
    player = QMediaPlayer(parent)
    output = QAudioOutput(parent)
    player.setAudioOutput(output)
    # The player doesn't own its output: keep it alive alongside.
    player._dj_audio_output = output  # type: ignore[attr-defined]
    return player


class AudioPreviewBar(QWidget):
    """Play the selected library track; see the module docstring.

    `player_factory(parent)` returns an object with `QMediaPlayer`'s
    interface subset used here: `setSource`, `play`, `pause`, `stop`,
    `setPosition`, `isPlaying`, and the `durationChanged`/`positionChanged`/
    `playbackStateChanged`/`errorOccurred` signals.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        player_factory: Callable[[QObject], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        if player_factory is None and multimedia_available():
            player_factory = _default_player_factory
        self._player_factory = player_factory
        self._player: Any = None
        self._path: str | None = None
        self._duration = 0
        self._pending_offset = False
        self._error: str | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button = QPushButton("■ Stop")
        self.stop_button.clicked.connect(self.stop)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setMinimumWidth(80)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.time_label = QLabel()
        self.offset_check = QCheckBox(f"Start at {round(START_OFFSET_FRACTION * 100)}%")
        self.offset_check.setToolTip("Skip the intro: playback starts 30% into the track.")
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.seek_slider, 1)
        row.addWidget(self.time_label)
        row.addWidget(self.offset_check)
        row.addWidget(help_button(self, *help_texts.LIBRARY_PREVIEW))
        self._tooltips = {
            self.play_button: "Play or pause the selected track.",
            self.stop_button: "Stop and rewind.",
            self.seek_slider: "Drag to move through the track.",
            self.offset_check: self.offset_check.toolTip(),
        }
        self._update_controls()

    # --- state ----------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._player_factory is not None

    @property
    def source_path(self) -> str | None:
        return self._path

    def is_playing(self) -> bool:
        return self._player is not None and bool(self._player.isPlaying())

    def set_source(self, path: str | Path | None) -> None:
        """Preview `path` (None clears). Keeps auditioning if already playing."""
        new_path = str(path) if path is not None else None
        if new_path == self._path:
            return
        was_playing = self.is_playing()
        if self._player is not None:
            self._player.stop()
        self._path = new_path
        self._duration = 0
        self._pending_offset = False
        self._error = None
        self.seek_slider.setRange(0, 0)
        if self._player is not None:
            self._player.setSource(QUrl.fromLocalFile(new_path) if new_path else QUrl())
        if was_playing and new_path:
            self.play()
        self._update_controls()

    # --- transport ------------------------------------------------------

    def _ensure_player(self) -> Any:
        if self._player is None and self._player_factory is not None:
            try:
                player = self._player_factory(self)
            except Exception:
                _LOGGER.exception("Could not create the audio preview player")
                self._player_factory = None
                self._update_controls()
                return None
            player.durationChanged.connect(self._on_duration_changed)
            player.positionChanged.connect(self._on_position_changed)
            player.playbackStateChanged.connect(self._update_controls)
            player.errorOccurred.connect(self._on_error)
            self._player = player
            if self._path:
                player.setSource(QUrl.fromLocalFile(self._path))
        return self._player

    def play(self) -> None:
        if not self._path:
            return
        player = self._ensure_player()
        if player is None:
            return
        if self._duration == 0 and self.offset_check.isChecked():
            # The duration is only known once the media is loaded; apply the
            # offset from `_on_duration_changed`.
            self._pending_offset = True
        player.play()
        self._update_controls()

    def pause(self) -> None:
        if self._player is not None:
            self._player.pause()
        self._update_controls()

    def toggle_play(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        """Stop and rewind; safe to call at any time (tab hidden, app closing)."""
        self._pending_offset = False
        if self._player is not None:
            self._player.stop()
        self._update_controls()

    def seek(self, position_ms: int) -> None:
        if self._player is not None:
            self._player.setPosition(int(position_ms))

    # --- player signals -------------------------------------------------

    def _on_duration_changed(self, duration: int) -> None:
        self._duration = int(duration)
        self.seek_slider.setRange(0, max(self._duration, 0))
        if self._pending_offset and self._duration > 0:
            self._pending_offset = False
            self.seek(start_position_ms(self._duration))
        self._update_time_label(self.seek_slider.value())

    def _on_position_changed(self, position: int) -> None:
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(int(position))
            self._update_time_label(int(position))

    def _on_slider_moved(self, value: int) -> None:
        self._update_time_label(value)

    def _on_slider_released(self) -> None:
        self.seek(self.seek_slider.value())

    def _on_error(self, _error: object = None, message: str = "") -> None:
        self._error = message or "This file could not be played."
        _LOGGER.warning("Audio preview of %s failed: %s", self._path, self._error)
        self._update_controls()

    # --- display --------------------------------------------------------

    def _update_time_label(self, position: int) -> None:
        self.time_label.setToolTip("")
        if not self._path:
            self.time_label.setText("")
            return
        total = format_time(self._duration) if self._duration > 0 else "--:--"
        self.time_label.setText(f"{format_time(position)} / {total}")

    def _update_controls(self, *_args: object) -> None:
        available = self.available
        has_track = available and bool(self._path)
        self.play_button.setEnabled(has_track)
        self.stop_button.setEnabled(has_track)
        self.seek_slider.setEnabled(has_track and self._duration > 0)
        self.offset_check.setEnabled(available)
        self.play_button.setText("❚❚ Pause" if self.is_playing() else "▶ Play")
        for widget, tooltip in self._tooltips.items():
            widget.setToolTip(tooltip if available else UNAVAILABLE_TOOLTIP)
        if not available:
            self.time_label.setText("Preview unavailable")
            self.time_label.setToolTip(UNAVAILABLE_TOOLTIP)
        elif self._error is not None:
            self.time_label.setText("Cannot play")
            self.time_label.setToolTip(self._error)
        else:
            self._update_time_label(self.seek_slider.value())
