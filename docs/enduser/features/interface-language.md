# 🌐 Interface language

> Show DJ MIDI Studio in French (or follow your computer's language)
> instead of English. Chosen in Preferences, applied at the next launch.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Interface language

## Table of Contents

- [Choose a language](#choose-a-language)
- [What is translated](#what-is-translated)
- [What stays in English](#what-stays-in-english)
- [Related](#related)

## Choose a language

Open Preferences with the **⚙** button at the top right, then pick a
`Language` on the `General` tab:

| Choice | Shows |
| --- | --- |
| `English` | English — the default |
| `Français` | French |
| `System` | French when your computer's language is French, English otherwise |

Click `Save`, then quit and restart DJ MIDI Studio: the language is applied
when the app starts. Language names are always written in their own
language, so you can find yours even when you can't read the current one.

## What is translated

This first version translates what you use most:

- the menu bar: `Fichier`, `Édition`, `Affichage`, `Macros`, `Aide` and
  every fixed entry in them;
- the main tabs: `Tableau de bord`, `Configuration du contrôleur`,
  `Images du contrôleur`, `Par canal`, `Par platine`, `Par contrôleur`,
  `Bibliothèque musicale`;
- the **● Rec** / **⟳ Sync** buttons beside the menu bar;
- the whole Preferences window;
- Qt's own standard buttons and dialogs (`OK`, `Annuler`, `Enregistrer`,
  file pickers).

## What stays in English

The content of each tab, the tool windows (Live Monitor, MIDI Routing,
MIDI Clock, Metronome, Controller Emulator), messages and the `?` help
texts are still in English, as is this documentation. They will be
translated over the next releases. Controller and function names that
come from your DJ software or your controller's MIDI documentation are
never translated.

## Related

- [Workspace and preferences](workspace.md#preferences)
- [User guide](../user-guide.md)
