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

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from djmidi import catalog
from djmidi.atelier.describe import controller_for_port
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

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
) -> StartupReport:
    """`macros` are `midi_macros.MidiMacro`s (only `name` and `output_port`
    are read); `sync_controllers` the controllers with a stored sync set."""
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
    order = {BLOCKING: 0, TODO: 1, OK: 2}
    report.items.sort(key=lambda item: order[item.status])
    return report


__all__ = [
    "BLOCKING",
    "CHECK",
    "IAC",
    "LEARN",
    "LEDS",
    "MACROS",
    "OK",
    "SCENE",
    "TODO",
    "StartupItem",
    "StartupReport",
    "check_startup",
    "controller_of_port",
    "is_own_or_loopback",
]
