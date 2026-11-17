# 🩺 Startup check

> What's plugged in, compared with what the app knows about it: each thing
> still missing comes with the one button that finishes it. It opens on its
> own when something new needs you.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Startup check

## Table of Contents

- [What it does](#what-it-does)
- [What it looks at](#what-it-looks-at)
- [When it opens](#when-it-opens)
- [Related](#related)

## What it does

One card per device you have plugged in. Each line says what's missing in
plain words, with a coloured dot and a button:

| Dot | Means |
|---|---|
| 🔴 Red | Something you set up can't work right now |
| 🟠 Amber | It works, but a step is missing |
| 🟢 Green | Ready |

The button opens the tool that finishes that step; nothing is changed until
you use it. **✕** hides a line for good. **Check again** looks at your
devices again after you plug one in.

## What it looks at

| Line | Button |
|---|---|
| A device the app doesn't know | **Teach it**: Controller Setup, to learn its controls by pressing them |
| A controller never checked on your unit | **Check it**: the guided check of every button |
| Its lights were never probed | **Probe its lights**: the Atelier, where each LED can be probed |
| No light scene for it | **Create a scene**: the Atelier's scene designer |
| An IAC bus is offline while macros send to it | **Open Audio MIDI Setup**, to turn the bus on (Window → Show MIDI Studio, IAC Driver, *Device is online*) |
| A macro's port isn't connected | **Edit the macros** |
| A macro's controller is unplugged | Nothing to fix: plug it in |
| A macro's trigger pad is also used by your Serato mapping for that controller (one press would do both) | **Move to …**: moves the trigger to the first free pad of the same mode, in one click |

Serato keeps one mapping file per device in `Music/_Serato_/MIDI/Xml`; only
the files whose name names the controller (`ddj-xp2-custom.xml` for the
DDJ-XP2) are read, never written.

It only reads port names, the app's own files and your Serato mapping files:
no MIDI is sent and nothing outside the app's workspace is written. Only
**Move to …** changes something: that macro's trigger, in the app's own
`Macros` folder.

## When it opens

Plug a device in while the app runs and the check looks again: it opens on
its own when that brings something new.

At startup, when at least one line you haven't hidden needs you — instead
of the Helpful Notes. Untick **Show at startup when something needs you** to
stop that; it's always in **Help → Startup Check…**.

## Related

- [Controller Setup](controller-setup.md)
- [Atelier](atelier.md)
- [MIDI macros](midi-macros.md)
- [First-run setup](first-run-wizard.md)
