# 🔌 Writing a software plugin

> How to add support for another DJ program's MIDI mappings — VirtualDJ,
> Engine DJ… — as a plugin, and check it before anyone reviews it.

📍 [Docs](../../README.md) › [Developer](../README.md) › [Design](README.md) › Writing a software plugin

## Table of Contents

- [What a plugin does](#what-a-plugin-does)
- [Start from the example](#start-from-the-example)
- [The model to produce](#the-model-to-produce)
- [The contract check](#the-contract-check)
- [Saving: patch, don't rebuild](#saving-patch-dont-rebuild)
- [Install and share](#install-and-share)
- [Related](#related)

## What a plugin does

A software plugin is one `SoftwareDefinition`, registered with
`djmidi.software.register(...)`:

| Field | What it is |
| --- | --- |
| `plugin_id`, `name` | A lowercase id (`virtualdj`) and the name the app shows |
| `extensions` | Lowercase file suffixes, each starting with `.` |
| `parser(text) -> MidiConfig` | Reads the program's mapping file into the app's model |
| `exporter(MidiConfig) -> str` | Writes it back; raise `ValueError` for what it can't write |
| `signature(text) -> bool` | Optional: recognizes the format from its content |
| `change_summary(old, new) -> str` | Optional: a readable summary shown before a save |

With that, the app opens the program's mappings in every view (By Channel,
By Deck, By Controller, the emulator, the cheat sheet…), validates them,
compares them and saves them.

**Only from real files.** Every built-in plugin was written against real
exports of its program, and its tests use synthetic files of the same
shape. Never guess a format: a plugin that writes a structure its program
doesn't expect can break the user's setup.

## Start from the example

[`examples/software-plugin`](../../../examples/software-plugin/README.md)
is a complete plugin for a made-up line format, with a sample file and its
packaging. Copy it, rename the package, and replace the parser and exporter
with your program's format.

## The model to produce

`djmidi.model` holds the shape every view reads:

- one `Control(channel, event_type, control)` per MIDI address — channel
  `"1"`..`"16"`, event type `"Note On"`, `"Note Off"`, `"Control Change"`
  or `"Pitch Bend"`, control `"0"`..`"127"`, all as text;
- on it, one `UserIO(event)` per direction: `"click"` (the controller sends
  it) or `"output"` (LED feedback the program sends);
- in each, one `MappingElement(tag=…, deck_id=…)` per function: `tag` is
  the program's own name for it, `deck_id` its deck (or `None`).

Anything else your format carries goes in the `extra_attrs` dictionaries
(text only) — or on the config object itself for large data, as the
Traktor plugin does with its decoded file.

## The contract check

`djmidi.software.check_software_plugin(definition, samples)` runs what the
built-in plugins pass, on your sample files:

| Severity | Meaning |
| --- | --- |
| error | The app would break: the parser raises, an address is out of range, an event isn't `click`/`output`, a function has no name, or a save doesn't parse back to the same bindings |
| warning | Worth fixing: the plugin wouldn't recognize its own sample, or an edited trigger is lost on save |
| info | Fine, documented: an unedited save isn't byte-identical, or the plugin refuses edits (read-only) |

From the command line (exit code 1 when there is an error):

```bash
uv run python scripts/check_software_plugin.py --import my_plugin my-id samples/*.ext
```

Put the same check in your plugin's tests, with every sample you have.

## Saving: patch, don't rebuild

A DJ program's file holds more than the app models (comments, settings,
fields nobody documented). The Traktor and Mixxx plugins therefore change
**only** the bytes of what was edited and keep everything else identical;
an unedited save gives back the very same file. Do the same when you can,
and raise `ValueError` with a clear message for what you can't write yet
(adding a binding, say) rather than approximating it. A read-only plugin is
fine: say so from the exporter.

## Install and share

The app finds external plugins through the `djmidi.software` entry point
group (see the example's `pyproject.toml`), and loads them only when
**Preferences → General → Trust external plugins** is on. To have a plugin
built in, open a pull request with the plugin under `src/djmidi/software/`,
synthetic test files of the real shape, and a note of where the real format
was checked.

## Related

- [Plugin manifest](plugin-manifest.md)
- [Plugins (end-user)](../../enduser/plugins.md)
- [Contributing](../contributing.md)
