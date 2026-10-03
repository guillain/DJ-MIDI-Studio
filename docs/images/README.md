# Documentation Images 🖼️

📍 [Docs](../README.md) › Images

This directory contains visual assets used by the documentation. Images are
kept local so the user and developer guides remain useful offline and can be
bundled with the application where appropriate.

## Table of Contents

- [In this section](#in-this-section)
- [Generation](#generation)
- [Usage rules](#usage-rules)

## In this section

| Index | What it covers |
| --- | --- |
| [Layout screenshots](layout/README.md) | Every screenshot of the app's tabs, tools, dialogs and windows |
| [Controller gallery](controllers/README.md) | One Controller Emulator screenshot per built-in controller |

## Generation

Screenshots are generated without MIDI hardware from the reference mapping:

```bash
QT_QPA_PLATFORM=offscreen uv run python scripts/capture_docs_screenshots.py
```

The release workflow regenerates and publishes these screenshots as release
artifacts.

## Usage rules

Use screenshots to explain stable application behavior and window compositions.
When the UI changes, regenerate the affected images and update the relevant
documentation pages and indexes together. The test suite
(`tests/test_docs.py`) fails on any image link that no longer resolves.
