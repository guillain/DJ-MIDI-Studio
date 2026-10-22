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

![Preferences, General tab, in French with Français selected](../../images/layout/interface-language-preferences.png)

## What is translated

This first version translates what you use most:

- the menu bar: `Fichier`, `Édition`, `Affichage`, `Macros`, `Aide` and
  every fixed entry in them;
- the main tabs: `Tableau de bord`, `Config. contrôleur`,
  `Images contrôleur`, `Par canal`, `Par platine`, `Par contrôleur`,
  `Bibliothèque` (kept short so they fit a small window; when they still
  don't, the tab bar shows scroll arrows instead of cutting the names);
- the **● Rec** / **⟳ Sync** buttons and the sync-scene list beside the
  menu bar, with their tooltips, the messages they show in the status bar
  and their questions (replacing a stored sync set, quitting while
  recording);
- the whole Preferences window;
- the first-run setup wizard (`Aide → Configuration initiale…`), the
  `Prêt pour le live` report, the `Test de latence MIDI` and the
  `Carte des couches` windows;
- the whole Music Library tab: the music folders, the table and its
  filters, the `Morceau`, `Catégories`, `Playlists`, `Historique` and `Set`
  panels, the preview bar, the status line and the windows its buttons
  open (except `Trouver les doublons…` and `Bilan de santé…`);
- Qt's own standard buttons and dialogs (`OK`, `Annuler`, `Enregistrer`,
  file pickers).

![The Dashboard in French: menus, tabs, Rec/Sync translated; the tab's content still in English](../../images/layout/interface-language-fr.png)

## What stays in English

The rest of each tab's content, the tool windows (Live Monitor, MIDI
Routing, MIDI Clock, Metronome, Controller Emulator), the Music Library's
duplicates and health-report windows, most other messages and the `?` help
texts are still in English, as is this documentation. Inside the translated
windows, text computed from your data stays in English too: the findings
of the `Prêt pour le live` report, the latency statistics line, the
change-history entry descriptions, the Sync result summary in the status
bar, the Set panel's summary line and transition notes, and the
smart-playlist rule summaries and sort names. They will be
translated over the next releases. Controller and function names that
come from your DJ software or your controller's MIDI documentation are
never translated.

## Related

- [Workspace and preferences](workspace.md#preferences)
- [User guide](../user-guide.md)
