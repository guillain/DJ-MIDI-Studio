"""Plays MIDI macros (issue #228) without blocking the event loop.

``midi_macros.run_macro`` sleeps between steps, fine for a script but not
for the GUI: a 500 ms pause would freeze every view. :class:`MacroPlayer`
sends the steps due right away and schedules the rest with
``QTimer.singleShot``, so several macros (or the same one twice) can play at
once. A macro whose steps have no delay plays synchronously and
:meth:`MacroPlayer.play` returns its result immediately.

Each run opens its output port once and keeps it open across its delays
(issue #308): reopening the port per step is slow and some drivers drop
messages on reopen (#297). The trade-off is a port held open across
event-loop turns, so every way a run can end closes it -- the last step,
a failing open or send, :meth:`MacroPlayer.stop_all`, and the player
being destroyed with runs still waiting (a pending timer then never fires).
A macro waits at most ``MAX_DELAY_MS`` per step, so the hold is bounded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal

from djmidi.midi_macros import (
    MacroResult,
    MidiMacro,
    PortOpener,
    macro_port_opener,
    resolve_macro_port,
    send_step,
    unplayable_result,
)

_LOGGER = logging.getLogger(__name__)

CANCELLED = "cancelled"


@dataclass(eq=False)  # compared by identity: two runs of one macro are distinct
class _Run:
    macro: MidiMacro
    port: str
    index: int = 0
    waited: bool = False
    # Holds the open port until the run ends.
    stack: ExitStack = field(default_factory=ExitStack)
    send: Callable[..., None] | None = None


def _close_run(run: _Run) -> None:
    try:
        run.stack.close()
    except Exception as exc:  # noqa: BLE001 - closing must never crash the app
        _LOGGER.warning("Macro %r: closing %r failed: %s", run.macro.name, run.port, exc)


def _close_runs(runs: list[_Run]) -> None:
    """Closes the ports of runs left waiting when the player is destroyed.
    Takes the list, not the player, since the player is gone by then."""
    while runs:
        _close_run(runs.pop())


class MacroPlayer(QObject):
    # Emitted once per play() call with its MacroResult, failures included.
    finished = Signal(object)

    def __init__(
        self,
        sender: Callable[..., None] | None = None,
        parent: QObject | None = None,
        port_opener: PortOpener | None = None,
    ) -> None:
        super().__init__(parent)
        self._sender = sender
        self._port_opener = port_opener
        self._running: list[_Run] = []
        self.destroyed.connect(partial(_close_runs, self._running))

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
        try:
            # Resolved per run, so the default stays midi_io.open_midi_output
            # as it is when the macro plays (tests patch it).
            opener = macro_port_opener(self._sender, self._port_opener)
            run.send = run.stack.enter_context(opener(port))
        except Exception as exc:  # noqa: BLE001 - a port that won't open must not crash the app
            return self._finish(run, str(exc))
        return self._advance(run)

    def stop_all(self) -> None:
        """Cancels every waiting run, closing its port; each reports a
        ``"cancelled"`` result."""
        for run in list(self._running):
            self._finish(run, CANCELLED)

    def _advance(self, run: _Run) -> MacroResult | None:
        if run not in self._running:  # cancelled while its timer was pending
            return None
        assert run.send is not None  # opened by play()
        steps = run.macro.steps
        while run.index < len(steps):
            step = steps[run.index]
            if step.delay_ms and not run.waited:
                run.waited = True
                QTimer.singleShot(step.delay_ms, self, lambda run=run: self._advance(run))
                return None
            run.waited = False
            try:
                send_step(run.send, step.message)
            except Exception as exc:  # noqa: BLE001 - a failing port must not crash the app
                return self._finish(run, str(exc))
            run.index += 1
        return self._finish(run)

    def _finish(self, run: _Run, error: str = "") -> MacroResult:
        if run in self._running:
            self._running.remove(run)
        _close_run(run)
        if error and error != CANCELLED:
            _LOGGER.warning("Macro %r: sending to %r failed after %d message(s): %s", run.macro.name, run.port, run.index, error)
        result = MacroResult(run.macro.name, run.port, run.index, len(run.macro.steps), error)
        self.finished.emit(result)
        return result
