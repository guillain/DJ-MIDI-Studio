"""Hardware-free fallback profile for unknown MIDI controllers."""

from __future__ import annotations

from dataclasses import dataclass, field

from djmidi.catalog._registry import ControlInfo, ControllerDefinition


@dataclass(frozen=True)
class GenericMidiControl:
    channel: str
    event_type: str
    data1: str
    data2: str = ""
    name: str = ""


@dataclass
class GenericMidiProfile:
    """Preserves learned triggers without guessing a vendor-specific layout."""

    name: str = "Generic MIDI"
    controls: list[GenericMidiControl] = field(default_factory=list)

    def learn(
        self,
        channel: str,
        event_type: str,
        data1: str,
        data2: str = "",
        name: str = "",
    ) -> GenericMidiControl:
        control = GenericMidiControl(channel, event_type, data1, data2, name)
        if control not in self.controls:
            self.controls.append(control)
        return control

    def to_definition(self) -> ControllerDefinition:
        entries = [
            ControlInfo(
                self.name,
                "GENERIC",
                control.name or f"{control.event_type} {control.data1}",
                _event_kind(control.event_type),
                (control.channel,),
                control.data1,
            )
            for control in self.controls
        ]
        return ControllerDefinition(
            name=self.name,
            plugin_id="generic.midi",
            manufacturer="Generic",
            midi_capabilities=("midi.input",),
            static_entries=entries,
            section_order=("GENERIC",),
            display_order=1000,
        )


def _event_kind(event_type: str) -> str:
    lowered = event_type.casefold()
    if "note" in lowered:
        return "NOTE"
    if "control" in lowered or lowered in {"cc", "control_change"}:
        return "CC"
    raise ValueError(f"Unsupported generic MIDI event type: {event_type!r}")


__all__ = ["GenericMidiControl", "GenericMidiProfile"]
