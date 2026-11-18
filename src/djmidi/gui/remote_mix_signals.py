"""Signals between DJs in Mix Together (remote mix, phase 10): one button, or a pad of
your controller, and the message shows big on every other DJ's screen.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.remote_mix import signals


def signal_text(key: str) -> str:
    return QCoreApplication.translate("RemoteSignals", signals.SIGNALS[key])


class SignalToast(QFrame):
    """A signal over every other app (Serato, Traktor in full screen): a small window at
    the top of the screen that never takes the focus, gone after a few seconds."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("remoteSignalToast")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # macOS hides tool windows of a background app
        self.label = QLabel()
        self.label.setObjectName("remoteSignal")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.label)

    def show_text(self, text: str, style: str) -> None:
        self.setStyleSheet(style)
        self.label.setText(text)
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.top() + 24)
        self.show()
        self.raise_()


class SignalsPanel(QFrame):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pads_path: Path | None = None,
        name_of: Callable[[int], str] = lambda dj: f"DJ {dj + 1}",
        beats_to_phrase: Callable[[], int | None] = lambda: None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("remoteSignals")
        self._pads_path = pads_path or user_paths.workspace_dir() / signals.FILE_NAME
        self.pads = signals.SignalPads.load(self._pads_path)
        self._name_of = name_of
        self._beats_to_phrase = beats_to_phrase
        self._clock = clock
        self.board: signals.SignalBoard | None = None
        self._send: Callable[[dict], None] | None = None
        self.learning: str | None = None
        self.shown: signals.Signal | None = None
        self._shown_until = 0.0

        title = QLabel(self.tr("Signals"))
        title.setObjectName("remoteSoundTitle")
        hint = QLabel(self.tr("A nod from afar: it shows big on the other DJs' screens. Learn a pad to send it from your controller."))
        hint.setWordWrap(True)
        self.banner = QLabel()
        self.banner.setObjectName("remoteSignal")
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.buttons: dict[str, QPushButton] = {}
        self.learn_buttons: dict[str, QPushButton] = {}
        self.forget_buttons: dict[str, QPushButton] = {}
        grid = QGridLayout()
        for row, key in enumerate(signals.SIGNALS):
            button = QPushButton(signal_text(key))
            button.clicked.connect(lambda _=False, k=key: self.send(k))
            learn = QPushButton()
            learn.clicked.connect(lambda _=False, k=key: self.learn(k))
            forget = QPushButton("✕")
            forget.setObjectName("chip")
            forget.setToolTip(self.tr("Forget this pad"))
            forget.setAccessibleName(self.tr("Forget this pad"))
            forget.clicked.connect(lambda _=False, k=key: self.forget(k))
            grid.addWidget(button, row, 0)
            grid.addWidget(learn, row, 1)
            grid.addWidget(forget, row, 2)
            self.buttons[key], self.learn_buttons[key], self.forget_buttons[key] = button, learn, forget
        grid.setColumnStretch(0, 1)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.banner)
        layout.addWidget(hint)
        layout.addLayout(grid)
        self.over_apps = QCheckBox(self.tr("Show signals over other apps"))
        self.over_apps.setToolTip(
            self.tr("While you look at your DJ software, a signal shows at the top of the screen for a few seconds")
        )
        self.over_apps.setChecked(True)
        layout.addWidget(self.over_apps)
        self.toast: SignalToast | None = None
        layout.addWidget(self.status_label)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._show_pads()
        self._enable()

    def attach(self, me: int, send: Callable[[dict], None]) -> None:
        if self.board is None or self.board.me != me:
            self.board = signals.SignalBoard(me)
        self._send = send
        self._enable()

    def detach(self) -> None:
        self.board = None
        self._send = None
        self.learning = None
        self._hide_banner()
        self._show_pads()
        self._enable()

    def _enable(self) -> None:
        for button in self.buttons.values():
            button.setEnabled(self.board is not None)

    def send(self, key: str) -> bool:
        if self.board is None or self._send is None:
            return False
        message = self.board.send(key)
        for _ in range(signals.REPEATS):  # a lost packet must not lose the signal
            self._send(message)
        self.status_label.setText(self.tr("Sent: {signal}").format(signal=signal_text(key)))
        return True

    def receive(self, message: dict) -> signals.Signal | None:
        if self.board is None:
            return None
        signal = self.board.receive(message)
        if signal is not None:
            self.shown, self._shown_until = signal, self._clock() + signals.SHOW_S
            self._show_banner()
            self._timer.start()
        return signal

    def _show_banner(self) -> None:
        if self.shown is None:
            return
        text = self.tr("{name}: {signal}").format(name=self._name_of(self.shown.sender), signal=signal_text(self.shown.key))
        beats = self._beats_to_phrase() if self.shown.key in signals.PHRASE_SIGNALS else None
        if beats:
            text += " " + self.tr("(in {count} beats)").format(count=beats)
        self.banner.setText(text)
        self.banner.show()
        if self.over_apps.isChecked() and not self._in_view():
            if self.toast is None:
                self.toast = SignalToast(self)
            self.toast.show_text(text, self._toast_style())
        elif self.toast is not None:
            self.toast.hide()

    def _in_view(self) -> bool:
        """The DJ already sees the banner: this window is in front and the tab is open."""
        window = self.window()
        return self.isVisible() and window is not None and window.isActiveWindow()

    def _toast_style(self) -> str:
        from djmidi.gui import theme

        c = theme.colors()
        return (
            f"QFrame#remoteSignalToast {{ background: {c['panel_bg']}; border: 2px solid {c['accent']}; "
            f"border-radius: 12px; }}"
            f"QLabel#remoteSignal {{ font-size: 26px; font-weight: 700; color: {c['title']}; padding: 12px 20px; "
            f"background: transparent; border: none; }}"
        )

    def _hide_banner(self) -> None:
        self._timer.stop()
        self.shown = None
        self.banner.hide()
        if self.toast is not None:
            self.toast.hide()

    def closeEvent(self, event) -> None:
        if self.toast is not None:
            self.toast.close()
            self.toast.deleteLater()
            self.toast = None
        super().closeEvent(event)

    def _tick(self) -> None:
        if self._clock() >= self._shown_until:
            self._hide_banner()
        else:
            self._show_banner()

    def learn(self, key: str) -> None:
        self.learning = None if self.learning == key else key
        self._show_pads()
        if self.learning is not None:
            self.status_label.setText(self.tr("Press a pad on your controller…"))

    def forget(self, key: str) -> None:
        self.pads.forget(key)
        self._save()
        self._show_pads()

    def feed_midi_event(self, event) -> bool:
        """Learn a pad, or send the signal a learned pad stands for. True when used."""
        if self.learning is not None:
            trigger = signals.pad_from_event(event)
            if trigger is None:
                return False
            key, self.learning = self.learning, None
            self.pads.bind(key, trigger)
            self._save()
            self._show_pads()
            self.status_label.setText(
                self.tr("{pad} now sends “{signal}”.").format(pad=trigger.label(), signal=signal_text(key))
            )
            return True
        key = self.pads.fired(event)
        if key is None:
            return False
        self.send(key)
        return True

    def _save(self) -> None:
        try:
            self.pads.save(self._pads_path)
        except OSError as exc:
            self.status_label.setText(self.tr("Pads not saved: {error}").format(error=exc))

    def _show_pads(self) -> None:
        for key, learn in self.learn_buttons.items():
            pad = self.pads.bindings.get(key)
            if self.learning == key:
                learn.setText(self.tr("Press a pad…"))
            else:
                learn.setText(pad.label() if pad else self.tr("Learn a pad"))
            learn.setToolTip(self.tr("Send this signal from a pad of your controller"))
            self.forget_buttons[key].setVisible(pad is not None)


__all__ = ["SignalsPanel", "signal_text"]
