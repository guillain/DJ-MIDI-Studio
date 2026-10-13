# ⏱️ MIDI Latency Test

> Time how long a MIDI message takes to go out and come back, over a run of
> pings: min, median, max and jitter — through a port or a device that
> echoes what it receives.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › MIDI Latency Test

## Table of Contents

- [It needs an echo](#it-needs-an-echo)
- [Run a test](#run-a-test)
- [Reading the results](#reading-the-results)
- [What the test sends](#what-the-test-sends)
- [Related](#related)

## It needs an echo

The test sends a `Note On` to an output port and waits for the same note to
come back on an input port. **The result only means something when the
message actually comes back**:

- a **loopback port** chosen as both output and input — on macOS the
  **IAC Driver** bus (enable it in *Audio MIDI Setup*), or a virtual MIDI
  cable on Windows;
- a **MIDI thru** (an interface or a cable patched back to your computer);
- a controller you **know** sends back the LED messages it receives.

Most DJ controllers do **not** echo: their LED lights up, but nothing comes
back to the computer, so every ping times out. That says nothing about the
controller's real latency — only that this test can't measure it. The app
never assumes a controller echoes.

## Run a test

Open **`View` → `MIDI Latency Test…`**:

1. Pick the **output** to send to and the **input** to listen on. When a
   port has the same name on both sides (an IAC bus, a virtual cable), the
   input is chosen for you. `⟳` refreshes the lists.
2. Set the number of **pings** (1–1000), the **channel** and **note** to
   use, the **interval** between two pings and the **timeout** after which a
   ping counts as lost.
3. Click **`Start`**. Each finished ping is listed as it comes in; `Stop`
   ends the run early.

The window can stay open while you keep working; the test runs in the
background.

## Reading the results

When the run ends the summary shows how many pings came back, the share
lost, and over the replies:

- **min / median / max**: the round-trip time in milliseconds — out
  through the output *and* back through the input, so roughly twice the
  one-way delay;
- **jitter**: the average change from one ping's time to the next — how
  steady the timing is.

`No reply … does not seem to echo` means nothing came back at all: check
the ports, or see [It needs an echo](#it-needs-an-echo).

## What the test sends

Each ping is a `Note On` on the chosen channel and note, followed by a
`Note Off` once it is answered or timed out, so an echoing LED isn't left
lit. Each ping uses its own velocity (1, 2, 3 … 127, then again) and, by
default, only a reply carrying that velocity counts — so a slow echo of a
ping that already timed out is never taken for the next one. Untick
**`Reply must carry the ping's velocity`** for a device that echoes a
different value. Pick a note your DJ software doesn't use if it listens on
the same port.

## Related

- [Live Monitor](live-monitor.md): see what actually comes back on an input.
- [MIDI Routing, Clock and Metronome](midi-routing-and-clock.md): route or loop MIDI between ports.
- [MIDI Macros](midi-macros.md): send a fixed list of messages by hand.
