"""Controlled physical execution for configured MIDI routes."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

import mido

from djmidi.midi_api import MidiMessage
from djmidi.midi_router import MidiRouter

InputOpener = Callable[[str], Any]
OutputOpener = Callable[[str], Any]


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
    ) -> None:
        self.router = router
        self._input_opener = input_opener
        self._output_opener = output_opener
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        self.running = False

    @property
    def input_port_ids(self) -> tuple[str, ...]:
        return tuple(self._inputs)

    @property
    def output_port_ids(self) -> tuple[str, ...]:
        return tuple(self._outputs)

    def start(self) -> None:
        routes = tuple(route for route in self.router.routes if route.enabled)
        if not routes:
            raise ValueError("at least one enabled MIDI route is required")
        self.stop()
        input_ids = {route.source_port_id for route in routes}
        output_ids = {route.destination_port_id for route in routes}
        try:
            for port_id in sorted(input_ids):
                self._inputs[port_id] = self._input_opener(port_id)
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
        return forwarded

    @staticmethod
    def _pending(port: Any) -> Iterable[Any]:
        return port.iter_pending()

    def _send(self, destination_id: str, message: MidiMessage) -> None:
        self._outputs[destination_id].send(mido.Message.from_bytes(list(message.data)))


__all__ = ["MidiRoutingSession"]
