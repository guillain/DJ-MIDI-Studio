# 🧭 First-run setup

> On the very first launch, a short wizard finds your controllers, offers to
> open your Serato MIDI mapping and to record a controller sync set. Every
> step is optional, and you can run it again from the Help menu.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › First-run setup

## Table of Contents

- [When it appears](#when-it-appears)
- [Your controllers](#your-controllers)
- [Your Serato mapping](#your-serato-mapping)
- [Controller sync set](#controller-sync-set)
- [What it never does](#what-it-never-does)
- [Related](#related)

## When it appears

The wizard opens by itself once, the first time DJ MIDI Studio starts on a
computer where it has no preferences yet. Click **Skip** at any step to
close it; finished or skipped, it won't open by itself again. Run it any
time later from `Help → First-Run Setup…`.

## Your controllers

The wizard lists the connected MIDI controllers it recognizes from their
port names, with the ports each one uses. Select the one to show on the
Dashboard; every recognized controller stays available in the other tabs.

Plugged a controller in after opening the wizard? Click **Rescan**. A port
no controller profile recognizes is listed too: build a profile for it in
[Controller Setup](controller-setup.md) by pressing its buttons.

## Your Serato mapping

The wizard looks in Serato's own MIDI folder (`~/Music/_Serato_/MIDI/Xml`)
and lists the mappings it finds there, newest first, with the newest one
selected. Pick one to open it in the [mapping editor](mapping-editor.md), or
pick **Don't open a mapping now**. With no mapping found, use `File → Open`
later to open one from anywhere.

## Controller sync set

Tick **Start recording a sync set when this wizard closes** to record, right
away, the buttons you always press after plugging your controllers in. Press
them, then click **`■ Stop`** at the top right of the window. The set is
saved per controller and replayed by **`⟳ Sync`** — see
[Controller Sync](controller-sync.md).

## What it never does

- It never writes into the Serato folder: it only lists it, and opening a
  mapping only reads the file. Nothing is saved unless you save the mapping
  yourself.
- It only reads MIDI port names to recognize controllers: it sends no MIDI
  and opens no port (recording starts only if you ticked it).

## Related

- [Controller Setup](controller-setup.md)
- [Controller Sync](controller-sync.md)
- [Mapping editor](mapping-editor.md)
- [Workspace and preferences](workspace.md)
