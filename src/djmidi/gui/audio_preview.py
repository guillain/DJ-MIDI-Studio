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

Issue #210 added a volume slider and an "Auto-advance" box (off by
default), both remembered through an injected settings object
(`set_settings`, `QSettings`-like `value`/`setValue`; `MainWindow` passes
its `_layout_settings()`, which is `None` in tests, so tests never touch a
real user's settings), plus keyboard control routed from the library table
through `handle_key`: Space plays/pauses, Left/Right seek by
`SEEK_STEP_MS`. When auto-advance is on and a track plays to its end, the
bar emits `advanceRequested`; the tab picks the next row and calls `play`.

Read-only by construction: the bar only ever hands a file path to the
player, it never writes anything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QT_TRANSLATE_NOOP, QObject, Qt, QUrl, Signal
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

#: Left/Right arrow seek step (issue #210).
SEEK_STEP_MS = 10_000

#: Volume slider range is 0..100 percent; the first-run default.
DEFAULT_VOLUME = 80

#: Settings keys (issue #210); stored in `MainWindow`'s `QSettings`.
VOLUME_SETTINGS_KEY = "library/preview_volume"
AUTO_ADVANCE_SETTINGS_KEY = "library/preview_auto_advance"

UNAVAILABLE_TOOLTIP = QT_TRANSLATE_NOOP(
    "AudioPreviewBar", "Audio preview unavailable: PySide6's QtMultimedia module could not be loaded."
)


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


def clamp_volume(value: object, default: int = DEFAULT_VOLUME) -> int:
    """A stored volume (int, or the string `QSettings` may give back) as 0..100."""
    try:
        volume = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return min(max(volume, 0), 100)


def parse_bool(value: object, default: bool = False) -> bool:
    """A stored flag: `QSettings` returns "true"/"false" strings on some platforms."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return default
    if isinstance(value, int):
        return bool(value)
    return default


def relative_seek_target(position_ms: int, delta_ms: int, duration_ms: int) -> int:
    """`position + delta`, clamped to the track (0..duration)."""
    target = max(int(position_ms) + int(delta_ms), 0)
    if duration_ms > 0:
        target = min(target, int(duration_ms))
    return target


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
    `playbackStateChanged`/`errorOccurred` signals. Optional: `audioOutput()`
    (whose `setVolume(float)` the volume slider drives) and the
    `mediaStatusChanged` signal (end of track, for auto-advance).
    """

    #: Auto-advance is on and the current track played to its end.
    advanceRequested = Signal()

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
        self._settings: Any = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.play_button = QPushButton(self.tr("▶ Play"))
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button = QPushButton(self.tr("■ Stop"))
        self.stop_button.clicked.connect(self.stop)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setMinimumWidth(80)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.time_label = QLabel()
        percent = round(START_OFFSET_FRACTION * 100)
        self.offset_check = QCheckBox(self.tr("Start at {percent}%").format(percent=percent))
        self.offset_check.setToolTip(
            self.tr("Skip the intro: playback starts {percent}% into the track.").format(percent=percent)
        )
        self.volume_label = QLabel(self.tr("Vol"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(DEFAULT_VOLUME)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.auto_advance_check = QCheckBox(self.tr("Auto-advance"))
        self.auto_advance_check.setChecked(False)
        self.auto_advance_check.toggled.connect(self._on_auto_advance_toggled)
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.seek_slider, 1)
        row.addWidget(self.time_label)
        row.addWidget(self.volume_label)
        row.addWidget(self.volume_slider)
        row.addWidget(self.offset_check)
        row.addWidget(self.auto_advance_check)
        row.addWidget(help_button(self, *help_texts.LIBRARY_PREVIEW))
        self._tooltips = {
            self.play_button: self.tr("Play or pause the selected track (Space in the table)."),
            self.stop_button: self.tr("Stop and rewind."),
            self.seek_slider: self.tr("Drag to move through the track (Left/Right in the table: 10 s)."),
            self.offset_check: self.offset_check.toolTip(),
            self.volume_slider: self.tr("Preview volume, remembered for next time."),
            self.auto_advance_check: self.tr("When a track ends, play the next one in the table."),
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

    @property
    def auto_advance(self) -> bool:
        return self.auto_advance_check.isChecked()

    def volume(self) -> int:
        return self.volume_slider.value()

    def set_settings(self, settings: Any) -> None:
        """Remember volume/auto-advance in `settings` (QSettings-like; None = don't).

        Loads the stored values right away. Tests leave this unset (or pass
        a plain fake), so a real user's settings are never read or written.
        """
        self._settings = None  # don't write back while loading
        if settings is not None:
            self.volume_slider.setValue(clamp_volume(settings.value(VOLUME_SETTINGS_KEY, DEFAULT_VOLUME)))
            self.auto_advance_check.setChecked(parse_bool(settings.value(AUTO_ADVANCE_SETTINGS_KEY, False)))
        self._settings = settings

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
            status_signal = getattr(player, "mediaStatusChanged", None)
            if status_signal is not None:
                status_signal.connect(self._on_media_status_changed)
            self._player = player
            self._apply_volume()
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

    def seek_relative(self, delta_ms: int) -> None:
        """Move by `delta_ms` from the current position, clamped to the track."""
        if self._player is None or self._duration <= 0:
            return
        target = relative_seek_target(self.seek_slider.value(), delta_ms, self._duration)
        self.seek(target)
        self.seek_slider.setValue(target)
        self._update_time_label(target)

    def handle_key(self, key: int, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> bool:
        """Space = play/pause, Left/Right = seek; True when the key was used.

        Only plain (unmodified) keys, and only with a track to act on, so
        Shift+arrows and friends keep their usual table meaning.
        """
        if modifiers & ~Qt.KeyboardModifier.KeypadModifier:
            return False
        if not (self.available and self._path):
            return False
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            return True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self._duration > 0:
            self.seek_relative(SEEK_STEP_MS if key == Qt.Key.Key_Right else -SEEK_STEP_MS)
            return True
        return False

    def _on_volume_changed(self, value: int) -> None:
        self._apply_volume()
        if self._settings is not None:
            self._settings.setValue(VOLUME_SETTINGS_KEY, int(value))

    def _on_auto_advance_toggled(self, checked: bool) -> None:
        if self._settings is not None:
            self._settings.setValue(AUTO_ADVANCE_SETTINGS_KEY, bool(checked))

    def _apply_volume(self) -> None:
        output_getter = getattr(self._player, "audioOutput", None)
        output = output_getter() if callable(output_getter) else None
        if output is not None and hasattr(output, "setVolume"):
            output.setVolume(self.volume_slider.value() / 100.0)

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

    def _on_media_status_changed(self, status: object) -> None:
        if QMediaPlayer is None or status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self.auto_advance:
            self.advanceRequested.emit()

    def _on_slider_moved(self, value: int) -> None:
        self._update_time_label(value)

    def _on_slider_released(self) -> None:
        self.seek(self.seek_slider.value())

    def _on_error(self, _error: object = None, message: str = "") -> None:
        self._error = message or self.tr("This file could not be played.")
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
        self.volume_slider.setEnabled(available)
        self.auto_advance_check.setEnabled(available)
        self.play_button.setText(self.tr("❚❚ Pause") if self.is_playing() else self.tr("▶ Play"))
        for widget, tooltip in self._tooltips.items():
            widget.setToolTip(tooltip if available else self.tr(UNAVAILABLE_TOOLTIP))
        if not available:
            self.time_label.setText(self.tr("Preview unavailable"))
            self.time_label.setToolTip(self.tr(UNAVAILABLE_TOOLTIP))
        elif self._error is not None:
            self.time_label.setText(self.tr("Cannot play"))
            self.time_label.setToolTip(self._error)
        else:
            self._update_time_label(self.seek_slider.value())
