# Testing and Quality

> 🧪 Fast feedback locally, the same quality gate in CI, and hardware checks
> kept explicit when they cannot be simulated reliably.

📍 [Docs](../../README.md) › [Developer](../README.md) › [CI/CD](README.md) › Testing and Quality

## Table of Contents

- [Quality Goals](#quality-goals)
- [Command Reference](#command-reference)
- [Bash Test Script](#bash-test-script)
- [Performance budget](#performance-budget)
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

## Performance budget

The Music Library has to stay usable on a large collection (the
maintainer's has 85,000 tracks). Wall-clock limits would be flaky in CI,
so `tests/test_library_perf_budget.py` counts operations instead, on a
synthetic 20,000-track index:

| Budget | Why |
| --- | --- |
| Category resolutions < tracks / 3 | `consolidate` memoizes by the folder's first two segments |
| No `Path.relative_to` while building rows | `folder_hint`'s string fast path |
| Python `data()` calls while sorting and filtering < one per track | the model sorts itself, filters read rows and cached text directly |
| No re-filtering on a filter change that changes nothing | the proxy's setters skip no-ops |

A budget fails only on a real regression, with the old cost far above it.
For seconds, run `uv run python scripts/benchmark_library.py` (85,000
tracks by default) before and after a change to the library's load or
filter path.

## CI Recommendation

Run locally before opening a Pull Request:

1. `bash scripts/test.sh quick` for fast feedback.
2. `bash scripts/test.sh quality` for the complete local gate.

GitHub Actions runs the quality gate automatically on every branch push and
Pull Request, then builds the native executable and Python artifacts on
Ubuntu, macOS, and Windows. The release workflow is intentionally separate:
only annotated tags matching `v*` create published releases.

For a successful push to a non-`main` branch, the final CI job checks for an
existing open Pull Request and creates one with the commit summary when none
exists. Existing PRs are left untouched, so subsequent pushes only update the
same review.

The Ubuntu jobs install ALSA and Qt/OpenGL runtime packages and set
`QT_QPA_PLATFORM=offscreen`, so the PySide6 test suite can run without a
display server. The GitHub setup actions use their Node.js 24-compatible
versions; this changes the Actions runtime only and does not add Node.js to
the DJ MIDI Studio application.
