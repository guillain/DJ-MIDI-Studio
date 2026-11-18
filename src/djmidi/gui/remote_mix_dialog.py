"""Tools → Mix Together: Connection Test… (remote mix, phase 0).

A thin window over ``djmidi.remote_mix.probe``: host or join, one button,
three lights (network, stability, tempo and phase) and a report to save and
send to the other DJ. The session, the Link reader, the address list and the
report folder are injectable for tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.gui import help_texts, theme
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.remote_mix import probe

_LOGGER = logging.getLogger(__name__)

SessionFactory = Callable[..., probe.ProbeSession]
LinkFactory = Callable[[], probe.LinkReader | None]

_COLOURS = {probe.GREEN: "#30a46c", probe.ORANGE: "#f5a524", probe.RED: "#e5484d", probe.UNKNOWN: "#8b8d98"}


def local_addresses() -> list[str]:
    """This computer's IPv4 addresses the other DJ could reach (a VPN such as
    ZeroTier adds its own), loopback and link-local left out."""
    found = []
    for address in QNetworkInterface.allAddresses():
        if address.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol or address.isLoopback():
            continue
        text = address.toString()
        if not text.startswith("169.254."):
            found.append(text)
    return found


def _default_link() -> probe.LinkReader | None:
    try:
        from djmidi.ableton_link import AalinkStateProvider, LinkBackendUnavailable

        provider = AalinkStateProvider()
    except (ImportError, LinkBackendUnavailable) as exc:
        _LOGGER.info("Ableton Link unavailable for the connection test: %s", exc)
        return None
    reader = probe.link_reader_from(provider)
    reader.close = provider.close  # type: ignore[attr-defined]
    return reader


class RemoteMixDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session_factory: SessionFactory = probe.ProbeSession,
        link_factory: LinkFactory = _default_link,
        addresses: Callable[[], list[str]] = local_addresses,
        report_dir: Callable[[], Path] = lambda: user_paths.subfolder(user_paths.LOGS),
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Mix Together: Connection Test"))
        fit_to_screen(self, 560, 470)
        self._session_factory = session_factory
        self._link_factory = link_factory
        self._report_dir = report_dir
        self._now = now
        self.session: probe.ProbeSession | None = None
        self._link: probe.LinkReader | None = None
        self._started: datetime | None = None
        self.last_report: Path | None = None

        headline = QLabel(self.tr("Test the line with the other DJ"))
        headline.setObjectName("remoteHeadline")
        header = QHBoxLayout()
        header.addWidget(headline, 1)
        header.addWidget(help_button(self, *help_texts.REMOTE_MIX), 0, Qt.AlignmentFlag.AlignTop)
        intro = QLabel(
            self.tr(
                "Do this once before mixing together. One of you hosts, the other joins with the host's "
                "address. Turn Link on in both DJ programs, leave the test running a few minutes, then "
                "save the report and send it over."
            )
        )
        intro.setWordWrap(True)

        self.host_radio = QRadioButton(self.tr("I host"))
        self.join_radio = QRadioButton(self.tr("I join"))
        self.host_radio.setChecked(True)
        roles = QButtonGroup(self)
        roles.addButton(self.host_radio)
        roles.addButton(self.join_radio)
        role_row = QHBoxLayout()
        role_row.addWidget(self.host_radio)
        role_row.addWidget(self.join_radio)
        role_row.addStretch(1)

        found = addresses()
        self.addresses_label = QLabel(", ".join(found) if found else self.tr("No network address found"))
        self.addresses_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.addresses_label.setWordWrap(True)
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText(self.tr("e.g. 10.147.17.5"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(probe.DEFAULT_PORT)
        self.link_checkbox = QCheckBox(self.tr("Measure Ableton Link too"))
        self.link_checkbox.setChecked(True)
        form = QFormLayout()
        form.addRow(self.tr("Your addresses (give one to the other DJ):"), self.addresses_label)
        form.addRow(self.tr("Host's address:"), self.address_edit)
        form.addRow(self.tr("Port:"), self.port_spin)
        self._form = form

        self.start_button = QPushButton(self.tr("Start the test"))
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.toggle)
        self.save_button = QPushButton(self.tr("Save the report"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)

        self.status_label = QLabel(self.tr("Not started."))
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("remoteStatus")

        lights = QFrame()
        lights.setObjectName("remoteLights")
        grid = QGridLayout(lights)
        self.lights: dict[str, tuple[QLabel, QLabel]] = {}
        titles = {
            "network": self.tr("Network"),
            "stability": self.tr("Stability"),
            "link": self.tr("Tempo and phase"),
        }
        for row, (key, title) in enumerate(titles.items()):
            dot = QLabel("●")
            dot.setObjectName("remoteDot")
            name = QLabel(title)
            name.setObjectName("remoteLightTitle")
            detail = QLabel(self.tr("not measured yet"))
            detail.setWordWrap(True)
            grid.addWidget(dot, row, 0)
            grid.addWidget(name, row, 1)
            grid.addWidget(detail, row, 2)
            self.lights[key] = (dot, detail)
        grid.setColumnStretch(2, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(intro)
        layout.addLayout(role_row)
        layout.addLayout(form)
        layout.addWidget(self.link_checkbox)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(lights)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self.host_radio.toggled.connect(self._sync_role)
        self._sync_role()
        self._show_lights(None)
        self._restyle()
        theme.signals.themeChanged.connect(self._restyle)
        keep_wrapped_text_visible(self)

    # -- state -------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.session is not None

    def _sync_role(self) -> None:
        hosting = self.host_radio.isChecked()
        self._form.setRowVisible(self.addresses_label, hosting)
        self._form.setRowVisible(self.address_edit, not hosting)

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        peer = None
        if self.join_radio.isChecked():
            host = self.address_edit.text().strip()
            if not host:
                self.status_label.setText(self.tr("Type the host's address first."))
                self.address_edit.setFocus()
                return
            peer = (host, self.port_spin.value())
        self._link = self._link_factory() if self.link_checkbox.isChecked() else None
        try:
            session = self._session_factory(port=self.port_spin.value(), peer=peer, link_reader=self._link)
            session.start()
        except OSError as exc:
            self._close_link()
            self.status_label.setText(self.tr("Could not start: {error}").format(error=exc))
            return
        self.session = session
        self._started = self._now()
        self.last_report = None
        for widget in (self.host_radio, self.join_radio, self.address_edit, self.port_spin, self.link_checkbox):
            widget.setEnabled(False)
        self.start_button.setText(self.tr("Stop the test"))
        self._timer.start()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()
        if self.session is not None:
            self.refresh()
            self.session.stop()
            self._last_stats = self.session.stats()
            self._last_peer = self.session.peer
            self._last_role = "host" if self.host_radio.isChecked() else "join"
        self.session = None
        self._close_link()
        for widget in (self.host_radio, self.join_radio, self.address_edit, self.port_spin, self.link_checkbox):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Start the test"))

    def _close_link(self) -> None:
        close = getattr(self._link, "close", None)
        if callable(close):
            close()
        self._link = None

    def refresh(self) -> None:
        session = self.session
        if session is None:
            return
        stats = session.stats()
        if session.error:
            self.status_label.setText(self.tr("Network error: {error}").format(error=session.error))
        elif stats is None:
            if session.peer is None:
                self.status_label.setText(
                    self.tr("Waiting for the other DJ to join on port {port}…").format(port=session.port)
                )
            else:
                self.status_label.setText(self.tr("Calling {host}… no answer yet.").format(host=session.peer[0]))
        else:
            self.status_label.setText(
                self.tr("Connected to {host} for {seconds} s.").format(
                    host=session.peer[0] if session.peer else "?", seconds=round(stats.duration_s)
                )
            )
        self._show_lights(stats)
        self.save_button.setEnabled(stats is not None)

    def _show_lights(self, stats: probe.ProbeStats | None) -> None:
        verdicts = probe.verdicts(stats)
        details = {key: self.tr("not measured yet") for key in verdicts}
        if stats is not None:
            details["network"] = self.tr("round trip {rtt:.0f} ms, {loss:.1f} % lost").format(
                rtt=stats.rtt_median, loss=stats.loss_pct
            )
            details["stability"] = self.tr("jitter {jitter:.1f} ms").format(jitter=stats.jitter_ms)
            if not stats.local_tempo or not stats.remote_tempo:
                details["link"] = self.tr("turn Link on in both DJ programs (and leave this box ticked)")
            elif verdicts["link"] == probe.RED and abs(stats.local_tempo - stats.remote_tempo) > probe.TEMPO_TOLERANCE:
                details["link"] = self.tr("two tempos ({here:.2f} / {there:.2f} BPM): Link doesn't reach across").format(
                    here=stats.local_tempo, there=stats.remote_tempo
                )
            elif stats.phase_median_ms is not None:
                details["link"] = self.tr("{tempo:.2f} BPM both sides, phase gap {gap:.1f} ms").format(
                    tempo=stats.local_tempo, gap=stats.phase_median_ms
                )
        for key, (dot, detail) in self.lights.items():
            dot.setStyleSheet(f"color: {_COLOURS[verdicts[key]]}; font-size: 16px;")
            dot.setProperty("light", verdicts[key])
            detail.setText(details[key])

    def save_report(self) -> Path | None:
        if self.session is not None:
            stats, peer = self.session.stats(), self.session.peer
            role = "host" if self.host_radio.isChecked() else "join"
        else:
            stats = getattr(self, "_last_stats", None)
            peer = getattr(self, "_last_peer", None)
            role = getattr(self, "_last_role", "host")
        started = self._started or self._now()
        text = probe.report_markdown(
            stats,
            role=role,
            peer=peer[0] if peer else "?",
            started=started,
            translate=translator("RemoteMixReport"),
        )
        folder = self._report_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / probe.report_file_name(started)
        path.write_text(text, encoding="utf-8")
        self.last_report = path
        self.status_label.setText(self.tr("Report saved: {path}").format(path=path))
        return path

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)

    def _restyle(self) -> None:
        c = theme.colors()
        self.setStyleSheet(
            f"""
            QLabel#remoteHeadline {{ font-size: 17px; font-weight: 600; color: {c["title"]}; }}
            QLabel#remoteStatus {{ color: {c["hint_text"]}; }}
            QFrame#remoteLights {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                   border-radius: 10px; }}
            QFrame#remoteLights QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QFrame#remoteLights QLabel#remoteLightTitle {{ font-weight: 600; color: {c["title"]}; }}
            """
        )


__all__ = ["RemoteMixDialog", "local_addresses"]
