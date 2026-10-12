"""Plays MIDI macros (issue #228) without blocking the event loop.

``midi_macros.run_macro`` sleeps between steps, fine for a script but not
for the GUI: a 500 ms pause would freeze every view. :class:`MacroPlayer`
sends the steps due right away and schedules the rest with
``QTimer.singleShot``, so several macros (or the same one twice) can play at
once. A macro whose steps have no delay plays synchronously and
:meth:`MacroPlayer.play` returns its result immediately.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from djmidi.midi_macros import (
    MacroResult,
    MidiMacro,
    resolve_macro_port,
    send_message,
    unplayable_result,
)


@dataclass
class _Run:
    macro: MidiMacro
    port: str
    index: int = 0
    waited: bool = False


class MacroPlayer(QObject):
    # Emitted once per play() call with its MacroResult, failures included.
    finished = Signal(object)

    def __init__(self, sender: Callable[..., None] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sender = sender
        self._running: list[_Run] = []

    @property
    def running(self) -> int:
        """How many macros are still waiting on a delay."""
        return len(self._running)

    def play(self, macro: MidiMacro, available_ports: Sequence[str]) -> MacroResult | None:
        """Starts ``macro``; returns its result when it finished right away
        (no delay, or it couldn't start), ``None`` while it is still playing."""
        failed = unplayable_result(macro, available_ports)
        if failed is not None:
            self.finished.emit(failed)
            return failed
        port = resolve_macro_port(macro, available_ports)
        assert port is not None  # checked by unplayable_result
        run = _Run(macro, port)
        self._running.append(run)
        return self._advance(run)

    def _advance(self, run: _Run) -> MacroResult | None:
        steps = run.macro.steps
        while run.index < len(steps):
            step = steps[run.index]
            if step.delay_ms and not run.waited:
                run.waited = True
                QTimer.singleShot(step.delay_ms, self, lambda run=run: self._advance(run))
                return None
            run.waited = False
            try:
                send_message(step.message, run.port, self._sender)
            except Exception as exc:  # noqa: BLE001 - a failing port must not crash the app
                return self._finish(run, str(exc))
            run.index += 1
        return self._finish(run)

    def _finish(self, run: _Run, error: str = "") -> MacroResult:
        if run in self._running:
            self._running.remove(run)
        result = MacroResult(run.macro.name, run.port, run.index, len(run.macro.steps), error)
        self.finished.emit(result)
        return result
