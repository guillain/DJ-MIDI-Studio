# Declarative Controller Profiles

> 🎛️ Use JSON profiles for predictable static NOTE/CC catalogs. Move to a
> Python plugin when the controller needs custom lookup or behavior.

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
`controllers/ddj-flx10/`, and the annotated first-page diagram is available in
the Controller Images view. Firmware capture is still required before treating
the profile as production-verified.

The Numark Mixtrack Pro FX and Hercules DJControl Inpulse 500 profiles also
include official product-view artwork for physical orientation. These images
help identify the hardware layout but do not replace a vendor MIDI message
list or a hardware capture.

The DDJ-REV1 profile is based on Pioneer DJ's official MIDI Message List E1 and
covers its shared deck transport controls and eight-pad modes, including the
shifted pad channels. Jog, fader, EQ, and FX continuous controls remain out of
the normalized catalog.

The DDJ-FLX4 profile is similarly conservative. It models the common two-deck
and eight-pad layout used by the DDJ-400 family and includes an official
Pioneer product view. Its MIDI values remain provisional until confirmed with
an FLX4 hardware capture or an FLX4-specific MIDI message list.

All six Pioneer pad-grid profiles (`DDJ-XP2`, `XDJ-XZ`, `DDJ-1000`, `DDJ-FLX4`,
`DDJ-REV1`, and `DDJ-FLX10`) resolve pad modes 1 through 8. The DDJ-XP2 also
has dedicated `PAD MODE 1..8` button entries; on hardware, modes 5 through 8
are emitted by the second NOTE in the double-click sequence. The Numark and
Hercules profiles currently expose their verified eight-pad bank only: their
mode-switch messages are not yet documented by a vendor MIDI list or a local
hardware capture, so they are intentionally not guessed.

The Behringer CMD LC-1 has no published MIDI message list. Its profile was
captured from real hardware with Controller Setup (factory settings, MIDI
channel 8) and cross-checked against a real Serato export. Under the eight
encoders, the face is 13 rows of 4 buttons, notes left to right: the buttons
printed 1-8 (notes 16-23), an unlabelled 4x8 grid (32-63), then MUTE (64-67),
SOLO (68-71) and RECORD (72-75). Notes 24-31 are unused. The encoders are
endless rotaries without a push switch (CC from 16 on channel 8) and stay out
of the catalog like every continuous control. LED feedback was checked on
the unit: a Note On sent back on the button's own note lights its LED, which
is the convention Live Monitor and the Controller Emulator assume.

Reference sources:

- [Controller documentation index and official PDF URLs](controllers/README.md)
- [Pioneer DDJ-FLX10 MIDI message list](controllers/ddj-flx10-midi-message-list-e1.pdf)
- [Pioneer DDJ-FLX4 product page](https://www.pioneerdj.com/en/product/dj-controllers/ddj-flx4/)
- [Pioneer DDJ-REV1 MIDI message list](controllers/ddj-rev1-midi-message-list-e1.pdf)
- [Numark Mixtrack Pro FX product page](https://www.numark.com/product/mixtrack-pro-fx)
- [Hercules DJControl Inpulse 500 product page](https://www.hercules.com/en-us/dj-controllers/djcontrol-inpulse-500/)
