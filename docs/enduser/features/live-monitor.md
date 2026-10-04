# 📡 Live Monitor

> See every MIDI message your controllers send, in real time, already
> translated into the physical control and the DJ-software function it
> triggers. The whole app reacts as you play.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Live Monitor

## Table of Contents

- [What it does](#what-it-does)
- [Start monitoring](#start-monitoring)
- [Read the event log](#read-the-event-log)
- [The whole app lights up](#the-whole-app-lights-up)
- [See what Serato sends back (LED feedback)](#see-what-serato-sends-back-led-feedback)
- [Limits](#limits)
- [Related](#related)

## What it does

Live Monitor listens to your MIDI inputs and logs each event with its
source device, channel and value, plus the **physical control** (`PAD ·
Pad 3`) and the **mapped function** from the loaded mapping. Every live
event also drives the controller layouts, the [Controller
Images](controller-images.md) overlay and every open [Controller
Emulator](controller-emulator.md), so the screen mirrors what your hands do
on the hardware.

![Live Monitor](../../images/layout/live-monitor.png)

## Start monitoring

By default there is nothing to start: as soon as a mapping is loaded, the
app listens on every available MIDI input (⚙ Preferences → `Auto-start Live
Monitor when a mapping is loaded`, on by default). A port that is busy is
skipped quietly.

To choose ports yourself, open `View → Live Monitor`, then:

1. `Refresh ports`, then tick the inputs to watch (or `Select all sources`).
2. Click `Start monitoring`.
3. Press a button or pad on the controller.

Your manual port choice is never overridden by the auto-start.

## Read the event log

| Column | Meaning |
| --- | --- |
| Time | When the message arrived |
| Dir | `in` (controller → computer) or `out` (software → controller) |
| Source device | The MIDI port it came from |
| Channel, Type, Data1, Data2 | The raw MIDI message (Note On/Off or Control Change, number, value) |
| Physical / Serato | The physical control, then the mapped function |

Physical names are matched against the source device, so a pad on one
controller is never mistaken for the same note on another one.
`Clear log` empties the table; `Save log…` exports it. `Sync controllers`
runs [Controller Sync](controller-sync.md).

## The whole app lights up

For the controller each view is showing:

| You do | The screen shows |
| --- | --- |
| Hit a pad or button | The red selection border jumps to it and the glyph flashes white |
| Hold a button down | A steady amber "held" highlight until you release it |
| Turn a knob, move a fader | The knob rotates / the fader thumb moves, and stays where you left it |
| Spin a jog wheel | The jog glyph turns (XDJ-XZ, DDJ-1000, DDJ-FLX10, DDJ-REV1) |

## See what Serato sends back (LED feedback)

DJ software lights the controller's LEDs by sending MIDI *out* to it. macOS
doesn't let a third app see that traffic directly, so add the app's virtual
port **`DJMidiStudio Monitor`** as an *extra* MIDI output in Serato's MIDI
settings. LED messages then appear as `out` events and latch the same amber
highlight on screen until Serato switches the LED off.

## Limits

- VU meters don't react: no level data is available to drive them.
- An LED is matched on the same note number as the button that triggers it,
  which is Serato's usual convention.

## Related

- [Controller Emulator](controller-emulator.md): the same live feedback on
  an interactive schematic.
- [Controller Sync](controller-sync.md): the `Sync controllers` button.
- [MIDI Routing and Clock](midi-routing-and-clock.md): forward MIDI between
  devices.
