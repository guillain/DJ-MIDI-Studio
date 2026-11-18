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
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
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
from djmidi.gui.remote_mix_listen import ListenerPanel
from djmidi.gui.remote_mix_signals import SignalsPanel
from djmidi.gui.remote_mix_tracklist import TracklistPanel
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    ResponsiveRow,
    fit_to_screen,
    keep_wrapped_text_visible,
)
from djmidi.library import history
from djmidi.remote_mix import (
    audio,
    bridge,
    listen,
    next_step,
    probe,
    signals,
    tracklist,
)
from djmidi.remote_mix import demo as demo_mode
from djmidi.remote_mix import settings as remembered

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
        listener_factory: Callable[..., listen.ListenerClient] = listen.ListenerClient,
        ensure_listening: Callable[[], bool] | None = None,
        controls_path: Path | None = None,
        history_dirs: Callable[[], dict[str, Path]] = history.default_history_dirs,
        exports_dir: Path | None = None,
        settings_path: Path | None = None,
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
        self.listen_radio = QRadioButton(self.tr("I listen"))
        self.listen_radio.setToolTip(self.tr("No decks: hear the official mix from the control room"))
        roles.addButton(self.listen_radio)
        role_row = QHBoxLayout()
        role_row.addWidget(self.host_radio)
        role_row.addWidget(self.join_radio)
        role_row.addWidget(self.listen_radio)
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
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        self.name_edit.setPlaceholderText(self.tr("shown on everyone's mixer"))
        self.link_checkbox = QCheckBox(self.tr("Measure Ableton Link too"))
        self.link_checkbox.setChecked(True)
        form = QFormLayout()
        form.addRow(self.tr("Your addresses (give one to the other DJ):"), self.addresses_label)
        form.addRow(self.tr("Host's address:"), self.address_edit)
        form.addRow(self.tr("Port:"), self.port_spin)
        form.addRow(self.tr("Your DJ name:"), self.name_edit)
        self._form = form

        self.start_button = QPushButton(self.tr("Start the test"))
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.toggle)
        self.demo_button = QPushButton(self.tr("Try alone"))
        self.demo_button.setToolTip(
            self.tr("A pretend second DJ on this computer: find everything before the real session")
        )
        self.demo_button.clicked.connect(self.start_demo)
        self.save_button = QPushButton(self.tr("Save the report"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.demo_button)
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
        self._form_widget = QWidget()
        form.setContentsMargins(0, 0, 0, 0)
        self._form_widget.setLayout(form)
        left.addWidget(self._form_widget)
        left.addWidget(self.link_checkbox)
        left.addLayout(buttons)
        left.addWidget(self.status_label)
        self._lights_frame = lights
        left.addWidget(lights)
        left.addWidget(self._build_together())
        # Signals between DJs (phase 10): shown with the tempo panel, once connected.
        self.signals_panel = SignalsPanel(
            self,
            pads_path=None if controls_path is None else controls_path.parent / signals.FILE_NAME,
            name_of=self.sound_panel._dj_name,
            beats_to_phrase=self._beats_to_phrase,
        )
        self.signals_panel.hide()
        left.addWidget(self.signals_panel)
        left.addStretch(1)
        sound_column = self._sound_column = QWidget()
        right = QVBoxLayout(sound_column)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.sound_panel)
        # The shared tracklist (phase 11): shown once in a session, kept after it to copy or save.
        self.tracklist_panel = TracklistPanel(
            self, name_of=self.sound_panel._dj_name, history_dirs=history_dirs, exports_dir=exports_dir
        )
        self.tracklist_panel.hide()
        right.addWidget(self.tracklist_panel)
        right.addStretch(1)
        self.columns = ResponsiveRow(
            [(connect_column, 3), (self.sound_panel.table_widget, 4), (sound_column, 3)], spacing=16
        )

        body = QWidget()
        body.setObjectName("remoteBody")
        layout = QVBoxLayout(body)
        layout.addLayout(header)
        layout.addWidget(intro)
        layout.addWidget(self._build_next_step())
        layout.addWidget(self.columns, 1)
        # A listener (phase 8) has no decks: its own panel instead of the three columns.
        self.listener_panel = ListenerPanel(self, backend=audio_backend, client_factory=listener_factory)
        self.listener_panel.hide()
        layout.addWidget(self.listener_panel, 1)
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
        self.listen_radio.toggled.connect(self._sync_role)
        self.address_edit.textChanged.connect(self._show_next_step)
        self._settings_path = settings_path or user_paths.workspace_dir() / remembered.FILE_NAME
        self._loading_settings = False
        self._load_settings()
        self._sync_role()
        self._show_lights(None)
        self._restyle()
        theme.signals.themeChanged.connect(self._restyle)
        keep_wrapped_text_visible(self)

    def _build_next_step(self) -> QFrame:
        """The golden rule: what to do now, always in view, with the one button that does it."""
        frame = QFrame()
        frame.setObjectName("remoteNextStep")
        self.next_step_frame = frame
        self.next_step_number = QLabel()
        self.next_step_number.setObjectName("remoteStepNumber")
        self.next_step_label = QLabel()
        self.next_step_label.setWordWrap(True)
        self.next_step_button = QPushButton()
        self.next_step_button.clicked.connect(self._do_next_step)
        self.next_step: next_step.Step | None = None
        row = QHBoxLayout(frame)
        row.addWidget(self.next_step_number)
        row.addWidget(self.next_step_label, 1)
        row.addWidget(self.next_step_button)
        return frame

    def _state(self) -> next_step.State:
        role = next_step.LISTEN if self.listen_radio.isChecked() else (
            next_step.HOST if self.host_radio.isChecked() else next_step.JOIN
        )
        session = self.session
        connected = session is not None and session.stats() is not None
        link = connected and self._link is not None and self._link() is not None
        return next_step.State(
            role=role,
            running=session is not None,
            has_address=bool(self.address_edit.text().strip()),
            connected=connected,
            link=link,
            sound=self.sound_panel.running,
        )

    def _show_next_step(self) -> None:
        step = self.next_step = next_step.next_step(self._state())
        self.next_step_frame.setVisible(step is not None)
        if step is None:
            return
        texts = {
            next_step.TYPE_ADDRESS: self.tr("Type the host's address (the other DJ sees theirs in this window), then start."),
            next_step.START: self.tr("Start: the lights test the line between you."),
            next_step.GIVE_ADDRESS: self.tr("Give one of your addresses to the other DJ; they join with it."),
            next_step.WAIT_HOST: self.tr("Calling the host… they must have started too."),
            next_step.LINK: self.tr("Connected. Turn Link on in your DJ software (and tick Measure Ableton Link too)."),
            next_step.SOUND: self.tr("Same tempo. Pick where your master comes from, then start the sound."),
            next_step.MIXING: self.tr("You're mixing together: the mixer, the signals and the tracklist are shared."),
        }
        buttons = {
            "focus_address": self.tr("Type the address"),
            "start": self.tr("Start"),
            "copy_address": self.tr("Copy my address"),
            "start_sound": self.tr("Start the sound"),
        }
        self.next_step_number.setText(self.tr("Step {number} of {total}").format(number=step.number, total=next_step.STEPS))
        self.next_step_label.setText(texts[step.key])
        action = step.action
        self.next_step_button.setVisible(action is not None)
        if action is not None:
            self.next_step_button.setText(buttons[action])

    def _do_next_step(self) -> None:
        action = self.next_step.action if self.next_step is not None else None
        if action == "focus_address":
            self.address_edit.setFocus()
        elif action == "start":
            self.start()
        elif action == "copy_address":
            first = self.addresses_label.text().split(",")[0].strip()
            QGuiApplication.clipboard().setText(first)
            self.next_step_label.setText(self.tr("{address} copied: send it to the other DJ.").format(address=first))
        elif action == "start_sound":
            self.sound_panel.start_button.click()
            self._show_next_step()

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
        return self.sound_panel.feed_midi_event(event) or self.signals_panel.feed_midi_event(event)

    def _beats_to_phrase(self) -> int | None:
        snapshot = self._link() if self._link is not None else None
        return None if snapshot is None else bridge.phrase_position(snapshot.beat).beats_to_phrase

    def _audio_context(self):
        session = self.session
        if session is None or session.peer is None or self._link is None:
            return None
        context = (session.peer[0], self.port_spin.value() + audio.AUDIO_PORT_OFFSET, self._link)
        return (*context, session) if hasattr(session, "peer_ids") else context

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
        self.signals_panel.setVisible(connected)
        self.sound_panel.setVisible(connected or self.sound_panel.running)
        if not connected:
            return
        peer = session.peer[0] if session.peer else "?"
        if not getattr(session, "roster", None):
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
        # With three DJs or more the host keeps the lead (phase 9): no hand-over.
        self.lead_button.setVisible(len(getattr(session, "roster", {}) or {}) <= 2)
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

    @property
    def demo(self) -> bool:
        return isinstance(self.session, demo_mode.DemoSession)

    def _sync_role(self) -> None:
        listening = self.listen_radio.isChecked()
        if listening and self.running:
            self.stop()
        if not listening and self.listener_panel.running:
            self.listener_panel.stop()
        self.listener_panel.setVisible(listening)
        for widget in (self._form_widget, self.link_checkbox, self.start_button, self.demo_button, self.save_button,
                       self.status_label, self._lights_frame, self.sound_panel.table_widget, self._sound_column):
            widget.setVisible(not listening)
        if listening:
            self.together_frame.hide()
            self.sound_panel.hide()
        hosting = self.host_radio.isChecked()
        self._form.setRowVisible(self.addresses_label, hosting)
        self._form.setRowVisible(self.address_edit, not hosting)
        self._show_next_step()

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start_demo(self) -> None:
        """Try alone: a pretend second DJ on this computer (nothing leaves it)."""
        self.host_radio.setChecked(True)
        self.start(demo=True)

    def start(self, demo: bool = False) -> None:
        peer = None
        if demo:
            self._link = (self._link_factory() if self.link_checkbox.isChecked() else None) or demo_mode.DemoClock()
            session = demo_mode.DemoSession(
                port=self.port_spin.value(), name=self.name_edit.text().strip()[:40], link_reader=self._link
            )
            session.start()
            self._started_session(session)
            return
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
                max_peers=probe.MAX_DJS - 1 if peer is None else 1,
                name=self.name_edit.text().strip()[:40],
            )
            session.start()
        except OSError as exc:
            self._close_link()
            self.status_label.setText(self.tr("Could not start: {error}").format(error=exc))
            return
        self._started_session(session)

    def _started_session(self, session) -> None:
        self.save_settings()  # what this DJ typed, kept for the next time
        self.session = session
        self._mix_ticks = 0
        self.tracklist_panel.reset()
        self._started = self._now()
        self.last_report = None
        for widget in (self.host_radio, self.join_radio, self.address_edit, self.port_spin, self.link_checkbox, self.name_edit):
            widget.setEnabled(False)
        self.demo_button.setEnabled(False)
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
        self.signals_panel.detach()
        self.signals_panel.hide()
        self.tracklist_panel.detach()
        self.tracklist_panel.setVisible(self.tracklist_panel.copy_button.isEnabled())
        for widget in (self.host_radio, self.join_radio, self.address_edit, self.port_spin, self.link_checkbox, self.name_edit):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Start the test"))
        self.demo_button.setEnabled(True)
        self._show_next_step()

    def _close_link(self) -> None:
        close = getattr(self._link, "close", None)
        if callable(close):
            close()
        self._link = None

    def _share_mixer(self) -> None:
        """Who is in the room, the other DJs' mixer moves; ours again every second (lost packets)."""
        me, send = getattr(self.session, "my_id", None), getattr(self.session, "send", None)
        if me is not None and callable(send):
            if self.sound_panel.table is None or self.sound_panel.table.me != me:
                self.sound_panel.attach_table(me, send)
            self.signals_panel.attach(me, send)
            self.tracklist_panel.attach(me, send)
            self.tracklist_panel.show()
            self.sound_panel.set_roster(me, dict(getattr(self.session, "roster", {}) or {}))
        inbox = getattr(self.session, "inbox", None)
        while inbox is not None:
            try:
                message = inbox.get_nowait()
            except queue.Empty:
                break
            if message.get("k") == signals.MESSAGE_KIND:
                self.signals_panel.receive(message)
            elif message.get("k") == tracklist.MESSAGE_KIND:
                self.tracklist_panel.receive(message)
            else:
                self.sound_panel.apply_remote(message)
        self._mix_ticks = getattr(self, "_mix_ticks", 0) + 1
        if self._mix_ticks % 4 == 0:
            self.sound_panel.send_snapshot()
        if self._mix_ticks % tracklist.RESEND_EVERY == 0:
            self.tracklist_panel.resend()
            self._tracklist_to_listeners()

    def _tracklist_to_listeners(self) -> None:
        """The control room sends the whole tracklist to its listeners (phase 12)."""
        server, shared = self.sound_panel.listen_server, self.tracklist_panel.list
        if server is None or shared is None:
            return
        for message in tracklist.for_listeners(shared.rows, self.sound_panel._dj_name):
            server.send_message(message)

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
        elif self.demo:
            self.status_label.setText(
                self.tr("Demo: the Demo DJ plays your own sound back a bar late and repeats your talkback. Nothing leaves this computer.")
            )
        else:
            self.status_label.setText(
                self.tr("Connected to {host} for {seconds} s.").format(
                    host=session.peer[0] if session.peer else "?", seconds=round(stats.duration_s)
                )
            )
        self._show_lights(stats)
        self._show_together(session, stats)
        self.save_button.setEnabled(stats is not None)
        self._show_next_step()

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

    # -- remembered between sessions ---------------------------------------

    def _remembered_widgets(self) -> dict[str, QWidget]:
        sound, listener = self.sound_panel, self.listener_panel
        return {
            "name": self.name_edit,
            "address": self.address_edit,
            "port": self.port_spin,
            "link": self.link_checkbox,
            "follow": self.follow_checkbox,
            "input": sound.input_combo,
            "monitor": sound.monitor_combo,
            "program": sound.program_combo,
            "quality": sound.quality_combo,
            "nudge": sound.nudge_spin,
            "stems": sound.stems_checkbox,
            "signals_over_apps": self.signals_panel.over_apps,
            "listen_address": listener.address_edit,
            "listen_port": listener.port_spin,
            "listen_output": listener.output_combo,
        }

    def _load_settings(self) -> None:
        values = remembered.load(self._settings_path)
        self._loading_settings = True
        try:
            radio = {"host": self.host_radio, "join": self.join_radio, "listen": self.listen_radio}.get(values.get("role"))
            if radio is not None:
                radio.setChecked(True)
            for key, widget in self._remembered_widgets().items():
                if key in values:
                    _set_value(widget, values[key])
        finally:
            self._loading_settings = False
        for widget in self._remembered_widgets().values():
            _on_change(widget, self.save_settings)
        for radio in (self.host_radio, self.join_radio, self.listen_radio):
            radio.toggled.connect(self.save_settings)

    def save_settings(self, *_args) -> None:
        if self._loading_settings:
            return
        role = "listen" if self.listen_radio.isChecked() else "host" if self.host_radio.isChecked() else "join"
        values: dict[str, remembered.Value] = {"role": role}
        values.update({key: _value_of(widget) for key, widget in self._remembered_widgets().items()})
        try:
            remembered.save(self._settings_path, values)
        except OSError as exc:
            self.status_label.setText(self.tr("Settings not saved: {error}").format(error=exc))

    def closeEvent(self, event) -> None:
        self.stop()
        self.listener_panel.stop()
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
            QFrame#remoteTracklist {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                      border-radius: 10px; }}
            QFrame#remoteTracklist > QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QFrame#remoteNextStep {{ background: {c["panel_bg"]}; border: 2px solid {c["accent"]}; border-radius: 10px; }}
            QFrame#remoteNextStep QLabel {{ background: transparent; border: none; color: {c["text"]}; font-size: 14px; }}
            QFrame#remoteNextStep QLabel#remoteStepNumber {{ font-weight: 700; color: {c["title"]}; }}
            QFrame#remoteSignals {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                    border-radius: 10px; }}
            QFrame#remoteSignals QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QFrame#remoteSignals QLabel#remoteSignal {{ font-size: 22px; font-weight: 700; color: {c["title"]};
                                    border: 2px solid {c["accent"]}; border-radius: 10px; padding: 10px; }}
            QFrame#remoteSound {{ background: {c["panel_bg"]}; border: 1px solid {c["panel_border"]};
                                  border-radius: 10px; }}
            QFrame#remoteSound QLabel {{ background: transparent; border: none; color: {c["text"]}; }}
            QLabel#remoteSoundTitle {{ font-weight: 600; font-size: 14px; }}
            """
        )


def _value_of(widget: QWidget) -> remembered.Value:
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    data = widget.currentData()  # a QComboBox: device names, codec numbers; None ("nowhere") as ""
    return "" if data is None else data


def _set_value(widget: QWidget, value: remembered.Value) -> None:
    if isinstance(widget, QLineEdit) and isinstance(value, str):
        widget.setText(value)
    elif isinstance(widget, QSpinBox) and isinstance(value, int) and not isinstance(value, bool):
        widget.setValue(value)
    elif isinstance(widget, QCheckBox) and isinstance(value, bool):
        widget.setChecked(value)
    elif isinstance(widget, QComboBox):
        for index in range(widget.count()):
            data = widget.itemData(index)
            if ("" if data is None else data) == value:
                widget.setCurrentIndex(index)  # a device that is gone is simply not chosen
                return


def _on_change(widget: QWidget, slot) -> None:
    if isinstance(widget, QLineEdit):
        widget.editingFinished.connect(slot)
    elif isinstance(widget, QSpinBox):
        widget.valueChanged.connect(slot)
    elif isinstance(widget, QCheckBox):
        widget.toggled.connect(slot)
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(slot)


__all__ = ["RemoteMixDialog", "local_addresses"]
