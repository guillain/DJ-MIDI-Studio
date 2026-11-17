"""The startup check window: one card per device, each thing to finish on
its own line with the one button that finishes it. Read-only: buttons ask
MainWindow to open the matching tool (`actionRequested`); "Dismiss" hides
an item for good (`dismissed`)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts, theme
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.startup_check import (
    BLOCKING,
    CHECK,
    IAC,
    LEARN,
    LEDS,
    MACROS,
    OK,
    SCENE,
    TODO,
    StartupItem,
    StartupReport,
)

_GLYPHS = {BLOCKING: "●", TODO: "●", OK: "✓"}


class StartupCheckDialog(QDialog):
    actionRequested = Signal(object)  # StartupItem
    dismissed = Signal(str)  # item id
    recheckRequested = Signal()

    def __init__(
        self,
        report: StartupReport,
        dismissed: set[str] | None = None,
        show_at_startup: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Startup check"))
        self.setObjectName("startupCheck")
        fit_to_screen(self, 720, 560)
        self._dismissed = set(dismissed or ())
        self._action_labels = {
            LEARN: self.tr("Teach it"),
            CHECK: self.tr("Check it"),
            LEDS: self.tr("Probe its lights"),
            SCENE: self.tr("Create a scene"),
            MACROS: self.tr("Edit the macros"),
            IAC: self.tr("Open Audio MIDI Setup"),
        }
        box = QVBoxLayout(self)
        header = QHBoxLayout()
        self.headline = QLabel()
        self.headline.setObjectName("startupHeadline")
        self.headline.setWordWrap(True)
        header.addWidget(self.headline, 1)
        header.addWidget(help_button(self, *help_texts.STARTUP_CHECK), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)
        self.devices_label = QLabel()
        self.devices_label.setWordWrap(True)
        self.devices_label.setObjectName("startupDevices")
        box.addWidget(self.devices_label)

        self._cards = QWidget()
        self._cards_layout = QVBoxLayout(self._cards)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._cards)
        box.addWidget(scroll, 1)

        footer = QHBoxLayout()
        self.show_at_startup = QCheckBox(self.tr("Show at startup when something needs you"))
        self.show_at_startup.setChecked(show_at_startup)
        footer.addWidget(self.show_at_startup, 1)
        self.recheck_button = QPushButton(self.tr("Check again"))
        self.recheck_button.setToolTip(self.tr("Look at the connected devices again, after plugging one in."))
        self.recheck_button.clicked.connect(self.recheckRequested)
        footer.addWidget(self.recheck_button)
        close = QPushButton(self.tr("Close"))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        box.addLayout(footer)

        self._restyle()
        theme.signals.themeChanged.connect(self._restyle)
        self.set_report(report)
        keep_wrapped_text_visible(self)

    # -- content ------------------------------------------------------------

    def set_report(self, report: StartupReport) -> None:
        self.report = report
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0).widget()
            if child is not None:  # hidden now, deleted later: a card's own button may be the caller
                child.hide()
                child.deleteLater()
        visible = [item for item in report.items if item.id not in self._dismissed]
        blocking = sum(1 for item in visible if item.status == BLOCKING)
        todo = sum(1 for item in visible if item.status == TODO)
        if blocking:
            self.headline.setText(
                self.tr("{blocking} thing(s) won't work right now, {todo} to finish").format(
                    blocking=blocking, todo=todo
                )
            )
            self.headline.setProperty("status", BLOCKING)
        elif todo:
            self.headline.setText(self.tr("Almost ready: {todo} thing(s) to finish").format(todo=todo))
            self.headline.setProperty("status", TODO)
        else:
            self.headline.setText(self.tr("All set: everything plugged in is ready"))
            self.headline.setProperty("status", OK)
        self.headline.style().unpolish(self.headline)
        self.headline.style().polish(self.headline)
        self.devices_label.setText(
            self.tr("Plugged in: {devices}").format(devices=", ".join(report.devices))
            if report.devices
            else self.tr("No MIDI device plugged in.")
        )
        groups: dict[str, list[StartupItem]] = {}
        for item in visible:
            groups.setdefault(item.device, []).append(item)
        for device, items in groups.items():
            self._cards_layout.addWidget(self._card(device, items))
        self._cards_layout.addStretch(1)

    def _card(self, device: str, items: list[StartupItem]) -> QFrame:
        card = QFrame()
        card.setObjectName("startupCard")
        # The worst status colours the card's edge: the state reads at a glance.
        statuses = {item.status for item in items}
        card.setProperty("status", BLOCKING if BLOCKING in statuses else TODO if TODO in statuses else OK)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel(device)
        title.setObjectName("startupCardTitle")
        layout.addWidget(title)
        translate = translator("StartupCheck")
        for item in items:
            row = QHBoxLayout()
            dot = QLabel(_GLYPHS[item.status])
            dot.setObjectName("startupDot")
            dot.setProperty("status", item.status)
            dot.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(dot)
            text = QLabel(item.text(translate))
            text.setWordWrap(True)
            row.addWidget(text, 1)
            if item.action is not None:
                button = QPushButton(self._action_labels[item.action])
                button.setProperty("chip", True)
                button.clicked.connect(lambda _checked=False, it=item: self.actionRequested.emit(it))
                row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
            if item.status != OK:
                hide = QPushButton("✕")
                hide.setObjectName("startupDismiss")
                hide.setCursor(Qt.CursorShape.PointingHandCursor)
                hide.setToolTip(self.tr("Dismiss: don't show this again"))
                hide.setAccessibleName(self.tr("Dismiss: don't show this again"))
                hide.clicked.connect(lambda _checked=False, it=item: self.dismiss(it.id))
                row.addWidget(hide, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(row)
        return card

    def dismiss(self, item_id: str) -> None:
        self._dismissed.add(item_id)
        self.dismissed.emit(item_id)
        self.set_report(self.report)

    def card_titles(self) -> list[str]:
        return [
            label.text()
            for label in self._cards.findChildren(QLabel, "startupCardTitle")
            if label.parentWidget().isVisibleTo(self._cards)
        ]

    # -- look -----------------------------------------------------------------

    def _restyle(self) -> None:
        c = theme.colors()
        self.setStyleSheet(
            f"""
            QLabel#startupHeadline {{ font-size: 17px; font-weight: 600; color: {c["title"]}; }}
            QLabel#startupDevices {{ color: {c["hint_text"]}; }}
            QFrame#startupCard {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                  border-radius: 10px; }}
            QFrame#startupCard[status="blocking"] {{ border-left: 4px solid #e5484d; }}
            QFrame#startupCard[status="todo"] {{ border-left: 4px solid #f5a524; }}
            QFrame#startupCard[status="ok"] {{ border-left: 4px solid #30a46c; }}
            QFrame#startupCard QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QFrame#startupCard QLabel#startupCardTitle {{ font-weight: 600; font-size: 14px; color: {c["title"]}; }}
            QPushButton#startupDismiss {{ background: transparent; border: none; color: {c["hint_text"]};
                                          min-width: 22px; max-width: 22px; padding: 2px; font-size: 13px; }}
            QPushButton#startupDismiss:hover {{ color: {c["text"]}; }}
            QFrame#startupCard QLabel#startupDot {{ font-size: 15px; }}
            QFrame#startupCard QLabel#startupDot[status="blocking"] {{ color: #e5484d; }}
            QFrame#startupCard QLabel#startupDot[status="todo"] {{ color: #f5a524; }}
            QFrame#startupCard QLabel#startupDot[status="ok"] {{ color: #30a46c; }}
            """
        )


__all__ = ["StartupCheckDialog"]
