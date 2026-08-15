from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from djmidi.catalog._registry import ControlInfo
from djmidi.midi_io import MidiEvent, send_midi_message


@dataclass(frozen=True)
class PlaybackStats:
    sent_messages: int = 0
    skipped_entries: int = 0


def _parse_int(text: str, field_name: str, low: int, high: int) -> int:
    try:
        value = int(text.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if not low <= value <= high:
        raise ValueError(f"{field_name} must be in [{low}, {high}]")
    return value


def send_control_info_entry(
    output_port_name: str,
    entry: ControlInfo,
    value: int,
    sender: Callable[..., None] | None = None,
) -> int:
    sender = send_midi_message if sender is None else sender
    sent = 0
    data1 = _parse_int(entry.data1, "Data1", 0, 127)
    for channel_text in entry.channels:
        channel = _parse_int(channel_text, "Channel", 1, 16)
        if entry.note_or_cc == "NOTE":
            sender(
                output_port_name=output_port_name,
                event_type="note_on",
                channel_1_based=channel,
                data1=data1,
                data2=value,
            )
            sender(
                output_port_name=output_port_name,
                event_type="note_off",
                channel_1_based=channel,
                data1=data1,
                data2=0,
            )
            sent += 2
        elif entry.note_or_cc == "CC":
            sender(
                output_port_name=output_port_name,
                event_type="control_change",
                channel_1_based=channel,
                data1=data1,
                data2=value,
            )
            sent += 1
        else:
            raise ValueError(f"Unsupported row Type: {entry.note_or_cc!r}")
    return sent


def replay_midi_events(
    output_port_name: str,
    events: Sequence[MidiEvent],
    sender: Callable[..., None] | None = None,
) -> PlaybackStats:
    """Replay captured MIDI events immediately, preserving their event order."""
    sender = send_midi_message if sender is None else sender
    sent = 0
    skipped = 0
    for event in events:
        try:
            sender(
                output_port_name=output_port_name,
                event_type=event.event_type,
                channel_1_based=_parse_int(event.channel, "Channel", 1, 16),
                data1=_parse_int(event.data1, "Data1", 0, 127),
                data2=_parse_int(event.data2, "Data2", 0, 127),
            )
            sent += 1
        except ValueError:
            skipped += 1
    return PlaybackStats(sent_messages=sent, skipped_entries=skipped)


def play_control_info_entries(
    output_port_name: str,
    entries: Sequence[ControlInfo],
    value: int,
    sender: Callable[..., None] | None = None,
) -> PlaybackStats:
    sent = 0
    skipped = 0
    for entry in entries:
        try:
            sent += send_control_info_entry(output_port_name, entry, value, sender=sender)
        except ValueError:
            skipped += 1
    return PlaybackStats(sent_messages=sent, skipped_entries=skipped)


__all__ = ["PlaybackStats", "play_control_info_entries", "replay_midi_events", "send_control_info_entry"]
