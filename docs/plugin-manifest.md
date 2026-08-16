# Plugin Manifest

> 🧩 A manifest is the plugin's identity card: stable ID, compatibility,
> capabilities, permissions, and versioned API contract.

## Table of Contents

- [Purpose](#purpose)
- [Required Fields](#required-fields)
- [Capabilities and Permissions](#capabilities-and-permissions)
- [Validation](#validation)

## Purpose

Every external controller or DJ software integration will declare its identity
and compatibility before it is loaded. The current manifest schema is version
`1` and is implemented by `djmidi.plugins.PluginManifest`.

## Required Fields

```json
{
  "schema_version": 1,
  "plugin_id": "example.controller",
  "kind": "controller",
  "name": "Example Controller",
  "version": "1.0.0",
  "api_version": "1",
  "vendor": "Example",
  "license": "MIT",
  "min_app_version": "0.1.0",
  "capabilities": ["midi.input", "catalog.lookup"],
  "permissions": ["midi.read"]
}
```

`kind` is either `controller` or `software`. `plugin_id` is a stable lowercase
identifier and must not contain spaces.

## Capabilities and Permissions

Capabilities describe what an integration can do, for example
`midi.input`, `midi.output`, `mapping.parse`, `mapping.export`, or
`clock.route`. Permissions describe what it may access, for example
`midi.read`, `midi.write`, or `filesystem.mapping.write`.

The permission model is descriptive for now. Loading third-party Python code
is not sandboxed yet; trust and isolation controls remain a later phase.

## Validation

Malformed JSON, missing required fields, unsupported schema versions, invalid
plugin identifiers, unknown kinds, and malformed capability/permission lists
are rejected before registration.
