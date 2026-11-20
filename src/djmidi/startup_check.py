"""The startup check: what's plugged in, compared with what the app knows,
as a short list of things to finish -- each with the one action that
finishes it (golden rule: the app comes to the DJ). Qt-free and read-only:
it only looks at port names and the workspace's own files, sends no MIDI
and changes nothing.

Statuses: ``OK`` (nothing to do), ``TODO`` (works, but something would make
it better: a check never run, LEDs never probed, no scene) and ``BLOCKING``
(something the DJ set up can't work right now: a macro whose port is gone).
Each item has a stable ``id`` so the DJ can hide it for good.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from djmidi import catalog
from djmidi.atelier.describe import controller_for_port
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

_LOGGER = logging.getLogger(__name__)

OK, TODO, BLOCKING = "ok", "todo", "blocking"
# Actions the window offers; MainWindow opens the matching tool.
LEARN, CHECK, LEDS, SCENE, MACROS, IAC = (
    "learn",
    "check",
    "leds",
    "scene",
    "macros",
    "iac",
)
MOVE_TRIGGER = "move_trigger"  # params: macro, channel, note, port, pad

# The app's own virtual ports and loopback buses are not devices to check.
_OWN_OR_LOOPBACK = re.compile(r"^(DJMidiStudio|DJ MIDI Studio|IAC\b)", re.IGNORECASE)
_IAC = re.compile(r"^IAC\b", re.IGNORECASE)

_TEXTS = {
    "unknown": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "The app doesn't know this device yet: teach it the controls in a few presses.",
    ),
    "never_checked": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "Never checked on your unit: a guided check confirms every button in a few minutes.",
    ),
    "leds": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "Its lights were never probed: the app is guessing which note lights what.",
    ),
    "no_scene": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "No light scene yet: design how it should light up when the set starts.",
    ),
    "ready": QT_TRANSLATE_NOOP(
        "StartupCheck", "Ready: checked, lights probed and a scene saved."
    ),
    "iac_offline": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "{port} is offline, so {count} macro(s) can't reach your DJ software: {macros}.",
    ),
    "port_missing": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "{port} isn't connected, so {count} macro(s) can't play: {macros}.",
    ),
    "controller_unplugged": QT_TRANSLATE_NOOP(
        "StartupCheck", "Not plugged in: plug it in to use {count} macro(s) ({macros})."
    ),
    "trigger_in_serato": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "{trigger} fires the macro {macro}, but your Serato mapping {file} uses it too: "
        "one press would do both.",
    ),
    "trigger_in_serato_no_free": QT_TRANSLATE_NOOP(
        "StartupCheck",
        "{trigger} fires the macro {macro}, but your Serato mapping {file} uses it too, "
        "and no pad of that mode is free: pick another trigger.",
    ),
    "nothing_plugged": QT_TRANSLATE_NOOP(
        "StartupCheck", "No controller is plugged in. Plug one in, then check again."
    ),
}


@dataclass(frozen=True)
class StartupItem:
    id: str
    device: str
    status: str
    text_key: str
    action: str | None = None
    controller: str | None = None
    params: tuple[tuple[str, str], ...] = ()

    def text(self, translate: Translate = untranslated) -> str:
        return translate(_TEXTS[self.text_key]).format(**dict(self.params))


@dataclass
class StartupReport:
    items: list[StartupItem] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)

    def needing_attention(self, dismissed: Iterable[str] = ()) -> list[StartupItem]:
        hidden = set(dismissed)
        return [
            item for item in self.items if item.status != OK and item.id not in hidden
        ]


def is_own_or_loopback(port: str) -> bool:
    return bool(_OWN_OR_LOOPBACK.match(port.strip()))


def controller_of_port(port: str) -> str | None:
    """The controller a port belongs to: an exact name match, else the best
    catalog match ("XDJ-XZ (1)" is the XDJ-XZ)."""
    exact = controller_for_port(port)
    if exact is not None:
        return exact
    matches = catalog.detect_controller(port, include_disabled=True)
    return matches[0].controller.name if matches and matches[0].score > 0 else None


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _port_connected(port: str, outputs: Sequence[str]) -> bool:
    if port in outputs:
        return True
    squashed = _squash(port)
    return bool(squashed) and any(
        squashed in _squash(name) or _squash(name) in squashed for name in outputs
    )


def check_startup(
    input_ports: Sequence[str],
    output_ports: Sequence[str],
    macros: Iterable = (),
    sync_controllers: Iterable[str] = (),
    has_captures: Callable[[str], bool] = lambda _controller: False,
    has_leds: Callable[[str], bool] = lambda _controller: False,
    serato_files: Sequence[Path] = (),
) -> StartupReport:
    """`macros` are `midi_macros.MidiMacro`s (`name`, `output_port` and
    `triggers` are read); `sync_controllers` the controllers with a stored
    sync set; `serato_files` the DJ's Serato MIDI mapping files (only those
    whose name names a trigger's controller are read)."""
    macros = list(macros)
    report = StartupReport()
    with_scene = set(sync_controllers)
    seen: dict[str, list[str]] = {}
    for port in input_ports:
        if is_own_or_loopback(port):
            continue
        controller = controller_of_port(port)
        seen.setdefault(controller or f"\x00{port}", []).append(port)
    for key in seen:
        if key.startswith("\x00"):
            port = key[1:]
            report.devices.append(port)
            report.items.append(
                StartupItem(f"unknown:{port}", port, TODO, "unknown", LEARN)
            )
            continue
        controller = key
        report.devices.append(controller)
        before = len(report.items)
        if not has_captures(controller):
            report.items.append(
                StartupItem(
                    f"check:{controller}",
                    controller,
                    TODO,
                    "never_checked",
                    CHECK,
                    controller,
                )
            )
        if not has_leds(controller):
            report.items.append(
                StartupItem(
                    f"leds:{controller}", controller, TODO, "leds", LEDS, controller
                )
            )
        if controller not in with_scene:
            report.items.append(
                StartupItem(
                    f"scene:{controller}",
                    controller,
                    TODO,
                    "no_scene",
                    SCENE,
                    controller,
                )
            )
        if len(report.items) == before:
            report.items.append(
                StartupItem(
                    f"ready:{controller}", controller, OK, "ready", None, controller
                )
            )
    if not seen:
        report.items.append(
            StartupItem("nothing-plugged", "MIDI", TODO, "nothing_plugged")
        )

    missing: dict[str, list[str]] = {}
    for macro in macros:
        port = (getattr(macro, "output_port", "") or "").strip()
        if port and not _port_connected(port, output_ports):
            missing.setdefault(port, []).append(macro.name)
    for port, names in missing.items():
        params = (
            ("port", port),
            ("count", str(len(names))),
            ("macros", ", ".join(names)),
        )
        if _IAC.match(port):
            report.items.append(
                StartupItem(
                    f"iac:{port}", port, BLOCKING, "iac_offline", IAC, params=params
                )
            )
        elif (controller := controller_of_port(port)) is not None:
            # A controller that's simply unplugged: plugging it in is the fix.
            report.items.append(
                StartupItem(
                    f"unplugged:{controller}",
                    controller,
                    TODO,
                    "controller_unplugged",
                    None,
                    controller,
                    params,
                )
            )
        else:
            report.items.append(
                StartupItem(
                    f"port:{port}",
                    port,
                    BLOCKING,
                    "port_missing",
                    MACROS,
                    params=params,
                )
            )
    if serato_files:
        report.items.extend(_trigger_conflicts(macros, serato_files))
    order = {BLOCKING: 0, TODO: 1, OK: 2}
    report.items.sort(key=lambda item: order[item.status])
    return report


