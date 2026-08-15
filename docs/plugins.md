# Plugin installation and trust

DJ MIDI Studio discovers built-in modules automatically. External integrations
are Python packages exposing one of these entry-point groups:

- `djmidi.controllers` for controller catalogs;
- `djmidi.software` for mapping software parsers/exporters.

An external package must expose a versioned `PluginManifest` and use a stable
plugin ID. Its capabilities, permissions, supported formats, and hardware
assumptions should be documented alongside the package.

## Trust policy

External entry points are blocked by default. Enable `Trust external plugins`
in `Settings -> Preferences...` only after reviewing the package source,
manifest, version, vendor, license, and required permissions. The next
application start loads trusted entry points and records failures in the
execution log and discovery diagnostics.

Python plugins run in the application process; this is an admission/trust gate,
not a security sandbox. Do not trust an unreviewed package. A failed external
plugin is reported and does not prevent built-in integrations from loading.

## Updating and troubleshooting

Keep plugin updates pinned and review manifest/API compatibility before
installing them. If discovery fails, inspect the execution log, disable trust,
and use the explicit built-in integration or generic MIDI profile as a
fallback. Plugin enablement and trust choices are stored in the application
preferences JSON file.
