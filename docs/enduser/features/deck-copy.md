# 📋 Copy Deck Mappings

> Copy everything one deck does onto another deck in one go — on the MIDI
> channel the other deck uses — instead of re-creating each function by hand.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Copy Deck Mappings

## Table of Contents

- [Copy a deck](#copy-a-deck)
- [Channels](#channels)
- [Controls the target deck already uses](#controls-the-target-deck-already-uses)
- [What is copied](#what-is-copied)
- [Related](#related)

## Copy a deck

1. Open a Serato mapping (`File → Open Mapping...`).
2. Choose `Edit → Copy Deck Mappings…`.
3. Pick the deck to copy **From** and the deck to copy **To**. Decks are
   numbered as Serato numbers them, from 0, as in the By Deck tab.
4. Check the target channels and read the preview, then click **Copy**.

The whole copy is one step of `Edit → Undo`. Nothing is saved until you
save the mapping.

## Channels

On most controllers each deck sends on its own MIDI channel (in a 4-deck
DDJ-XP2 mapping: deck 0 on channel 8, deck 1 on 10, deck 2 on 12, deck 3
on 14). The table lists every channel the source deck uses, with the
channel its copy goes to: by default the one the target deck already uses.
Change it when the target deck has no mapping yet, or sends on another
channel.

## Controls the target deck already uses

A control (same channel and note) that already has a mapping for the
target deck is **skipped**, and the preview lists it. Tick **Replace the
target deck's mappings on the same controls** to replace them instead: the
target deck's mappings on those controls are removed before the copy.
Other decks' mappings on the same controls are always kept.

## What is copied

Every `<control>` holding a mapping for the source deck is copied: its
note or CC on the new channel, its click and output parts, and only the
source deck's functions, with their slots, behaviours and values. Serato
mappings often repeat each control several times (10 times in a
DDJ-XP2 + XDJ-XZ export); each repetition is copied too, so the copy works
in Serato like the original.

Only Serato mappings can be copied: the Traktor, rekordbox and Mixxx
writers keep their files' structure and refuse added bindings.

## Related

- [Mapping editor](mapping-editor.md)
- [Layer Map](layer-map.md)
- [Mapping diff](mapping-diff.md)
