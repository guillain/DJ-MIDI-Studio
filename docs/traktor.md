# Traktor integration

DJ MIDI Studio includes a discoverable `traktor` software plugin for Native
Instruments Traktor mapping files.

## Supported files

The plugin accepts the XML-based formats commonly used for Traktor mappings:

- `.nml` and `.tsi` files;
- XML files whose root element is `NML`;
- MIDI NOTE mappings through `<NOTE NOTE="..." />`;
- MIDI CC mappings through `<CC CC="..." />`;
- zero-based Traktor MIDI channels, normalized to the application's
  one-based channel model.

The plugin can export the application's normalized model back to a compact NML
document. `File -> Save` and `File -> Save As...` still apply the normal
validation, diff preview, backup, atomic-write, and rollback safeguards.

## Workflow

1. Open a `.nml`, `.tsi`, or XML mapping from `File -> Open...`.
2. Let the NML signature select Traktor automatically, or choose
   `Native Instruments Traktor` explicitly in the software selector.
3. Inspect the normalized channels and controls in the mapping views.
4. Validate and export the mapping after reviewing the proposed diff.

The integration is intentionally conservative. It preserves mapping names,
deck identifiers, NOTE/CC triggers, and the first supported trigger per
mapping. Traktor features outside the normalized MIDI model—commands with
multiple trigger variants, modifiers, conditions, interaction modes, feedback
LED rules, and non-MIDI command types—are not reconstructed by this first
plugin. Keep the original file as a backup and verify exported mappings in
Traktor before using them in a live setup.

The implementation lives in `src/djmidi/software/traktor.py`; hardware-free
coverage is provided by `tests/test_software_plugins.py` and
`tests/test_integration_detection.py`.
