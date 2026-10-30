"""Plays MIDI macros (issue #228) without blocking the event loop.

``midi_macros.run_macro`` sleeps between steps, fine for a script but not
for the GUI: a 500 ms pause would freeze every view. :class:`MacroPlayer`
sends the steps due right away and schedules the rest with
``QTimer.singleShot``, so several macros (or the same one twice) can play at
once. A macro whose steps have no delay plays synchronously and
:meth:`MacroPlayer.play` returns its result immediately.

Each run keeps its output port open across short delays (issue #308):
reopening the port per step is slow and some drivers drop messages on
reopen (#297). On Windows, though, an output port usually takes one client
(issue #336), so the player never lets a run lock a controller out:

* runs on the same port share one ref-counted handle (:class:`_SharedPort`),
  opened by the first run that needs it and closed when the last one lets
  go, so overlapping macros -- or the same one pressed twice -- work;
* a run releases its hold before a delay longer than
  ``HOLD_PORT_MAX_DELAY_MS`` and reopens the port when the delay is over,
  so Sync, Live send and other apps can use the controller meanwhile.

A *wait* step (issue #367) pauses a run until the main window feeds it the
awaited controller press (:meth:`MacroPlayer.feed_event`); the run lets go
of its port meanwhile and gives up after the step's timeout.

A held port spans event-loop turns, so every way a run can end lets go of
it -- the last step, a failing open or send, :meth:`MacroPlayer.stop_all`,
and the player being destroyed with runs still waiting (every handle is
closed then and a pending timer never fires).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal

from djmidi.midi_macros import (
    HOLD_PORT_MAX_DELAY_MS,
    WAIT_TIMED_OUT,
    MacroResult,
    MacroTrigger,
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
    # The shared port's sender while this run holds it, else None.
    send: Callable[..., None] | None = None
    # The press a wait step is waiting for, else None.
    waiting_for: MacroTrigger | None = None


@dataclass(eq=False)
class _SharedPort:
    """One open output port and how many runs hold it."""

    send: Callable[..., None]
    stack: ExitStack = field(default_factory=ExitStack)
    holders: int = 0


def _close_port(name: str, shared: _SharedPort) -> None:
    try:
        shared.stack.close()
    except Exception as exc:  # noqa: BLE001 - closing must never crash the app
        _LOGGER.warning("Macro player: closing %r failed: %s", name, exc)


def _close_ports(ports: dict[str, _SharedPort]) -> None:
    """Closes the ports still held when the player is destroyed. Takes the
    dict, not the player, since the player is gone by then."""
    while ports:
        _close_port(*ports.popitem())


class MacroPlayer(QObject):
    # Emitted once per play() call with its MacroResult, failures included.
    finished = Signal(object)

    def __init__(
        self,
        sender: Callable[..., None] | None = None,
        parent: QObject | None = None,
        port_opener: PortOpener | None = None,
        hold_port_ms: int = HOLD_PORT_MAX_DELAY_MS,
    ) -> None:
        super().__init__(parent)
        self._sender = sender
        self._port_opener = port_opener
        # Longest delay a run waits with its port held (tests shorten it).
        self._hold_port_ms = hold_port_ms
        self._running: list[_Run] = []
        self._ports: dict[str, _SharedPort] = {}
        self.destroyed.connect(partial(_close_ports, self._ports))

    @property
    def running(self) -> int:
        """How many macros are still waiting on a delay or a press."""
        return len(self._running)

    @property
    def waiting(self) -> int:
        """How many runs are waiting for a controller press."""
        return sum(1 for run in self._running if run.waiting_for is not None)

    def feed_event(self, event) -> bool:
        """Resumes the runs waiting for this live press; True when one was
        (the press then belongs to them, not to another macro's trigger)."""
        resumed = [run for run in self._running if run.waiting_for is not None and run.waiting_for.matches(event)]
        for run in resumed:
            run.waiting_for = None
            run.index += 1
            self._advance(run)
        return bool(resumed)

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

    @property
    def open_ports(self) -> list[str]:
        """The ports a run currently holds open."""
        return list(self._ports)

    def _acquire(self, run: _Run) -> None:
        """Gives ``run`` the shared handle of its port, opening it first when
        no other run holds it. Raises when the port won't open."""
        shared = self._ports.get(run.port)
        if shared is None:
            stack = ExitStack()
            # Resolved per open, so the default stays midi_io.open_midi_output
            # as it is when the macro plays (tests patch it).
            opener = macro_port_opener(self._sender, self._port_opener)
            send = stack.enter_context(opener(run.port))
            shared = self._ports[run.port] = _SharedPort(send, stack)
        shared.holders += 1
        run.send = shared.send

    def _release(self, run: _Run) -> None:
        """Lets go of ``run``'s hold; the last holder closes the port."""
        if run.send is None:
            return
        run.send = None
        shared = self._ports.get(run.port)
        if shared is None:
            return
        shared.holders -= 1
        if shared.holders <= 0:
            del self._ports[run.port]
            _close_port(run.port, shared)

    def stop_all(self) -> None:
        """Cancels every waiting run, closing its port; each reports a
        ``"cancelled"`` result."""
        for run in list(self._running):
            self._finish(run, CANCELLED)

    def _advance(self, run: _Run) -> MacroResult | None:
        if run not in self._running:  # cancelled while its timer was pending
            return None
        steps = run.macro.steps
        while run.index < len(steps):
            step = steps[run.index]
            if step.wait:
                run.waiting_for = step.wait_trigger
                self._release(run)  # nobody knows how long the press takes
                index = run.index
                QTimer.singleShot(step.wait_timeout_ms, self, lambda run=run, index=index: self._wait_expired(run, index))
                return None
            if step.delay_ms and not run.waited:
                run.waited = True
                if step.delay_ms > self._hold_port_ms:
                    self._release(run)  # don't lock the controller out (#336)
                QTimer.singleShot(step.delay_ms, self, lambda run=run: self._advance(run))
                return None
            run.waited = False
            try:
                if run.send is None:
                    self._acquire(run)
                assert run.send is not None
                send_step(run.send, step.message)
            except Exception as exc:  # noqa: BLE001 - a failing port must not crash the app
                return self._finish(run, str(exc))
            run.index += 1
        return self._finish(run)

    def _wait_expired(self, run: _Run, index: int) -> None:
        if run in self._running and run.waiting_for is not None and run.index == index:
            self._finish(run, WAIT_TIMED_OUT)

    def _finish(self, run: _Run, error: str = "") -> MacroResult:
        if run in self._running:
            self._running.remove(run)
        self._release(run)
        if error and error != CANCELLED:
            _LOGGER.warning("Macro %r: sending to %r failed after %d message(s): %s", run.macro.name, run.port, run.index, error)
        result = MacroResult(run.macro.name, run.port, run.index, len(run.macro.steps), error)
        self.finished.emit(result)
        return result
