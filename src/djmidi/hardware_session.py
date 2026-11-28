"""Guided hardware session (issue #426).

Everything left in the backlog that needs the maintainer's real controllers or
DJ software (issue #356, the Atelier's LED probe, the freeze fix) as one
checklist: each :class:`Check` says what to do, optionally captures the MIDI
the controller sends while it runs, and records a pass / fail / skip result
with a note. The session is saved as JSON in the workspace's Exports folder and
turned into a Markdown report to paste into the matching issue.

Qt-free: the dialog (``gui/hardware_session_dialog.py``) feeds it live
:class:`~djmidi.midi_io.MidiEvent`s and shows what it returns.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

_LOGGER = logging.getLogger(__name__)

FORMAT = "djmidi-hardware-session/1"
SESSION_FILE_NAME = "hardware-session.json"
MAX_CAPTURED = 200

TODO = "todo"
PASS = "pass"
FAIL = "fail"
SKIP = "skip"
STATUSES = (TODO, PASS, FAIL, SKIP)

STATUS_LABELS = {
    TODO: QT_TRANSLATE_NOOP("HardwareSession", "to do"),
    PASS: QT_TRANSLATE_NOOP("HardwareSession", "pass"),
    FAIL: QT_TRANSLATE_NOOP("HardwareSession", "fail"),
    SKIP: QT_TRANSLATE_NOOP("HardwareSession", "skipped"),
}


@dataclass(frozen=True)
class Check:
    """One thing to try on the hardware.

    ``compare`` names, for a capture check, the note / CC numbers each source
    claims the controller sends (``{"catalog / official PDF": (16, 17)}``):
    :func:`verdict` says which one the capture agrees with.
    """

    id: str
    title: str
    steps: str
    issue: str
    controller: str = ""
    capture: bool = False
    compare: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    # The app's tool this check is done in (one of TOOLS), "" for none: the
    # window offers a button that opens it.
    tool: str = ""


# Tools a check can open (MainWindow.open_test_tool), with their button text.
TOOL_PROFILE_CHECK = "profile-check"
TOOL_SERATO_LEARN = "serato-learn"
TOOL_RECORD_SET = "record-set"
TOOL_ANALYSE_SET = "analyse-set"
TOOL_ATELIER = "atelier"
TOOL_MACROS = "macros"
TOOL_STARTUP_CHECK = "startup-check"
TOOLS = {
    TOOL_PROFILE_CHECK: QT_TRANSLATE_NOOP("HardwareSession", "Open Check a Controller"),
    TOOL_SERATO_LEARN: QT_TRANSLATE_NOOP("HardwareSession", "Open Serato MIDI Learn"),
    TOOL_RECORD_SET: QT_TRANSLATE_NOOP("HardwareSession", "Record a live set"),
    TOOL_ANALYSE_SET: QT_TRANSLATE_NOOP("HardwareSession", "Analyse a set"),
    TOOL_ATELIER: QT_TRANSLATE_NOOP("HardwareSession", "Open the Studio tab"),
    TOOL_MACROS: QT_TRANSLATE_NOOP("HardwareSession", "Open the macros"),
    TOOL_STARTUP_CHECK: QT_TRANSLATE_NOOP("HardwareSession", "Open the Startup Check"),
}


CHECKS: tuple[Check, ...] = (
    Check(
        "ddj-xp2-loop-notes",
        QT_TRANSLATE_NOOP("HardwareSession", "DDJ-XP2: 1/2X and 2X notes"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Click Start capture, press 1/2X then 2X on deck 1 (plain, without SHIFT), then Stop capture. "
            "Keep Serato running: the controller then sends 18 / 19 (rekordbox's bundled mapping and this "
            "app's profile); with no DJ software it sends the official MIDI Message List's 16 / 17.",
        ),
        "#356",
        controller="DDJ-XP2",
        capture=True,
        compare={
            QT_TRANSLATE_NOOP("HardwareSession", "the official PDF"): (16, 17),
            QT_TRANSLATE_NOOP(
                "HardwareSession", "rekordbox's bundled mapping and this app's profile"
            ): (18, 19),
        },
    ),
    Check(
        "cmd-micro-jog",
        QT_TRANSLATE_NOOP("HardwareSession", "CMD Micro: jog wheel messages"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Click Start capture, turn the left jog a little clockwise, then counter-clockwise, then do the "
            "same with the right jog, and Stop capture. The capture shows which Control Change numbers and "
            "values the jogs send, which the app needs to turn them on screen.",
        ),
        "#356",
        controller="Behringer CMD Micro",
        capture=True,
    ),
    Check(
        "cmd-studio-4a-jog",
        QT_TRANSLATE_NOOP("HardwareSession", "CMD Studio 4a: jogs and pitch faders"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Click Start capture, turn the deck 1 jog a little both ways, then move the deck 1 pitch fader "
            "from end to end, then Stop capture, and write in the note which control sent what. Your Traktor "
            "export binds one pitch bend per deck as an absolute fader, not as a jog: the capture shows "
            "whether the jog or the pitch fader sends it (Pitch Bend lines, 0 to 16383).",
        ),
        "#356",
        controller="Behringer CMD Studio 4a",
        capture=True,
    ),
    Check(
        "atelier-led-probe",
        QT_TRANSLATE_NOOP("HardwareSession", "Atelier: probe the LEDs"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "In the Atelier tab, pick a button of each controller, click Probe this LED…, send its value and "
            "watch the button. Save what lights up. Note any button whose LED doesn't answer on its own note.",
        ),
        "#413",
        tool=TOOL_ATELIER,
    ),
    Check(
        "pioneer-colours",
        QT_TRANSLATE_NOOP("HardwareSession", "Pioneer pad colours"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "In the LED probe, send a few values (1, 8, 16, 24, 32, 40, 48, 56) to a DDJ-XP2 or XDJ-XZ pad "
            "and write down the colour each one shows. The colour table the project has for Pioneer pads "
            "has no official source yet.",
        ),
        "#413",
        tool=TOOL_ATELIER,
    ),
    Check(
        "live-bursts",
        QT_TRANSLATE_NOOP("HardwareSession", "No freeze during a live session"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "With Serato or Traktor running and the Live Monitor open, play for ten minutes: jogs, pads, "
            "faders. Note whether the window ever stopped responding. Then send the log (Help → Report a "
            "Problem…): it now names the port that sends large MIDI bursts.",
        ),
        "#356",
        tool=TOOL_RECORD_SET,
    ),
    Check(
        "serato-learn",
        QT_TRANSLATE_NOOP("HardwareSession", "Serato: MIDI-learn the CUE button"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Play, Sync and the hot cues already have Serato's names (learned over the IAC bus). Cue is still "
            "missing: open Serato MIDI Learn, pick the Deck 1 · CUE step, click Send, then find and click the "
            "deck's CUE in Serato before the countdown ends. Save the MIDI preset and attach it to the issue.",
        ),
        "#194",
        tool=TOOL_SERATO_LEARN,
    ),
    Check(
        "traktor-import",
        QT_TRANSLATE_NOOP(
            "HardwareSession", "Traktor: import a playlist exported by this app"
        ),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "In Traktor, import Exports/djmidi-import-test.nml from the app's workspace (Import Playlist). "
            "Note whether the playlist DJMIDI import test appears with its five tracks.",
        ),
        "#356",
    ),
    Check(
        "traktor-learn-sync-hotcue",
        QT_TRANSLATE_NOOP("HardwareSession", "Traktor: learn Sync and Hotcue 1"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "As for the Play one: in Traktor's Controller Manager, start from the empty Generic MIDI device, "
            "add one In command for Sync on deck A, learn it from the controller's SYNC and export. Then do "
            "the same for Hotcue 1. Attach the two .tsi files: they give Traktor's command numbers the "
            ".tsi writer needs.",
        ),
        "#233",
    ),
    Check(
        "xp2-pad-lights",
        QT_TRANSLATE_NOOP("HardwareSession", "DDJ-XP2: pad lights with Serato"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Serato open, a track on deck 1, pads in HOT CUE mode; watch the pad, not the screen. a) Press an "
            "empty pad (it sets a hot cue). b) Press it again. c) Hold SHIFT and press it (it deletes the hot "
            "cue). d) Close Serato and press two or three pads. Write what the light did each time.",
        ),
        "#451",
        controller="DDJ-XP2",
    ),
    Check(
        "xp2-serato-spy",
        QT_TRANSLATE_NOOP("HardwareSession", "DDJ-XP2: what Serato sends to the lights"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Serato sends the pad lights straight to the controller, so this app can't see them; MIDI Monitor "
            "can. Open Serato, then MIDI Monitor, tick the spy on output to DDJ-XP2, Clear, and go through "
            "each PAD MODE of deck 1 with and without SHIFT; set two hot cues and delete them; start and stop "
            "a sample. Copy the list as plain text into Exports/serato-to-xp2.txt.",
        ),
        "#451",
        controller="DDJ-XP2",
    ),
    Check(
        "xp2-lights-tab",
        QT_TRANSLATE_NOOP("HardwareSession", "DDJ-XP2: the app lights each pad"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Close Serato first, or it repaints the pads. Open Check a Controller, pick DDJ-XP2 and its Lights "
            "tab: the app lights one pad at a time. Answer for each one, at least the first pad mode of both "
            "decks, and note the colours you see.",
        ),
        "#451",
        controller="DDJ-XP2",
        tool=TOOL_PROFILE_CHECK,
    ),
    Check(
        "startup-buttons",
        QT_TRANSLATE_NOOP("HardwareSession", "Startup Check: each button opens its tool"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "With the controllers plugged in, open the Startup Check and click a few of its buttons (probe "
            "the lights, make a scene…). Each should close the window and open the matching tool.",
        ),
        "#451",
        tool=TOOL_STARTUP_CHECK,
    ),
    Check(
        "macros-in-serato",
        QT_TRANSLATE_NOOP("HardwareSession", "Macros: each one does what its name says"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "With Serato open and the controllers plugged in, press the pad of each macro (the macro list "
            "shows them) and watch Serato. Note any macro that does nothing or the wrong thing; a macro sent "
            "to the IAC bus needs Serato MIDI Learn first.",
        ),
        "#486",
        tool=TOOL_MACROS,
    ),
    Check(
        "deck-switch-together",
        QT_TRANSLATE_NOOP("HardwareSession", "Decks 1/3 and 2/4: does the deck warning show?"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "With Serato open and the Live Monitor running, switch only the XDJ-XZ's left deck to 3 (SHIFT "
            "twice): a big warning must show over Serato, saying the DDJ-XP2 is still on deck 1. Switch the "
            "DDJ-XP2 to deck 3 too: the warning must go. Do the same on the right side (2 and 4). Neither "
            "controller switches when sent its own messages (test of 2026-11-28), so the app warns instead.",
        ),
        "#550",
        tool=TOOL_RECORD_SET,
    ),
    Check(
        "serato-output-spy",
        QT_TRANSLATE_NOOP("HardwareSession", "What does Serato send to the controllers when a deck switches?"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Install MIDI Monitor (free, snoize.com). In its window, under Spy on output to destinations, tick "
            "the XDJ-XZ and DDJ-XP2 outputs. With Serato open, switch the XDJ-XZ's left deck 1 to 3 and back, "
            "wait five seconds, then the DDJ-XP2's. Save the MIDI Monitor document (File, Save) and attach it "
            "to the issue: if Serato tells a controller which deck it is on, the app can tell the other one "
            "the same way.",
        ),
        "#550",
    ),
    Check(
        "record-and-analyse",
        QT_TRANSLATE_NOOP("HardwareSession", "Record a set and analyse it"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Click Record a live set, mix as usual (at least twenty minutes), then stop it in the Live Monitor "
            "and Analyse a set. Check the controls carry names, not CC numbers, and note the repeated gestures "
            "it finds: they make good macros.",
        ),
        "#488",
        tool=TOOL_RECORD_SET,
    ),
)

CHECKS_BY_ID = {check.id: check for check in CHECKS}


@dataclass(frozen=True)
class CapturedMessage:
    port: str
    event_type: str
    channel: int
    data1: int
    data2: int

    def text(self) -> str:
        return f"{self.port} · {self.event_type} ch {self.channel} · {self.data1} = {self.data2}"

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "event_type": self.event_type,
            "channel": self.channel,
            "data1": self.data1,
            "data2": self.data2,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> CapturedMessage:
        return cls(
            str(data.get("port", "")),
            str(data["event_type"]),
            int(data["channel"]),
            int(data["data1"]),
            int(data["data2"]),
        )


def captured_from_event(event) -> CapturedMessage | None:
    """An input-direction ``MidiEvent`` as a captured message, else None."""
    if getattr(event, "direction", "in") != "in":
        return None
    try:
        return CapturedMessage(
            str(event.port),
            str(event.event_type),
            int(event.channel),
            int(event.data1),
            int(event.data2),
        )
    except TypeError, ValueError:
        return None


@dataclass
class CheckResult:
    status: str = TODO
    note: str = ""
    captured: list[CapturedMessage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "note": self.note,
            "captured": [m.to_dict() for m in self.captured],
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> CheckResult:
        status = data.get("status", TODO)
        captured = []
        for item in data.get("captured", []) or []:
            try:
                captured.append(CapturedMessage.from_dict(item))
            except KeyError, TypeError, ValueError:
                continue
        return cls(
            status if status in STATUSES else TODO, str(data.get("note", "")), captured
        )


@dataclass
class HardwareSession:
    results: dict[str, CheckResult] = field(default_factory=dict)

    def result(self, check_id: str) -> CheckResult:
        return self.results.setdefault(check_id, CheckResult())

    def set_status(self, check_id: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        self.result(check_id).status = status

    def set_note(self, check_id: str, note: str) -> None:
        self.result(check_id).note = note

    def capture(self, check_id: str, message: CapturedMessage) -> bool:
        """Keeps the message (False once :data:`MAX_CAPTURED` are kept)."""
        captured = self.result(check_id).captured
        if len(captured) >= MAX_CAPTURED:
            return False
        captured.append(message)
        return True

    def clear_capture(self, check_id: str) -> None:
        self.result(check_id).captured.clear()

    def counts(self) -> dict[str, int]:
        counts = dict.fromkeys(STATUSES, 0)
        for check in CHECKS:
            counts[self.results.get(check.id, CheckResult()).status] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "results": {
                key: value.to_dict()
                for key, value in self.results.items()
                if key in CHECKS_BY_ID
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> HardwareSession:
        if data.get("format") != FORMAT:
            raise ValueError("not a hardware session file")
        results = {}
        for key, value in (data.get("results") or {}).items():
            if key in CHECKS_BY_ID and isinstance(value, Mapping):
                results[key] = CheckResult.from_dict(value)
        return cls(results)


def save_session(session: HardwareSession, path: str | os.PathLike) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(
        json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(part, path)


def load_session(path: str | os.PathLike) -> HardwareSession:
    """The saved session, or a fresh one when there is none or it can't be read."""
    path = Path(path)
    if not path.exists():
        return HardwareSession()
    try:
        return HardwareSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        _LOGGER.warning("Ignoring unreadable hardware session %s: %s", path, exc)
        return HardwareSession()


