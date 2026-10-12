# 🏷️ Readable function names

> Serato names each mapped function with an internal tag such as
> `auto_loop_roll_specific_length`. The app shows a short name instead —
> `Loop roll` — and keeps the original tag one hover away.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Readable function names

## Table of Contents

- [Where the short names appear](#where-the-short-names-appear)
- [The names](#the-names)
- [Finding the original tag](#finding-the-original-tag)
- [Related](#related)

## Where the short names appear

- The **By Channel**, **By Deck** and **By Controller** trees of the
  [Mapping editor](mapping-editor.md).
- The **Find function** results — and you can search with either the short
  name or the original tag.
- The [Compare mappings](mapping-diff.md) list
  (`Codfather ST (deck 3, slot 1) -> play (deck 3, slot 1)`).
- The printed [Cheat Sheet](cheat-sheet.md)
  (`Loop roll · slot 3 (D1, D3)`).

## The names

Only the functions found in real Serato mappings have a short name, and
each name comes from the tag's own words — nothing is guessed:

| Short name | Serato tag |
| --- | --- |
| Auto loop | `auto_loop_specific_length` |
| Loop roll | `auto_loop_roll_specific_length` |
| Codfather ST | `codfather_st` |
| Codfather FX | `codfather_fx` |

A slot stays a slot number (`Loop roll · slot 3`): which loop length a
Serato slot stands for isn't documented, so the app doesn't print `1/4` or
`8 beats` it can't verify. Any other function — a Traktor command, or a
Serato tag not in this table — is shown exactly as the file names it.

## Finding the original tag

Nothing is hidden behind a short name:

- in the trees and the Find function list, hover a row: the tooltip shows
  the original tag;
- in Compare mappings, hover the change: the tooltip repeats it with the
  original tags (`Raw: …`);
- typing the original tag in the By Channel filter or in Find function
  still finds the row;
- the cheat sheet ends with a **Function names** page listing each short
  name it used next to its Serato tag.

## Related

- [Mapping editor](mapping-editor.md): the three trees and Find function.
- [Compare mappings](mapping-diff.md): the change list.
- [Cheat Sheet (PDF)](cheat-sheet.md): the printed pages.
