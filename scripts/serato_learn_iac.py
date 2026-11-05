"""Send one distinct Note On/Off per step on an IAC bus, for Serato's MIDI Learn.

Usage:  uv run python scripts/serato_learn_iac.py ["IAC Driver Bus 1"]
In Serato: enable the IAC bus (Setup > MIDI), click MIDI, click the function
on screen, then press Enter here -- Serato learns the note just sent.
"""

import sys
import time

import mido

PORT = sys.argv[1] if len(sys.argv) > 1 else "IAC Driver Bus 1"
STEPS = [
    ("Deck 1 PLAY", 0, 0),
    ("Deck 1 CUE", 0, 1),
    ("Deck 1 SYNC", 0, 2),
    ("Deck 2 PLAY", 1, 0),
    ("Deck 2 CUE", 1, 1),
    ("Deck 2 SYNC", 1, 2),
    *((f"Deck 1 HOT CUE {n}", 0, 9 + n) for n in range(1, 9)),
]

with mido.open_output(PORT) as out:
    print(f"Sending on {PORT!r}. Ctrl+C to stop.")
    print("Tip: export the mapping XML after each step if you can (most useful).")
    for label, channel, note in STEPS:
        input(f"\nIn Serato, click {label} (MIDI Learn), then press Enter... ")
        out.send(mido.Message("note_on", channel=channel, note=note, velocity=127))
        time.sleep(0.15)
        out.send(mido.Message("note_off", channel=channel, note=note, velocity=0))
        print(f"  sent {label}: channel {channel + 1}, note {note}")
    print("\nDone. Export the mapping XML from Serato (MIDI > Save preset).")
