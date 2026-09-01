# Developer Setup 🧰

> A reproducible local environment for coding, testing, documentation, and
> optional MIDI hardware work.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Bootstrap the repository](#bootstrap-the-repository)
- [Run the application](#run-the-application)
- [Run checks](#run-checks)
- [Ableton Link support](#ableton-link-support)
- [Hardware notes](#hardware-notes)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Python `3.14` or newer.
- [`uv`](https://docs.astral.sh/uv/) for environment and dependency management.
- Git.
- A MIDI device is optional; most tests and screenshots run without hardware.

On Linux CI or headless Linux development, install the system ALSA, EGL,
OpenGL, and XKB packages required by `python-rtmidi` and PySide6.

## Bootstrap the repository

```bash
git clone https://github.com/guillain/DJ-MIDI-Studio.git
cd DJ-MIDI-Studio
bash scripts/bootstrap.sh
```

The manual equivalent installs the native Ableton Link binding used by local
and packaged runs:

```bash
uv sync --group dev
```

Keep generated environments, caches, logs, and build output outside commits.
Do not commit real Serato mappings, private MIDI captures, or credentials.

## Run the application

```bash
uv run djmidi
uv run djmidi --log-level DEBUG --log-file /tmp/djmidi.log
```

Useful local resources are the [Quickstart](../quickstart.md), [User Guide](../user-guide.md),
and [Architecture](../architecture.md).

## Run checks

```bash
bash scripts/test.sh quick       # fast feedback
bash scripts/test.sh all         # lint + complete test suite
bash scripts/test.sh quality     # coverage, smell, duplication, security
bash scripts/test.sh path tests/test_parser.py
```

Before opening a pull request, run at least `quick`; run `quality` when
changing core behavior, dependencies, packaging, or security-sensitive code.

The raw test runner is also available directly:

```bash
uv run pytest
uv run pytest tests/test_parser.py -k roundtrip
```

## Build and packaging scripts

All under `scripts/`, mirroring what CI runs:

- `scripts/bootstrap.sh` — one-command local setup plus the pre-commit quick-check hook.
- `scripts/test.sh` — lint/test entrypoint (`all`, `quick`, `lint`, `test`, `path`).
- `scripts/quality_gate.py` / `scripts/quality_gate.sh` — coverage, maintainability, duplication, and security gate.
- `scripts/capture_docs_screenshots.py` — regenerates the UI screenshots from the reference XML, no MIDI hardware needed.
- `scripts/build.sh` — build the wheel/sdist and the native executable bundle for the current OS.
- `scripts/release_artifacts.sh` — archive the OS-specific executable artifacts.
- `.github/workflows/build-executables.yml` — the CI matrix build for macOS/Linux/Windows executables.

```bash
bash scripts/build.sh
bash scripts/release_artifacts.sh
```

## Ableton Link support

```bash
uv sync --group dev
```

The native `aalink` binding is installed by the standard development
environment and included in packaged builds.

## Hardware notes

Use [Controller Setup](../user-guide.md) to learn unknown MIDI controls and
save a draft before generating a catalog module. Use the macOS IAC Driver or
another virtual MIDI port for repeatable tests when physical hardware is not
available. Hardware-dependent claims must be labeled as verified, provisional,
or not tested.

## Troubleshooting

- Inspect the application log; set `DJMIDI_LOG_DIR` for a deterministic log
  directory.
- Set `QT_QPA_PLATFORM=offscreen` for headless Qt tests.
- If MIDI is unavailable, continue with parser/exporter and GUI tests; do not
  weaken a test merely to hide a missing hardware service.
- See [Build and Release](../build-and-release.md) for packaging dependencies
  and smoke tests.
