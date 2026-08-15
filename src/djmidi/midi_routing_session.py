"""Controlled physical execution for configured MIDI routes."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

import mido

from djmidi.midi_api import MidiMessage
from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_router import MidiRouter

InputOpener = Callable[[str], Any]
OutputOpener = Callable[[str], Any]
SERATO_CLOCK_INPUT_NAME = "DJ MIDI Studio Serato Clock In"


class MidiRoutingSession:
    """Poll open MIDI inputs and forward messages through a :class:`MidiRouter`.

    The openers are injectable so routing behavior can be tested without MIDI
    hardware. Physical routing is deliberately opt-in and this class never
    opens a port until :meth:`start` is called.
    """

    def __init__(
        self,
        router: MidiRouter,
        *,
        input_opener: InputOpener = mido.open_input,
        output_opener: OutputOpener = mido.open_output,
        clock_mirror: MidiClockMirror | None = None,
        clock_mirrors: Iterable[MidiClockMirror] | None = None,
        virtual_input_ids: Iterable[str] = (),
        virtual_input_opener: InputOpener | None = None,
    ) -> None:
        self.router = router
        self._input_opener = input_opener
        self._output_opener = output_opener
        self._virtual_input_opener = virtual_input_opener or (
            lambda name: mido.open_input(name, virtual=True)
        )
        self._virtual_input_ids = frozenset(virtual_input_ids)
        if clock_mirror is not None and clock_mirrors is not None:
            raise ValueError("use clock_mirror or clock_mirrors, not both")
        self._clock_mirrors = tuple(clock_mirrors or ((clock_mirror,) if clock_mirror else ()))
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        self.running = False

    @property
    def input_port_ids(self) -> tuple[str, ...]:
        return tuple(self._inputs)

    @property
    def output_port_ids(self) -> tuple[str, ...]:
        return tuple(self._outputs)

    def set_clock_mirror(self, clock_mirror: MidiClockMirror | None) -> None:
        self.set_clock_mirrors(() if clock_mirror is None else (clock_mirror,))

    def set_clock_mirrors(self, clock_mirrors: Iterable[MidiClockMirror]) -> None:
        if self.running:
            raise RuntimeError("stop the routing session before changing the Clock policy")
        self._clock_mirrors = tuple(clock_mirrors)

    def set_virtual_input_ids(self, input_ids: Iterable[str]) -> None:
        if self.running:
            raise RuntimeError("stop the routing session before changing virtual MIDI inputs")
        self._virtual_input_ids = frozenset(input_ids)

    def start(self) -> None:
        routes = tuple(route for route in self.router.routes if route.enabled)
        if not routes and not self._clock_mirrors:
            raise ValueError("at least one enabled MIDI route or Clock policy is required")
        self._validate_topology(routes)
        self.stop()
        input_ids = {route.source_port_id for route in routes}
        output_ids = {route.destination_port_id for route in routes}
        for clock_mirror in self._clock_mirrors:
            input_ids.add(clock_mirror.source_port_id)
            output_ids.update(clock_mirror.destination_port_ids)
        try:
            for port_id in sorted(input_ids):
                opener = (
                    self._virtual_input_opener
                    if port_id in self._virtual_input_ids
                    else self._input_opener
                )
                self._inputs[port_id] = opener(port_id)
            for port_id in sorted(output_ids):
                self._outputs[port_id] = self._output_opener(port_id)
        except Exception:
            self.stop()
            raise
        self.running = True

    def stop(self) -> None:
        self.running = False
        for port in (*self._inputs.values(), *self._outputs.values()):
            close = getattr(port, "close", None)
            if close is not None:
                close()
        self._inputs.clear()
        self._outputs.clear()

    def poll(self) -> int:
        """Drain each input once and return the number of forwarded messages."""
        if not self.running:
            return 0
        forwarded = 0
        for source_id, port in self._inputs.items():
            for message in self._pending(port):
                normalized = MidiMessage(
                    data=bytes(message.bytes()),
                    received_time=time.monotonic(),
                    port_id=source_id,
                )
                forwarded += self.router.route_message(source_id, normalized, self._send)
                for clock_mirror in self._clock_mirrors:
                    forwarded += clock_mirror.forward(normalized, self._send)
        return forwarded

    @staticmethod
    def _pending(port: Any) -> Iterable[Any]:
        return port.iter_pending()

    def _send(self, destination_id: str, message: MidiMessage) -> None:
        self._outputs[destination_id].send(mido.Message.from_bytes(list(message.data)))

    def _validate_topology(self, routes: tuple) -> None:
        """Reject cycles formed by regular routes and Clock routes together.

        Clock edges are physical connections too. Treating them separately
        from ``MidiRouter`` would allow A -> B through a regular route and
        B -> A through Clock, which can create an uncontrolled feedback loop.
        """
        graph: dict[str, set[str]] = {}
        for route in routes:
            graph.setdefault(route.source_port_id, set()).add(route.destination_port_id)
        for mirror in self._clock_mirrors:
            for destination in mirror.destination_port_ids:
                graph.setdefault(mirror.source_port_id, set()).add(destination)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(child) for child in graph.get(node, ())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        if any(visit(node) for node in graph if node not in visited):
            raise ValueError("combined MIDI and Clock routes would create a feedback loop")


__all__ = ["SERATO_CLOCK_INPUT_NAME", "MidiRoutingSession"]
