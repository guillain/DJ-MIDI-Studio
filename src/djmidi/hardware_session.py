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


CHECKS: tuple[Check, ...] = (
    Check(
        "ddj-xp2-loop-notes",
        QT_TRANSLATE_NOOP("HardwareSession", "DDJ-XP2: 1/2X and 2X notes"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Click Start capture, press 1/2X then 2X on deck 1 (plain, without SHIFT), then Stop capture. "
            "The official MIDI Message List says notes 16 / 17; rekordbox's bundled mapping, a first real "
            "capture and this app's profile say 18 / 19.",
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
    ),
    Check(
        "serato-learn",
        QT_TRANSLATE_NOOP("HardwareSession", "Serato: MIDI-learn Play, Cue and Sync"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "Run scripts/serato_learn_iac.py, then in Serato's MIDI mode learn Play, Cue and Sync on decks 1 "
            "and 2 from the IAC bus, and export the mapping. Attach the XML to the issue: it gives Serato's "
            "own function names, which the Serato ↔ Traktor converter and the Atelier's function "
            "assignment wait for.",
        ),
        "#194",
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
        "traktor-exports",
        QT_TRANSLATE_NOOP("HardwareSession", "Traktor: Controller Manager exports"),
        QT_TRANSLATE_NOOP(
            "HardwareSession",
            "In Traktor's Controller Manager, export an empty Generic MIDI device, then add one button command "
            "and export again, then change one setting and export a third time. Attach the three .tsi files.",
        ),
        "#233",
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
