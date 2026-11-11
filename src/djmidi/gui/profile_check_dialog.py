"""File → Controller Profile → Verify Profile with the Controller… (issues #364, #451).

Three tabs over one controller library (`atelier.library`):

- **Check**: press what is framed on the photo; pick the categories, say
  which DJ software is running (a controller may send other messages while
  a software drives it), resume only what isn't checked or only what to
  redo. Every verdict is kept (`atelier.captures`).
- **Lights**: the app lights one LED at a time and you say what lit; a
  light show replays them. Answers are LED data (`atelier.led_data`), the
  only way an LED counts as verified (a button's LED often answers another
  note than the button sends).
- **Audit**: every control, documented / verified / mismatch / never tested,
  per software, with its LED; copy or save it.

Thin: the logic is ``gui/profile_check.py`` and ``atelier/``. The dialog
opens no MIDI input: the main window passes ``ensure_listening`` (starts the
Live Monitor, like MIDI Learn) and routes every live event to
:meth:`feed_event` while the dialog is open. LEDs go out through ``sender``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.atelier import captures as captures_mod
from djmidi.atelier import library as library_mod
from djmidi.atelier.features import features_for
from djmidi.atelier.led_data import LedRecord, save_led_record
from djmidi.gui.control_photo import ASKED, BAD, GOOD, ControlPhoto
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import PROFILE_CHECK
from djmidi.gui.profile_check import (
    ALL,
    MISMATCH,
    NOT_CHECKED,
    ODD,
    OK,
    SKIPPED,
    TO_REDO,
    ProfileCheck,
    check_sections,
    press_from_event,
    report_issue_url,
    report_text,
    trigger_text,
)
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_tab_titles_whole,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.midi_io import send_midi_message
from djmidi.update_check import current_version

_translate = translator("ProfileCheck")
_translate_captures = translator("ControllerCaptures")
_translate_library = translator("ControllerLibrary")
_MARKS = {OK: "✓", MISMATCH: "✗", SKIPPED: "–", ODD: "?"}
LONG_PRESS_MS = 3000
LIGHT_SHOW_STEP_MS = 350
SECTION_COLUMNS = 4


def _port_key(port: str) -> str:
    return " ".join(port.split()).casefold()


class ProfileCheckDialog(QDialog):
    # A capture or a light was recorded for this controller: the Atelier and
    # the Controller Emulators re-read its library.
    libraryChanged = Signal(str)

    def __init__(
        self,
        controllers: Sequence[str],
        ports: Sequence[str] = (),
        parent=None,
        ensure_listening: Callable[[], bool] | None = None,
        initial: str | None = None,
        open_url: Callable[[str], object] | None = None,
        reports_dir: str | Path = "",
        output_ports: Sequence[str] = (),
        judge_delay_ms: int = 0,
        sender: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Verify a controller profile"))
        self._ensure_listening = ensure_listening
        self._open_url = open_url or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self._reports_dir = str(reports_dir)
        self._judge_delay_ms = judge_delay_ms
        self._sender = sender or send_midi_message
        self.check: ProfileCheck | None = None
        self._pending: list = []
        self._judge_timer = QTimer(self, singleShot=True, timeout=self._judge_pending)

        self.controller_combo = QComboBox()
        self.controller_combo.addItems(list(controllers))
        if initial:
            self.controller_combo.setCurrentText(initial)
        self.controller_combo.currentTextChanged.connect(self._controller_changed)

        self.tabs = QTabWidget()
        self.tabs.addTab(_scrolled(self._build_check_tab(ports)), self.tr("Check"))
        self.tabs.addTab(_scrolled(self._build_lights_tab(output_ports)), self.tr("Lights"))
        self.tabs.addTab(self._build_audit_tab(), self.tr("Audit"))
        self.tabs.currentChanged.connect(lambda index: index == 2 and self.refresh_audit())

        top = QFormLayout()
        top.addRow(self.tr("Controller"), self.controller_combo)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *PROFILE_CHECK))
        bottom.addStretch(1)
        bottom.addWidget(close_button)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        layout.addLayout(bottom)
        self._controller_changed(self.controller_combo.currentText())
        self._refresh()
        keep_tab_titles_whole(self.tabs)
        fit_to_screen(self, 760, 720)
        keep_wrapped_text_visible(self)

    # --- building ---------------------------------------------------------------

    def _build_check_tab(self, ports: Sequence[str]) -> QWidget:
        page = QWidget()
        intro = QLabel(
            self.tr(
                "Press what is framed on the photo: the app checks that your controller sends what its "
                "profile says. Skip what your unit doesn't have. Keep your DJ software as you use it: "
                "some controllers answer differently when it drives them."
            )
        )
        intro.setWordWrap(True)
        self.port_combo = QComboBox()
        self.port_combo.addItem(self.tr("Any input"), "")
        for port in ports:
            self.port_combo.addItem(port, port)
        self.software_combo = QComboBox()
        for key, label in captures_mod.SOFTWARE_CHOICES:
            self.software_combo.addItem(_translate_captures(label), key)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem(self.tr("Every control"), ALL)
        self.scope_combo.addItem(self.tr("Only what isn't checked yet"), NOT_CHECKED)
        self.scope_combo.addItem(self.tr("Only mismatches and odd ones"), TO_REDO)
        self.sections_box = QWidget()
        self.sections_box.setToolTip(self.tr("The categories to check: untick the ones to leave out"))
        self._sections_grid = QGridLayout(self.sections_box)
        self._sections_grid.setContentsMargins(0, 0, 0, 0)
        self.section_checks: dict[str, QCheckBox] = {}
        form = QFormLayout()
        form.addRow(self.tr("Listen on"), self.port_combo)
        form.addRow(self.tr("DJ software running"), self.software_combo)
        form.addRow(self.tr("Ask"), self.scope_combo)
        form.addRow(self.tr("Categories"), self.sections_box)

        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.clicked.connect(self.start)
        self.skip_button = QPushButton(self.tr("Skip (not on my unit)"))
        self.skip_button.clicked.connect(self.skip)
        self.back_button = QPushButton(self.tr("Back"))
        self.back_button.clicked.connect(self.back)
        self.odd_button = QPushButton(self.tr("That was odd"))
        self.odd_button.setToolTip(self.tr("Flags the last answer as odd, to look at it again later"))
        self.odd_button.clicked.connect(self.mark_odd)
        step_row = QHBoxLayout()
        for button in (self.start_button, self.skip_button, self.back_button, self.odd_button):
            step_row.addWidget(button)
        step_row.addStretch(1)

        self.prompt = QLabel(self.tr("Click Start, then press the controls one by one."))
        self.prompt.setWordWrap(True)
        self.prompt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = self.prompt.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        self.prompt.setFont(font)
        self.state_label = QLabel("")
        self.state_label.setWordWrap(True)
        self.state_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.photo = ControlPhoto()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress = QLabel("")
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress)
        self.results = QListWidget()
        usable_minimum(self.results, 300, 90)

        self.copy_button = QPushButton(self.tr("Copy report"))
        self.copy_button.clicked.connect(self.copy_report)
        self.save_button = QPushButton(self.tr("Save report…"))
        self.save_button.clicked.connect(self.save_report)
        self.submit_button = QPushButton(self.tr("Submit to the project…"))
        self.submit_button.setToolTip(
            self.tr("Opens a pre-filled GitHub issue with the report; nothing is sent until you submit it there")
        )
        self.submit_button.clicked.connect(self.submit_report)
        report_row = QHBoxLayout()
        for button in (self.copy_button, self.save_button, self.submit_button):
            report_row.addWidget(button)
        report_row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addLayout(step_row)
        layout.addWidget(self.prompt)
        layout.addWidget(self.state_label)
        layout.addWidget(self.photo, 2)
        layout.addLayout(progress_row)
        layout.addWidget(self.results, 1)
        layout.addLayout(report_row)
        return page

    def _build_lights_tab(self, output_ports: Sequence[str]) -> QWidget:
        page = QWidget()
        intro = QLabel(
            self.tr(
                "The app lights one LED at a time: say what lit. That is the only way an LED counts as "
                "verified, because a button's light often answers another message than the button sends. "
                "Then play the light show and check that every framed control lights in turn."
            )
        )
        intro.setWordWrap(True)
        self.output_combo = QComboBox()
        self.output_combo.addItems(list(output_ports))
        self.light_section_combo = QComboBox()
        self.light_section_combo.currentIndexChanged.connect(self._reset_lights)
        self.upper_decks_box = QCheckBox(self.tr("Decks 3 and 4 too"))
        self.upper_decks_box.setToolTip(
            self.tr("Decks 3 and 4 usually light the same buttons as decks 1 and 2, once switched to them")
        )
        self.upper_decks_box.toggled.connect(self._reset_lights)
        form = QFormLayout()
        form.addRow(self.tr("Send to"), self.output_combo)
        form.addRow(self.tr("Category"), self.light_section_combo)
        form.addRow("", self.upper_decks_box)
        self.light_prompt = QLabel(self.tr("Click Light the next one."))
        self.light_prompt.setWordWrap(True)
        font = self.light_prompt.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.light_prompt.setFont(font)
        self.light_photo = ControlPhoto()
        self.light_next_button = QPushButton(self.tr("Light the next one"))
        self.light_next_button.clicked.connect(self.light_next)
        self.lit_here_button = QPushButton(self.tr("✓ It lit there"))
        self.lit_here_button.setToolTip(self.tr("The framed control lit"))
        self.lit_here_button.clicked.connect(self.lit_here)
        self.nothing_lit_button = QPushButton(self.tr("✗ Nothing lit"))
        self.nothing_lit_button.setToolTip(self.tr("No light came on"))
        self.nothing_lit_button.clicked.connect(self.nothing_lit)
        self.lit_other_combo = QComboBox()
        self.lit_other_combo.setToolTip(self.tr("The control that lit instead"))
        self.lit_other_button = QPushButton(self.tr("Another one lit"))
        self.lit_other_button.clicked.connect(self.lit_other)
        answer_row = QHBoxLayout()
        for widget in (self.light_next_button, self.lit_here_button, self.nothing_lit_button):
            answer_row.addWidget(widget)
        answer_row.addStretch(1)
        other_row = QHBoxLayout()
        other_row.addWidget(self.lit_other_combo, 1)
        other_row.addWidget(self.lit_other_button)
        self.show_button = QPushButton(self.tr("▶ Play the light show"))
        self.show_button.setToolTip(self.tr("Lights every LED of the category in turn"))
        self.show_button.clicked.connect(self.play_light_show)
        self.show_yes_button = QPushButton(self.tr("Each one lit"))
        self.show_yes_button.clicked.connect(lambda: self._light_show_answer(True))
        self.show_no_button = QPushButton(self.tr("Some didn't"))
        self.show_no_button.clicked.connect(lambda: self._light_show_answer(False))
        show_row = QHBoxLayout()
        for button in (self.show_button, self.show_yes_button, self.show_no_button):
            show_row.addWidget(button)
        show_row.addStretch(1)
        self._light_features: list = []
        self._light_index = -1
        self._show_timer = QTimer(self, timeout=self._light_show_step)
        self._show_index = -1

        layout = QVBoxLayout(page)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.light_prompt)
        layout.addWidget(self.light_photo, 1)
        layout.addLayout(answer_row)
        layout.addLayout(other_row)
        layout.addLayout(show_row)
        return page

    def _build_audit_tab(self) -> QWidget:
        page = QWidget()
        self.audit_summary = QLabel("")
        self.audit_summary.setWordWrap(True)
        self.audit_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.audit_table = QTableWidget(0, 5)
        self.audit_table.setHorizontalHeaderLabels(
            [self.tr("Control"), self.tr("Category"), self.tr("Status"), self.tr("Captured with"), self.tr("LEDs verified")]
        )
        header = self.audit_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.audit_table.verticalHeader().setVisible(False)
        self.audit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        usable_minimum(self.audit_table, 300, 120)
        copy_button = QPushButton(self.tr("Copy audit"))
        copy_button.clicked.connect(self.copy_audit)
        save_button = QPushButton(self.tr("Save audit…"))
        save_button.clicked.connect(self.save_audit)
        row = QHBoxLayout()
        row.addWidget(copy_button)
        row.addWidget(save_button)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(self.audit_summary)
        layout.addWidget(self.audit_table, 1)
        layout.addLayout(row)
        return page

    # --- controller and categories ---------------------------------------------------

    @property
    def controller(self) -> str:
        return self.controller_combo.currentText()

    def _controller_changed(self, controller: str) -> None:
        if controller not in catalog.CONTROLLER_NAMES:
            return
        for box in self.section_checks.values():
            self._sections_grid.removeWidget(box)
            box.deleteLater()
        self.section_checks = {}
        self.light_section_combo.blockSignals(True)
        self.light_section_combo.clear()
        self.light_section_combo.addItem(self.tr("All categories"), "")
        for index, section in enumerate(check_sections(controller)):
            box = QCheckBox(section)
            box.setChecked(True)
            self._sections_grid.addWidget(box, index // SECTION_COLUMNS, index % SECTION_COLUMNS)
            self.section_checks[section] = box
            self.light_section_combo.addItem(section, section)
        self.light_section_combo.blockSignals(False)
        self.photo.set_controller(controller)
        self.light_photo.set_controller(controller)
        self.photo.clear()
        self.lit_other_combo.clear()
        for feature in features_for(controller):
            self.lit_other_combo.addItem(feature.label, feature.id)
        self._reset_lights()

    def selected_sections(self) -> set[str]:
        return {section for section, box in self.section_checks.items() if box.isChecked()}

    @property
    def software(self) -> str:
        return self.software_combo.currentData() or captures_mod.NO_SOFTWARE

    # --- the check ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.check is not None and not self.check.done

    def start(self) -> bool:
        if self._ensure_listening is not None and not self._ensure_listening():
            self.status.setText(self.tr("No MIDI input is open: connect a controller, or pick one in Live Monitor."))
            return False
        controller = self.controller
        if controller not in catalog.CONTROLLER_NAMES:
            return False
        only = None
        scope = self.scope_combo.currentData()
        if scope != ALL:
            checked = captures_mod.checked_items(captures_mod.load_captures(controller), self.software)
            if scope == NOT_CHECKED:
                only = {key for key in _all_keys(controller) if key not in checked}
            else:
                only = {key for key, status in checked.items() if status in (MISMATCH, ODD)}
        self.check = ProfileCheck.start(controller, self.selected_sections(), only)
        self._pending = []
        self.status.setText("" if self.check.items else self.tr("Nothing to ask: every control here is done."))
        self._refresh()
        return True

    def feed_event(self, event) -> bool:
        """Every live event while the dialog is open; True when the check
        consumed it (a press from the chosen input)."""
        if not self.running:
            return False
        wanted = self.port_combo.currentData()
        if wanted and _port_key(wanted) != _port_key(event.port):
            return False
        trigger = press_from_event(event)
        if trigger is None:
            return False
        self._show_state(trigger)
        if self.check.ignores(trigger):
            return True  # a held SHIFT: wait for the control itself
        self._pending.append(trigger)
        if self._judge_delay_ms <= 0:
            self._judge_pending()
        elif not self._judge_timer.isActive():
            item = self.check.current
            self._judge_timer.start(LONG_PRESS_MS if item is not None and item.long_press else self._judge_delay_ms)
        return True

    def judge_now(self) -> None:
        """Judges the presses of the current attempt without waiting."""
        self._judge_timer.stop()
        self._judge_pending()

    def _judge_pending(self) -> None:
        presses, self._pending = self._pending, []
        if self.check is None:
            return
        item = self.check.current
        result = self.check.judge(presses)
        if result is None or item is None:
            return
        self._save_verdict(item, result.status, result.got, presses)
        if result.status == MISMATCH:
            self.photo.recolour(BAD)
            self.status.setText(result.detail(_translate))
        else:
            self.photo.recolour(GOOD)
            self.status.setText(self.tr("✓ Well done: {trigger}").format(trigger=trigger_text(result.got)))
        if self._judge_delay_ms:
            QTimer.singleShot(350, self._refresh)  # let the green / red frame show a moment
        else:
            self._refresh()

    def _save_verdict(self, item, status: str, got, presses) -> None:
        feature = _feature_for(self.controller, got)
        captures_mod.record_capture(
            self.controller,
            captures_mod.CaptureRecord(
                item=item.key,
                status=status,
                got=got,
                presses=tuple(presses),
                software=self.software,
                day=captures_mod.today(),
                deck=feature.deck if feature else None,
                bank=(feature.bank or "") if feature else "",
            ),
        )
        self.libraryChanged.emit(self.controller)

    def _show_state(self, trigger) -> None:
        feature = _feature_for(self.controller, trigger)
        if feature is None:
            self.state_label.setText(self.tr("Heard {trigger} (not in the profile)").format(trigger=trigger_text(trigger)))
            return
        parts = [self.tr("Deck {deck}").format(deck=feature.deck)] if feature.deck else []
        if feature.bank:
            parts.append(feature.bank)
        parts.append(feature.name)
        self.state_label.setText(self.tr("Heard: {what}").format(what=" · ".join(parts)))

    def skip(self) -> None:
        if self.running:
            item = self.check.current
            self.check.skip()
            self._save_verdict(item, SKIPPED, None, ())
            self._refresh()

    def back(self) -> None:
        if self.check is not None:
            self.check.back()
            self._refresh()

    def mark_odd(self) -> None:
        if self.check is None or not self.check.mark_odd():
            return
        index = self.check.index - 1
        result = self.check.results[index]
        self._save_verdict(self.check.items[index], ODD, result.got, (result.got,) if result.got else ())
        self.status.setText(self.tr("Flagged as odd: it will be asked again with Only mismatches and odd ones."))
        self._refresh()

    def _refresh(self) -> None:
        check = self.check
        self.skip_button.setEnabled(self.running)
        self.back_button.setEnabled(check is not None and check.index > 0)
        self.odd_button.setEnabled(check is not None and check.index > 0)
        has_results = check is not None and bool(check.results)
        for button in (self.copy_button, self.save_button, self.submit_button):
            button.setEnabled(has_results)
        self.start_button.setText(self.tr("Restart") if check is not None else self.tr("Start"))
        self.results.clear()
        if check is None:
            self.progress.setText("")
            self.progress_bar.setValue(0)
            return
        for index, result in sorted(check.results.items()):
            item = check.items[index]
            detail = result.detail(_translate)
            self.results.addItem(f"{_MARKS[result.status]} {item.title}" + (f" — {detail}" if detail else ""))
        self.results.scrollToBottom()
        counts = check.counts()
        self.progress_bar.setMaximum(max(1, len(check.items)))
        self.progress_bar.setValue(len(check.results))
        self.progress.setText(
            self.tr("{done}/{total} · {ok} ok · {bad} mismatch").format(
                done=len(check.results), total=len(check.items), ok=counts[OK], bad=counts[MISMATCH]
            )
        )
        current = check.current
        if current is not None:
            self.prompt.setText(current.prompt(_translate) + f"  ({current.section})")
            if not self.photo.frame(current.names, ASKED):
                self.state_label.setText(self.tr("This one isn't marked on the photo: find it by its name."))
        else:
            self.photo.clear()
            if counts[MISMATCH] or counts[ODD]:
                self.prompt.setText(self.tr("Done! A few answers differ from the profile: see the list and the Audit tab."))
            else:
                self.prompt.setText(self.tr("Done, everything matches. Bravo!"))

    # --- lights -------------------------------------------------------------------

    def _reset_lights(self) -> None:
        self._light_off()
        section = self.light_section_combo.currentData() or ""
        controller = self.controller
        features = features_for(controller) if controller in catalog.CONTROLLER_NAMES else ()
        self._light_features = light_candidates(
            [feature for feature in features if not section or feature.section == section],
            upper_decks=self.upper_decks_box.isChecked(),
        )
        self._light_index = -1
        self._show_timer.stop()
        self._update_light_buttons(asking=False)
        self.light_prompt.setText(
            self.tr("{count} lights to check. Click Light the next one.").format(count=len(self._light_features))
        )

    def _update_light_buttons(self, asking: bool) -> None:
        for widget in (self.lit_here_button, self.nothing_lit_button, self.lit_other_button, self.lit_other_combo):
            widget.setEnabled(asking)
        self.light_next_button.setEnabled(bool(self._light_features))
        self.show_button.setEnabled(bool(self._light_features))
        self.show_yes_button.setEnabled(False)
        self.show_no_button.setEnabled(False)

    def _send(self, channel: int, note: int, value: int) -> bool:
        port = self.output_combo.currentText().strip()
        if not port:
            self.status.setText(self.tr("Pick the controller's output port first."))
            return False
        try:
            self._sender(
                output_port_name=port, event_type="Note On", channel_1_based=channel, data1=note, data2=value
            )
        except Exception as exc:  # noqa: BLE001 - a light must never crash the dialog
            self.status.setText(self.tr("Could not send: {error}").format(error=exc))
            return False
        return True

    def _light_off(self) -> None:
        if 0 <= self._light_index < len(self._light_features):
            led = self._light_features[self._light_index].led
            self._send(led.channel, led.note, led.off_value)

    def light_next(self) -> bool:
        self._light_off()
        if self._light_index + 1 >= len(self._light_features):
            self._light_index = -1
            self.light_photo.clear()
            self.light_prompt.setText(self.tr("All lights asked. Play the light show to check them together."))
            self._update_light_buttons(asking=False)
            return False
        self._light_index += 1
        feature = self._light_features[self._light_index]
        if not self._send(feature.led.channel, feature.led.note, feature.led.on_value):
            self._light_index -= 1
            return False
        self.light_photo.frame((feature.name,), ASKED)
        self.light_prompt.setText(
            self.tr("{done}/{total} · Is the framed control lit: {name}?").format(
                done=self._light_index + 1, total=len(self._light_features), name=feature.label
            )
        )
        self._update_light_buttons(asking=True)
        index = self.lit_other_combo.findData(feature.id)
        if index >= 0:
            self.lit_other_combo.setCurrentIndex(index)
        return True

    def _record_light(self, feature_id: str) -> None:
        sent = self._light_features[self._light_index].led
        save_led_record(
            self.controller,
            LedRecord(
                feature_id,
                sent.channel,
                sent.note,
                sent.on_value,
                sent.off_value,
                source=f"light check {captures_mod.today()}",
            ),
        )
        self.libraryChanged.emit(self.controller)

    def lit_here(self) -> None:
        if self._light_index >= 0:
            self._record_light(self._light_features[self._light_index].id)
            self.light_photo.recolour(GOOD)
            self.status.setText(self.tr("✓ Light recorded."))
            self.light_next()

    def lit_other(self) -> None:
        if self._light_index >= 0 and self.lit_other_combo.currentData():
            self._record_light(self.lit_other_combo.currentData())
            self.status.setText(
                self.tr("Recorded: this light belongs to {name}.").format(name=self.lit_other_combo.currentText())
            )
            self.light_next()

    def nothing_lit(self) -> None:
        if self._light_index >= 0:
            self.light_photo.recolour(BAD)
            self.status.setText(self.tr("Noted: nothing lit for {name}.").format(name=self._light_features[self._light_index].label))
            self.light_next()

    def play_light_show(self) -> None:
        self._light_off()
        self._light_index = -1
        self._update_light_buttons(asking=False)
        self._show_index = -1
        self.light_prompt.setText(self.tr("Watch the controller: each framed control should light in turn."))
        self._show_timer.start(LIGHT_SHOW_STEP_MS)

    def _light_show_step(self) -> None:
        if 0 <= self._show_index < len(self._light_features):
            led = self._light_features[self._show_index].led
            self._send(led.channel, led.note, led.off_value)
        self._show_index += 1
        if self._show_index >= len(self._light_features):
            self._show_timer.stop()
            self.light_photo.clear()
            self.light_prompt.setText(self.tr("Did each framed control light in turn?"))
            self.show_yes_button.setEnabled(True)
            self.show_no_button.setEnabled(True)
            return
        feature = self._light_features[self._show_index]
        self.light_photo.frame((feature.name,), ASKED)
        if not self._send(feature.led.channel, feature.led.note, feature.led.on_value):
            self._show_timer.stop()

    def _light_show_answer(self, every_one: bool) -> None:
        self.show_yes_button.setEnabled(False)
        self.show_no_button.setEnabled(False)
        self.light_prompt.setText(
            self.tr("Bravo, the lights are right!")
            if every_one
            else self.tr("Check the wrong ones one by one with Light the next one.")
        )

    # --- audit ------------------------------------------------------------------

    def refresh_audit(self) -> list:
        controller = self.controller
        if controller not in catalog.CONTROLLER_NAMES:
            return []
        rows = library_mod.audit_controls(controller)
        counts = library_mod.audit_counts(rows)
        self.audit_summary.setText(
            self.tr(
                "{total} controls · {verified} verified · {mismatch} to look at · {untested} never tested · "
                "{leds} with a verified LED"
            ).format(
                total=counts["total"],
                verified=counts[library_mod.VERIFIED],
                mismatch=counts[library_mod.MISMATCH] + counts[library_mod.ODD],
                untested=counts[library_mod.UNTESTED],
                leds=counts["led-verified"],
            )
        )
        softwares = dict(captures_mod.SOFTWARE_CHOICES)
        colours = {library_mod.VERIFIED: GOOD, library_mod.MISMATCH: BAD, library_mod.ODD: ASKED}
        self.audit_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            status = _translate_library(library_mod.STATUS_LABELS[row.status])
            if row.got is not None:
                status += f" ({trigger_text(row.got)})"
            captured = ", ".join(
                f"{_translate_captures(softwares.get(software, software))}: "
                f"{_translate_library(library_mod.STATUS_LABELS[verdict])}"
                for software, verdict in row.per_software
            )
            values = (row.title, row.section, status, captured, f"{row.leds_verified}/{row.leds}" if row.leds else "–")
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 2 and row.status in colours:
                    cell.setForeground(QColor(colours[row.status]))
                self.audit_table.setItem(index, column, cell)
        return rows

    def audit(self) -> str:
        if self.controller not in catalog.CONTROLLER_NAMES:
            return ""
        return library_mod.audit_text(self.controller, app_version=current_version())

    def copy_audit(self) -> None:
        QGuiApplication.clipboard().setText(self.audit())
        self.status.setText(self.tr("Audit copied to the clipboard."))

    def save_audit(self, path: str | None = None) -> None:
        if path is None:
            name = f"controller-audit-{self.controller}.md"
            path, _ = QFileDialog.getSaveFileName(
                self, self.tr("Save audit"), str(Path(self._reports_dir) / name), self.tr("Markdown (*.md)")
            )
        if path:
            Path(path).write_text(self.audit() + "\n", encoding="utf-8")
            self.status.setText(self.tr("Audit saved to {path}").format(path=path))

    # --- the report -------------------------------------------------------------

    def report(self) -> str:
        if self.check is None:
            return ""
        return report_text(
            self.check,
            current_version(),
            self.port_combo.currentData() or "",
            software=dict(captures_mod.SOFTWARE_CHOICES).get(self.software, self.software),
        )

    def copy_report(self) -> None:
        QGuiApplication.clipboard().setText(self.report())
        self.status.setText(self.tr("Report copied to the clipboard."))

    def save_report(self, path: str | None = None) -> None:
        if path is None:
            name = f"profile-check-{self.check.controller if self.check else 'controller'}.md"
            path, _ = QFileDialog.getSaveFileName(
                self, self.tr("Save report"), str(Path(self._reports_dir) / name), self.tr("Markdown (*.md)")
            )
        if path:
            Path(path).write_text(self.report() + "\n", encoding="utf-8")
            self.status.setText(self.tr("Report saved to {path}").format(path=path))

    def submit_report(self) -> str:
        if self.check is None:
            return ""
        body = self.report()
        QGuiApplication.clipboard().setText(body)
        url, inlined = report_issue_url(self.check, body)
        self._open_url(url)
        self.status.setText(
            self.tr("Issue opened in your browser.")
            if inlined
            else self.tr("Issue opened in your browser: paste the report (already copied) into it.")
        )
        return url

    def done(self, result: int) -> None:
        self._show_timer.stop()
        self._light_off()
        super().done(result)


def light_candidates(features, upper_decks: bool = False) -> list:
    """The LEDs worth asking about: one per address, plain layer only (a
    SHIFT variant lights the same lamp), the first pad bank only (the pads
    are the same lamps in every mode), decks 3 and 4 only when asked (they
    are layers on the decks 1 and 2 buttons)."""
    first_bank: dict[str, str] = {}
    seen: set[tuple[int, int]] = set()
    chosen = []
    for feature in features:
        if feature.led is None or feature.shift:
            continue
        if feature.deck is not None and feature.deck > 2 and not upper_decks:
            continue
        if feature.bank is not None:
            bank = first_bank.setdefault(feature.section, feature.bank)
            if feature.bank != bank:
                continue
        address = (feature.led.channel, feature.led.note)
        if address in seen:
            continue
        seen.add(address)
        chosen.append(feature)
    return chosen


def _scrolled(page: QWidget) -> QScrollArea:
    """A tab that scrolls instead of squeezing on a small screen (issue #19)."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(page)
    return area


def _all_keys(controller: str) -> set[str]:
    from djmidi.gui.profile_check import check_items

    return {item.key for item in check_items(controller)}


def _feature_for(controller: str, trigger):
    if trigger is None or controller not in catalog.CONTROLLER_NAMES:
        return None
    channel, kind, data1 = trigger
    return next(
        (
            feature
            for feature in features_for(controller)
            if feature.input.kind == kind and str(feature.input.channel) == channel and str(feature.input.number) == data1
        ),
        None,
    )
