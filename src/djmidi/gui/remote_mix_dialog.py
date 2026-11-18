"""Tools → Mix Together… (remote mix, phases 0 and 1).

A thin window over ``djmidi.remote_mix.probe`` and ``bridge``: host or join,
one button, three lights (network, stability, tempo and phase), a report to
save and send to the other DJ and, once connected, the tempo bridge: one DJ
leads, the other's Link follows, **Take the lead** hands it over, and both
see the same bar count to the next phrase. The session, the Link reader, the address list and the
report folder are injectable for tests.
"""

from __future__ import annotations

import logging
import queue
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
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.gui import help_texts, theme
from djmidi.gui.help_button import help_button
from djmidi.gui.remote_mix_audio import AudioBackend, RemoteAudioPanel
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    ResponsiveRow,
    fit_to_screen,
    keep_wrapped_text_visible,
)
from djmidi.remote_mix import audio, bridge, probe, table

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
    reader.control = provider  # type: ignore[attr-defined]
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
        audio_backend: AudioBackend | None = None,
        audio_link_factory: Callable[..., audio.AudioLink] = audio.AudioLink,
        ensure_listening: Callable[[], bool] | None = None,
        controls_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Mix Together"))
        fit_to_screen(self, 560, 470)
        self._session_factory = session_factory
        self._link_factory = link_factory
        self._report_dir = report_dir
        self._now = now
        self.session: probe.ProbeSession | None = None
        self._link: probe.LinkReader | None = None
        self._started: datetime | None = None
        self.last_report: Path | None = None

        headline = QLabel(self.tr("Mix together from two places"))
        headline.setObjectName("remoteHeadline")
        header = QHBoxLayout()
        header.addWidget(headline, 1)
        header.addWidget(help_button(self, *help_texts.REMOTE_MIX), 0, Qt.AlignmentFlag.AlignTop)
        intro = QLabel(
            self.tr(
                "One of you hosts, the other joins with the host's address. Turn Link on in both DJ "
                "programs and start: the lights test the line, then the host's tempo and beat lead and the "
                "other side's Link follows. Save the report to send the measures over."
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

        self.sound_panel = RemoteAudioPanel(
            self._audio_context,
            self,
            backend=audio_backend,
            link_factory=audio_link_factory,
            ensure_listening=ensure_listening,
            controls_path=controls_path,
        )
        self.sound_panel.hide()

        # Three columns: connecting on the left, the mixer at the centre, the sound
        # on the right (shown once connected); one under the other when narrow.
        connect_column = QWidget()
        left = QVBoxLayout(connect_column)
        left.setContentsMargins(0, 0, 0, 0)
        left.addLayout(role_row)
        left.addLayout(form)
        left.addWidget(self.link_checkbox)
        left.addLayout(buttons)
        left.addWidget(self.status_label)
        left.addWidget(lights)
        left.addWidget(self._build_together())
        left.addStretch(1)
        sound_column = QWidget()
        right = QVBoxLayout(sound_column)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.sound_panel)
        right.addStretch(1)
        self.columns = ResponsiveRow(
            [(connect_column, 3), (self.sound_panel.table_widget, 4), (sound_column, 3)], spacing=16
        )

        body = QWidget()
        body.setObjectName("remoteBody")
        layout = QVBoxLayout(body)
        layout.addLayout(header)
        layout.addWidget(intro)
        layout.addWidget(self.columns, 1)
        layout.addStretch(1)
        # The sound panel makes the window tall: everything scrolls on a small screen.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self.host_radio.toggled.connect(self._sync_role)
        self._sync_role()
        self._show_lights(None)
        self._restyle()
        theme.signals.themeChanged.connect(self._restyle)
        keep_wrapped_text_visible(self)

    def _build_together(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("remoteTogether")
        self.together_frame = frame
        self.follow_checkbox = QCheckBox(self.tr("Keep our tempos together"))
        self.follow_checkbox.setChecked(True)
        self.follow_checkbox.setToolTip(
            self.tr("The DJ who leads sets tempo and beat; the other side's Link follows, and so does its DJ software")
        )
        self.follow_checkbox.toggled.connect(self._on_follow_toggled)
        self.lead_label = QLabel()
        self.lead_label.setWordWrap(True)
        self.lead_button = QPushButton(self.tr("Take the lead"))
        self.lead_button.setToolTip(self.tr("From now on your tempo and beat lead; the other DJ follows"))
        self.lead_button.clicked.connect(self.take_lead)
        self.phrase_label = QLabel()
        self.phrase_label.setObjectName("remotePhrase")
        row = QHBoxLayout()
        row.addWidget(self.lead_label, 1)
        row.addWidget(self.lead_button)
        box = QVBoxLayout(frame)
        box.addWidget(self.follow_checkbox)
        box.addLayout(row)
        box.addWidget(self.phrase_label)
        frame.hide()
        return frame

    def feed_midi_event(self, event) -> bool:
        """A live MIDI event for the mixer (Learn, or a fader that drives it)."""
        return self.sound_panel.feed_midi_event(event)

    def _audio_context(self):
        session = self.session
        if session is None or session.peer is None or self._link is None:
            return None
        return session.peer[0], self.port_spin.value() + audio.AUDIO_PORT_OFFSET, self._link

    def take_lead(self) -> None:
        if self.session is not None:
            self.session.take_lead()
            self.refresh()

    def _on_follow_toggled(self, on: bool) -> None:
        if self.session is not None:
            self.session.follow = on
            self.refresh()

    def _show_together(self, session: probe.ProbeSession, stats: probe.ProbeStats | None) -> None:
        connected = stats is not None and self._link is not None
        self.together_frame.setVisible(connected)
        self.sound_panel.setVisible(connected or self.sound_panel.running)
        if not connected:
            return
        peer = session.peer[0] if session.peer else "?"
        self.sound_panel.set_peer_name(peer)
        if session.leading:
            text = self.tr("You lead the tempo: {host} follows.").format(host=peer)
        elif not self.follow_checkbox.isChecked():
            text = self.tr("{host} leads, but you're not following: tick the box to lock on.").format(host=peer)
        elif session.remote_leading:
            text = self.tr("{host} leads the tempo: your Link follows.").format(host=peer)
        else:
            text = self.tr("Nobody leads: one of you clicks Take the lead.")
        if session.follow_error:
            text += " " + self.tr("Link refused a change: {error}").format(error=session.follow_error)
        self.lead_label.setText(text)
        self.lead_button.setEnabled(not session.leading)
        snapshot = self._link() if self._link is not None else None
        if snapshot is None:
            self.phrase_label.clear()
            return
        position = bridge.phrase_position(snapshot.beat)
        if position.beats_to_phrase == 0:
            self.phrase_label.setText(self.tr("Bar {bar} · beat {beat} — new phrase!").format(
                bar=position.bar, beat=position.beat))
        else:
            self.phrase_label.setText(self.tr("Bar {bar} · beat {beat} — next phrase in {count}").format(
                bar=position.bar, beat=position.beat, count=position.beats_to_phrase))

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
            session = self._session_factory(
                port=self.port_spin.value(),
                peer=peer,
                link_reader=self._link,
                link_control=getattr(self._link, "control", None),
                follow=self.follow_checkbox.isChecked(),
            )
            session.start()
        except OSError as exc:
            self._close_link()
            self.status_label.setText(self.tr("Could not start: {error}").format(error=exc))
            return
        self.session = session
        send = getattr(session, "send", None)
        if callable(send):
            self.sound_panel.attach_table(table.HOST if peer is None else table.GUEST, send)
        self._mix_ticks = 0
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
        self.sound_panel.stop()
        self.sound_panel.detach_table()
        self.sound_panel.hide()
        self.session = None
        self._close_link()
        self.together_frame.hide()
        for widget in (self.host_radio, self.join_radio, self.address_edit, self.port_spin, self.link_checkbox):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Start the test"))

    def _close_link(self) -> None:
        close = getattr(self._link, "close", None)
        if callable(close):
            close()
        self._link = None

    def _share_mixer(self) -> None:
        """Apply the other DJ's mixer moves; resend ours every second (lost packets)."""
        inbox = getattr(self.session, "inbox", None)
        while inbox is not None:
            try:
                message = inbox.get_nowait()
            except queue.Empty:
                break
            self.sound_panel.apply_remote(message)
        self._mix_ticks = getattr(self, "_mix_ticks", 0) + 1
        if self._mix_ticks % 4 == 0:
            self.sound_panel.send_snapshot()

    def refresh(self) -> None:
        if self.session is not None:
            self._share_mixer()
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
        self._show_together(session, stats)
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
            QFrame#mixStrip {{ border: 1px solid {c["panel_border"]}; border-radius: 10px; background: {c["panel_bg"]}; }}
            QFrame#mixStrip QLabel {{ background: transparent; border: none; }}
            QLabel#mixStripName {{ font-size: 15px; font-weight: 600; color: {c["title"]}; }}
            QFrame#remoteLights {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                   border-radius: 10px; }}
            QFrame#remoteLights QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QFrame#remoteLights QLabel#remoteLightTitle {{ font-weight: 600; color: {c["title"]}; }}
            QFrame#remoteTogether {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                     border-radius: 10px; }}
            QFrame#remoteTogether QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QLabel#remotePhrase {{ font-size: 18px; font-weight: 600; }}
            QFrame#remoteSound {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                  border-radius: 10px; }}
            QFrame#remoteSound QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QLabel#remoteSoundTitle {{ font-weight: 600; font-size: 14px; }}
            """
        )


__all__ = ["RemoteMixDialog", "local_addresses"]
