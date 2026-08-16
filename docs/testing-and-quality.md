# Testing and Quality

> 🧪 Fast feedback locally, the same quality gate in CI, and hardware checks
> kept explicit when they cannot be simulated reliably.

## Table of Contents

- [Quality Goals](#quality-goals)
- [Command Reference](#command-reference)
- [Bash Test Script](#bash-test-script)
- [CI Recommendation](#ci-recommendation)

## Quality Goals

- Keep XML parse/export behavior stable.
- Preserve GUI editing behavior and selection synchronization.
- Preserve originating-tab navigation and faded layout selection history.
- Keep Dashboard controller cards in a three-column grid and Physical control details readable.
- Prevent regressions in catalog registration and lookup.

## Command Reference

```bash
uv run ruff check src tests
uv run pytest
uv run pytest -q tests/test_parser.py tests/test_exporter.py
```

## Bash Test Script

Use `scripts/test.sh` for common flows:

```bash
bash scripts/test.sh all
bash scripts/test.sh quick
bash scripts/test.sh quality
bash scripts/test.sh path tests/test_main_window.py
```

Modes:

- `all`: lint + full tests
- `quick`: lint + fast smoke subset
- `lint`: lint only
- `test`: tests only
- `path <target>`: targeted pytest execution
- `quality`: objective gate (coverage/smell/duplication/security)

## CI Recommendation

Run locally before opening a Pull Request:

1. `bash scripts/test.sh quick` for fast feedback.
2. `bash scripts/test.sh quality` for the complete local gate.

GitHub Actions runs the quality gate automatically on every branch push and
Pull Request, then builds the native executable and Python artifacts on
Ubuntu, macOS, and Windows. The release workflow is intentionally separate:
only annotated tags matching `v*` create draft releases.

The Ubuntu jobs install ALSA and Qt/OpenGL runtime packages and set
`QT_QPA_PLATFORM=offscreen`, so the PySide6 test suite can run without a
display server. The GitHub setup actions use their Node.js 24-compatible
versions; this changes the Actions runtime only and does not add Node.js to
the DJ MIDI Studio application.
