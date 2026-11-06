"""Groups the (usually ~10) exact-duplicate Control/MappingElement instances
that Serato writes for a single logical function (see the empirical finding:
every unique physical trigger in a real export is repeated verbatim several
times, and removing the "duplicates" breaks the config in Serato).

A MappingGroup is the safe unit of editing: every member shares the same
trigger (channel/event_type/control) and the same deck/slot/tag/event, so
editing them together keeps the file internally consistent instead of
turning identical duplicates into the conflicting kind the validator flags.

Bindings inside a Serato <case> (a modifier / SHIFT layer) group separately
per condition: Play while modifier_3 is off and Reverse while it is on are two
functions of one button, not duplicates."""

from __future__ import annotations

from dataclasses import dataclass, field

from djmidi.model import (
    NO_CONDITION,
    ConditionKey,
    Control,
    MappingElement,
    MidiConfig,
    UserIO,
    condition_of,
    describe_condition,
    iter_bindings,
)

Member = tuple[Control, UserIO, MappingElement]


@dataclass
class MappingGroup:
    deck_id: str
    slot_id: str
    tag: str
    event: str
    channel: str
    control_no: str
    event_type: str
    members: list[Member] = field(default_factory=list)
    # The <case> condition every member sits under (NO_CONDITION outside any).
    condition: ConditionKey = NO_CONDITION

    @property
    def representative(self) -> MappingElement:
        return self.members[0][2]

    @property
    def condition_text(self) -> str:
        """``modifier_3 = on`` -- empty for a binding outside any <case>."""
        return describe_condition(self.condition)


def build_mapping_groups(config: MidiConfig) -> list[MappingGroup]:
    groups: dict[tuple, MappingGroup] = {}
    order: list[tuple] = []
    for control in config.controls:
        for userio, case in iter_bindings(control):
            for mapping in userio.mappings:
                key = (
                    mapping.deck_id or "(none)",
                    mapping.slot_id or "(none)",
                    mapping.tag,
                    userio.event,
                    control.channel,
                    control.control,
                    control.event_type,
                    condition_of(case),
                )
                if key not in groups:
                    groups[key] = MappingGroup(
                        deck_id=key[0],
                        slot_id=key[1],
                        tag=key[2],
                        event=key[3],
                        channel=key[4],
                        control_no=key[5],
                        event_type=key[6],
                        condition=key[7],
                    )
                    order.append(key)
                groups[key].members.append((control, userio, mapping))
    return [groups[key] for key in order]