def serato_bound_notes(files: Iterable[Path]) -> dict[tuple[int, int], str]:
    """Every Note (channel, number) a Serato mapping file binds to a function,
    with the first file (by name) binding it. Read-only; an unreadable file
    is skipped."""
    from djmidi.model import iter_bindings
    from djmidi.parser import parse_file

    bound: dict[tuple[int, int], str] = {}
    for path in sorted(files, key=lambda p: p.name.lower()):
        try:
            config = parse_file(str(path))
        except Exception:
            _LOGGER.warning(
                "Startup check: skipped unreadable Serato mapping %s",
                path,
                exc_info=True,
            )
            continue
        for control in config.controls:
            if "note" not in str(control.event_type).lower():
                continue
            try:
                key = (int(control.channel), int(control.control))
            except TypeError, ValueError:
                continue
            if key not in bound and any(
                userio.mappings for userio, _case in iter_bindings(control)
            ):
                bound[key] = path.name
    return bound


_PAD_MODE = re.compile(r"\(([^)]*)\)\s*$")


def _mode_of(label: str) -> str | None:
    match = _PAD_MODE.search(label)
    return match.group(1) if match else None


def free_pad(
    controller: str, channel: int, note: int, taken: set[tuple[int, int]]
) -> tuple[str, int, int] | None:
    """A pad of the same controller, deck channel and pad mode as
    (channel, note) that's in `taken` neither (Serato bindings, other
    triggers): (label, channel, note), lowest note first, or None."""
    from djmidi.atelier.features import NOTE, features_for

    features = [
        f
        for f in features_for(controller)
        if f.input.kind == NOTE and f.section == "PAD"
    ]
    current = next(
        (f for f in features if (f.input.channel, f.input.number) == (channel, note)),
        None,
    )
    if current is None:
        return None
    mode = _mode_of(current.label)
    same_bank = sorted(
        (
            f
            for f in features
            if f.input.channel == channel
            and _mode_of(f.label) == mode
            and (f.input.channel, f.input.number) not in taken
        ),
        key=lambda f: f.input.number,
    )
    return (
        (same_bank[0].label, channel, same_bank[0].input.number) if same_bank else None
    )


