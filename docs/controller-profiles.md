# Declarative Controller Profiles

Controller plugins may be supplied as JSON when their behavior is limited to
static NOTE/CC entries. A profile contains a validated [plugin manifest](plugin-manifest.md)
and a `controller` object:

```json
{
  "manifest": {
    "schema_version": 1,
    "plugin_id": "example.controller",
    "kind": "controller",
    "name": "Example Controller",
    "version": "1.0.0",
    "api_version": "1",
    "vendor": "Example",
    "license": "MIT"
  },
  "controller": {
    "name": "Example Controller",
    "supported_software": ["serato"],
    "entries": [
      {
        "section": "DECK",
        "name": "PLAY",
        "note_or_cc": "NOTE",
        "channels": ["1", "2"],
        "data1": "60"
      }
    ]
  }
}
```

Profiles currently support static controls only. Pad formulas, dynamic
software behavior, MIDI routing, and device detection remain Python plugin
capabilities. Every profile must be verified against an official MIDI message
list or a hardware capture before being used for a production mapping.
