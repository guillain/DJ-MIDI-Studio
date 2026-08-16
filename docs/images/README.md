# Documentation Images 🖼️

This directory contains visual assets used by the documentation. Images are
kept local so the user and developer guides remain useful offline and can be
bundled with the application where appropriate.

## Table of Contents

- [Layout screenshots](#layout-screenshots)
- [Generation](#generation)
- [Usage rules](#usage-rules)

## Layout screenshots

All current UI screenshots are indexed in the [layout screenshot README](layout/README.md).

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
documentation pages and indexes together.