def _trigger_label(controller: str | None, channel: int, note: int) -> str:
    if controller is not None:
        from djmidi.atelier.features import NOTE, features_for

        for feature in features_for(controller):
            if feature.input.kind == NOTE and (
                feature.input.channel,
                feature.input.number,
            ) == (channel, note):
                return feature.label
    return f"Note {note} · ch {channel}"


def mapping_suggestions(
    controllers: Sequence[str], files_by_software: dict[str, Sequence[Path]]
) -> list[tuple[str, str, Path]]:
    """(controller, software id, file) for each mapping file named after a
    plugged controller, newest first per software: the Dashboard offers to
    open it, so the DJ never hunts for the file nor says which software."""
    found: list[tuple[str, str, Path]] = []
    for software_id, files in files_by_software.items():
        for controller in controllers:
            matches = serato_files_for(controller, files)
            matches.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
            if matches and not any(path == matches[0] for _c, _s, path in found):
                found.append((controller, software_id, matches[0]))
    return found


def serato_files_for(controller: str, files: Sequence[Path]) -> list[Path]:
    """The Serato mapping files whose name names `controller` ("xdj-xz
    ddj-xp2 - 4 decks.xml" for the DDJ-XP2): Serato keeps one file per
    device, and another device's file reuses the same channels and notes."""
    wanted = _squash(controller)
    return [path for path in files if wanted and wanted in _squash(path.stem)]


def _trigger_conflicts(macros: list, serato_files: Sequence[Path]) -> list[StartupItem]:
    """Macro triggers on a controller's notes that its Serato mapping binds
    too, each with a free pad of the same mode to move to."""
    bound_by_controller: dict[str, dict[tuple[int, int], str]] = {}

    def bound_for(controller: str | None) -> dict[tuple[int, int], str]:
        if controller is None:
            return {}
        if controller not in bound_by_controller:
            bound_by_controller[controller] = serato_bound_notes(
                serato_files_for(controller, serato_files)
            )
        return bound_by_controller[controller]

    triggers = [
        (macro, trigger, controller_of_port(trigger.port) if trigger.port else None)
        for macro in macros
        for trigger in getattr(macro, "triggers", ())
        if "note" in str(trigger.event_type).lower()
    ]
    items = []
    for macro, trigger, controller in triggers:
        serato_bound = bound_for(controller)
        key = (int(trigger.channel), int(trigger.data1))
        if key not in serato_bound:
            continue
        taken = set(serato_bound) | {
            (int(t.channel), int(t.data1)) for _m, t, c in triggers if c == controller
        }
        taken |= {
            (int(dict(i.params)["channel"]), int(dict(i.params)["note"]))
            for i in items
            if i.action == MOVE_TRIGGER
        }
        params = [
            ("trigger", _trigger_label(controller, *key)),
            ("macro", macro.name),
            ("file", serato_bound[key]),
        ]
        target = free_pad(controller, *key, taken)
        item_id = f"serato:{macro.name}:{key[0]}:{key[1]}"
        if target is None:
            items.append(
                StartupItem(
                    item_id,
                    controller,
                    BLOCKING,
                    "trigger_in_serato_no_free",
                    MACROS,
                    controller,
                    tuple(params),
                )
            )
            continue
        pad, channel, note = target
        params += [
            ("pad", pad),
            ("channel", str(channel)),
            ("note", str(note)),
            ("old_channel", str(key[0])),
            ("old_note", str(key[1])),
            ("port", trigger.port),
        ]
        items.append(
            StartupItem(
                item_id,
                controller,
                BLOCKING,
                "trigger_in_serato",
                MOVE_TRIGGER,
                controller,
                tuple(params),
            )
        )
    return items


__all__ = [
    "BLOCKING",
    "CHECK",
    "IAC",
    "LEARN",
    "LEDS",
    "MACROS",
    "MOVE_TRIGGER",
    "OK",
    "SCENE",
    "TODO",
    "StartupItem",
    "StartupReport",
    "check_startup",
    "controller_of_port",
    "free_pad",
    "is_own_or_loopback",
    "serato_bound_notes",
    "serato_files_for",
]
