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

The complete source and archive status for every built-in controller is
maintained in the [controller documentation index](controllers/README.md).
DDJ-XP2 and XDJ-XZ currently point to their official online MIDI message
lists, while DDJ-1000 and DDJ-FLX10 also keep local PDF copies. The remaining
profiles are explicitly marked there when only a product page, user guide, or
product sheet is available.

The DDJ-FLX10 currently ships as a conservative Python profile covering common
discrete deck and pad triggers. Its official MIDI message list is archived in
`docs/controllers/`, and the annotated first-page diagram is available in the
Controller Images view. Firmware capture is still required before treating the
profile as production-verified.

The Numark Mixtrack Pro FX and Hercules DJControl Inpulse 500 profiles also
include official product-view artwork for physical orientation. These images
help identify the hardware layout but do not replace a vendor MIDI message
list or a hardware capture.

The DDJ-FLX4 profile is similarly conservative. It models the common two-deck
and eight-pad layout used by the DDJ-400 family and includes an official
Pioneer product view. Its MIDI values remain provisional until confirmed with
an FLX4 hardware capture or an FLX4-specific MIDI message list.

Reference sources:

- [Controller documentation index and official PDF URLs](controllers/README.md)
- [Pioneer DDJ-FLX10 MIDI message list](controllers/ddj-flx10-midi-message-list-e1.pdf)
- [Pioneer DDJ-FLX4 product page](https://www.pioneerdj.com/en/product/dj-controllers/ddj-flx4/)
- [Numark Mixtrack Pro FX product page](https://www.numark.com/product/mixtrack-pro-fx)
- [Hercules DJControl Inpulse 500 product page](https://www.hercules.com/en-us/dj-controllers/djcontrol-inpulse-500/)
