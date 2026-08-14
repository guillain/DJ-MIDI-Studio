from __future__ import annotations

import argparse
import sys

from seratomidiconf.midi_io import list_output_ports, send_midi_message


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a one-shot MIDI message (Note On/Off or Control Change)."
    )
    parser.add_argument("--list-ports", action="store_true", help="List MIDI output ports and exit")
    parser.add_argument("--port", help="Output port name")
    parser.add_argument("--type", dest="event_type", help="Event type: note_on, note_off, control_change, cc")
    parser.add_argument("--channel", type=int, help="MIDI channel (1-16)")
    parser.add_argument("--data1", type=int, help="Note/CC number (0-127)")
    parser.add_argument("--data2", type=int, help="Velocity/value (0-127)")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()

    if args.list_ports:
        ports = list_output_ports()
        for name in ports:
            print(name)
        return 0

    missing = [
        name
        for name, value in (
            ("--port", args.port),
            ("--type", args.event_type),
            ("--channel", args.channel),
            ("--data1", args.data1),
            ("--data2", args.data2),
        )
        if value is None
    ]
    if missing:
        parser.error(f"Missing required arguments: {', '.join(missing)}")

    try:
        send_midi_message(
            output_port_name=args.port,
            event_type=args.event_type,
            channel_1_based=args.channel,
            data1=args.data1,
            data2=args.data2,
        )
    except Exception as exc:  # noqa: BLE001 - CLI should surface clear user-facing errors
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

