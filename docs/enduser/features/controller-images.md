# 🖼️ Controller Images

> The official diagrams and manuals of every supported controller, zoomable
> and available offline, with an optional overlay of each control's real
> position.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Controller Images

## Table of Contents

- [What it does](#what-it-does)
- [Browse a controller](#browse-a-controller)
- [Show real layout](#show-real-layout)
- [MIDI info](#midi-info)
- [Related](#related)

## What it does

The `Controller Images` tab shows the reference picture of the selected
controller and opens its bundled manual or MIDI message list. Everything is
stored with the app, so it works without an internet connection.

![Controller Images](../../images/layout/controlleur-image.png)

## Browse a controller

Pick a controller, then zoom with the mouse wheel, drag to pan, and
`Reset zoom` to fit. `Open documentation` opens its PDF. A controller
without artwork shows a placeholder instead of a wrong picture; a
controller built in [Controller Setup](controller-setup.md) can carry your
own image.

The same documents are in `Help → Controller References`.

## Show real layout

Tick `Show real layout` to draw a marker on every modeled control at its
true position on the picture. Six controllers are measured: DDJ-XP2,
XDJ-XZ, DDJ-1000, DDJ-FLX10, DDJ-REV1 and Numark Mixtrack Pro FX, with both
decks where the controller has two.

With the [Live Monitor](live-monitor.md) running, a marker flashes when you
hit that control on the hardware, a jog marker turns with the platter, and
LED messages from Serato light it amber.

## MIDI info

When a controller ships a second picture with its MIDI message list
callouts printed on it, `MIDI info` switches to it. The real-layout overlay
only lines up with the clean picture, so it is disabled while `MIDI info` is
on.

## Related

- [Supported controllers](../controller-profiles.md)
- [Controller Emulator](controller-emulator.md)
