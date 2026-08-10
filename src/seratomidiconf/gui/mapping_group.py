"""Groups the (usually ~10) exact-duplicate Control/MappingElement instances
that Serato writes for a single logical function (see the empirical finding:
every unique physical trigger in a real export is repeated verbatim several
times, and removing the "duplicates" breaks the config in Serato).

A MappingGroup is the safe unit of editing: every member shares the same
trigger (channel/event_type/control) and the same deck/slot/tag/event, so
editing them together keeps the file internally consistent instead of
turning identical duplicates into the conflicting kind the validator flags."""

from __future__ import annotations

from dataclasses import dataclass, field

from seratomidiconf.model import Control, MappingElement, MidiConfig, UserIO

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

    @property
    def representative(self) -> MappingElement:
        return self.members[0][2]


def build_mapping_groups(config: MidiConfig) -> list[MappingGroup]:
    groups: dict[tuple[str, str, str, str, str, str, str], MappingGroup] = {}
    order: list[tuple[str, str, str, str, str, str, str]] = []
    for control in config.controls:
        for userio in control.userios:
            for mapping in userio.mappings:
                key = (
                    mapping.deck_id or "(none)",
                    mapping.slot_id or "(none)",
                    mapping.tag,
                    userio.event,
                    control.channel,
                    control.control,
                    control.event_type,
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
                    )
                    order.append(key)
                groups[key].members.append((control, userio, mapping))
    return [groups[key] for key in order]