_NO_CAPTURE = QT_TRANSLATE_NOOP("HardwareSession", "Nothing captured yet.")
_NO_PRESS = QT_TRANSLATE_NOOP(
    "HardwareSession", "No press captured: {count} other message(s)."
)
_MATCHES = QT_TRANSLATE_NOOP(
    "HardwareSession", "Captured notes {numbers}: they match {source}."
)
_MATCHES_NONE = QT_TRANSLATE_NOOP(
    "HardwareSession", "Captured notes {numbers}: they match no known source."
)
_SUMMARY = QT_TRANSLATE_NOOP("HardwareSession", "{count} message(s) captured: {kinds}.")


def pressed_numbers(captured: Iterable[CapturedMessage]) -> tuple[int, ...]:
    """The distinct note numbers pressed (Note On, velocity > 0), in order."""
    numbers: list[int] = []
    for message in captured:
        if (
            message.event_type == "Note On"
            and message.data2 > 0
            and message.data1 not in numbers
        ):
            numbers.append(message.data1)
    return tuple(numbers)


def verdict(
    check: Check, result: CheckResult, translate: Translate = untranslated
) -> str:
    """What the capture says, in one sentence (empty for a check without capture)."""
    if not check.capture:
        return ""
    captured = result.captured
    if not captured:
        return translate(_NO_CAPTURE)
    if check.compare:
        numbers = pressed_numbers(captured)
        if not numbers:
            return translate(_NO_PRESS).format(count=len(captured))
        text = ", ".join(str(number) for number in numbers)
        for source, expected in check.compare.items():
            if set(numbers) == set(expected):
                return translate(_MATCHES).format(
                    numbers=text, source=translate(source)
                )
        return translate(_MATCHES_NONE).format(numbers=text)
    kinds: dict[tuple[str, int, int], int] = {}
    for message in captured:
        key = (message.event_type, message.channel, message.data1)
        kinds[key] = kinds.get(key, 0) + 1
    described = ", ".join(
        f"{kind} ch {channel} #{number} ×{count}"
        for (kind, channel, number), count in kinds.items()
    )
    return translate(_SUMMARY).format(count=len(captured), kinds=described)


def report_text(
    session: HardwareSession,
    app_version: str | None = None,
    now: datetime | None = None,
) -> str:
    """The session as Markdown, in English (it goes into GitHub issues)."""
    now = now or datetime.now().astimezone()
    lines = [
        "## Hardware session report",
        "",
        f"- App version: {app_version or 'unknown'}",
        f"- Date: {now.strftime('%Y-%m-%d %H:%M')}",
    ]
    counts = session.counts()
    lines.append(
        "- "
        + ", ".join(f"{counts[status]} {STATUS_LABELS[status]}" for status in STATUSES)
    )
    for check in CHECKS:
        result = session.results.get(check.id, CheckResult())
        lines += [
            "",
            f"### {check.title} ({check.issue})",
            "",
            f"- Result: **{STATUS_LABELS[result.status]}**",
        ]
        if result.note.strip():
            lines.append("- Note: " + " ".join(result.note.split()))
        said = verdict(check, result)
        if said:
            lines.append("- Capture: " + said)
        if result.captured:
            lines += (
                ["", "```"] + [message.text() for message in result.captured] + ["```"]
            )
    return "\n".join(lines)
