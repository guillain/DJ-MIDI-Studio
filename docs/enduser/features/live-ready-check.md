# ✅ Ready for live

> One click before a gig: the app reads your mapping and lists what could
> surprise you on stage — a deck without Play, Cue, Sync or Load, a control
> that fires two functions at once, a button that won't light. It explains
> each finding and never changes anything for you.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Ready for live

## Table of Contents

- [Running the check](#running-the-check)
- [What it looks for](#what-it-looks-for)
- [Reading the report](#reading-the-report)
- [What it never does](#what-it-never-does)
- [Related](#related)

## Running the check

Open a mapping, then either:

- click **Ready for live…** above the validation table, in the right-hand
  column of the By Channel, By Deck and By Controller tabs, or
- choose `Edit → Ready for Live…`.

A report window opens; you can keep it open next to the editor. Run the
check again after a change to refresh it.

## What it looks for

| Severity | Finding | Why it matters |
| --- | --- | --- |
| Error | One control fires **several functions on the same deck** | Pressing it on stage triggers all of them at once |
| Error | The **copies of one control disagree** | Serato honours only one copy, so the control may not do what you expect |
| Warning | A deck has **no Play, Cue, Sync or Load** mapping | The minimum you need on every deck you play |
| Info | A button's function can light up, but it has **no LED feedback** mapping | It works, but won't show its state |

A few details:

- **Essential functions** are recognised from the words of the mapped
  function's name (`Play/Pause` counts as Play, `Sync On` as Sync, a hot cue
  doesn't count as Cue). Only the buttons you press count, not LED feedback.
- A Serato mapping file only lists the controls **you remapped**. If
  Serato's built-in support for your controller already gives you Play,
  Cue, Sync and Load, the warnings about them are expected — that's why
  they are warnings, not errors.
- Serato repeats every control several times in a mapping file. Identical
  copies are normal and never reported.
- The LED check only flags a function the app has evidence can light up:
  one your file already maps as LED feedback somewhere, or one seen with LED
  feedback in real Serato mappings (Auto loop, Codfather ST, Codfather FX).
- Decks are numbered as in the **By Deck** tab (Serato counts from 0).

## Reading the report

The top line gives the verdict: **Ready for live**, **Check before
playing** (warnings only) or **Not ready** (at least one error). Below it:

- one check box per severity, with its count, to hide a kind of finding;
- one row per finding: its severity, what's wrong, and what to do;
- **Show control** (or a double-click) selects the control in By Channel
  so you can fix it in the editor;
- **Copy report** copies the whole list as text, to keep or share.

## What it never does

The check is read-only. It never edits, deduplicates or saves your mapping
and never sends MIDI: every fix stays your decision, made in the editor
with Undo available as usual.

## Related

- [Mapping editor](mapping-editor.md): editing, `Edit → Validate` and saving.
- [Readable function names](function-names.md): the short names used in
  the report.
- [Live Monitor](live-monitor.md): check what a control really sends.
