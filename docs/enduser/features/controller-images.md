# 🖼️ Controller Images

> The official diagrams and manuals of every supported controller, zoomable
> and available offline, with an optional overlay of each control's real
> position.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Controller Images

## Table of Contents

- [What it does](#what-it-does)
- [Browse a controller](#browse-a-controller)
- [Display layers](#display-layers)
- [Place the controls of your own profile](#place-the-controls-of-your-own-profile)
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

## Display layers

Every controller view (this tab, the `By Channel` / `By Deck` /
`By Controller` drawings and every [Controller
Emulator](controller-emulator.md)) has the same three layer checkboxes:

| Layer | Shows |
| --- | --- |
| `Controller` | The real photo of the controller |
| `MIDI` | The same controller with its MIDI message list callouts printed on it, when it ships one |
| `Layout` | The app's MIDI layout: a marker on every modeled control at its true position |

Only one photo shows at a time: ticking `MIDI` unticks `Controller` and the
other way round, and both can be off. The layout was measured on the
`Controller` photo, so it is greyed out while `MIDI` is shown. That gives
photo only, layout only, photo + layout, or the MIDI picture alone. Here the
layout starts off; in the other views it starts on, over the photo.

Every built-in controller has a measured layout: DDJ-XP2, XDJ-XZ, DDJ-1000,
DDJ-FLX10, DDJ-FLX4, DDJ-REV1, DDJ-REV5, DDJ-800, Numark Mixtrack Pro FX,
Hercules DJControl Inpulse 500, Behringer CMD LC-1, CMD Micro and CMD
Studio 4a, and Korg nanoPAD2, with both decks where the controller has two.
A controller profile you build yourself shows its photo here, and a grid in
the other views.

With the [Live Monitor](live-monitor.md) running, a marker flashes when you
hit that control on the hardware, a jog marker turns with the platter, and
LED messages from Serato light it amber.

## Place the controls of your own profile

A profile you installed — from the
[profile library](../controller-profiles.md#profile-library-rekordbox-devices)
or made in [Controller Setup](controller-setup.md) — starts without a
picture, so the layout views show it as a grid of controls. Give it its real
layout yourself:

1. Pick the controller here and click **`Place controls…`** (or
   **`File` → `Controller Profile` → `Place Controls on a Picture…`**).
2. **`Choose picture…`**: a flat, top-down photo or drawing of the
   controller works best.
3. The list holds one entry per physical control (a pad's modes and a
   button's SHIFT layer share it). Pick one, then drag a box over that
   control on the picture — or just click it for a standard-size box. The
   next control to place is selected for you; `Shape` switches between a
   rectangle and a circle, `Remove box` clears one.
4. **`Save`**: the picture is copied next to the profile and the boxes are
   stored in it.

From then on the controller shows on its picture here (`Layout` layer), in
By Channel / By Deck / By Controller, in the
[Controller Emulator](controller-emulator.md), in live MIDI highlights and
on the printable [cheat sheet](cheat-sheet.md), exactly like a built-in
controller. You can place only the controls you care about; the others keep
working, just without a marker. Built-in controllers already have their
layout and can't be edited.

## Related

- [Supported controllers](../controller-profiles.md)
- [Controller Emulator](controller-emulator.md)
