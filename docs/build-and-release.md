# Build and Release

> 📦 **Delivery guide:** build locally, validate continuously, then publish
> reproducible artifacts from an annotated release tag.

## Table of Contents

- [Build Targets](#build-targets)
- [Bootstrap](#bootstrap)
- [Local Build Scripts](#local-build-scripts)
- [Executable per OS](#executable-per-os)
- [SCM, tags, and releases](#scm-tags-and-releases)
- [GitHub Actions Workflow](#github-actions-workflow)
- [Release Artifact Packaging](#release-artifact-packaging)

## Build Targets

The project now supports:

- Python package artifacts (`wheel` + `sdist`)
- Native executable bundles (built on the host OS)

On macOS, an unsigned PyInstaller app is expected to trigger Gatekeeper
warnings. A distributable app must be signed with a Developer ID Application
certificate and notarized by Apple.

The first public CI release uses `--allow-unsigned` because the repository does
not yet have an Apple signing secret configured. Its macOS archive is therefore
for testing and will trigger the expected Gatekeeper warning. Configure a
Developer ID certificate and update the CI secret before treating macOS
artifacts as production-distributable.

## Bootstrap

Run one command to prepare the local environment:

```bash
bash scripts/bootstrap.sh
```

It validates `uv`, installs dependencies, ensures script executability, and installs a quick pre-commit hook.

## Local Build Scripts

Build package + executable:

```bash
bash scripts/build.sh
```

Build only package artifacts:

```bash
bash scripts/build.sh --skip-executable
```

Build only executable artifacts:

```bash
bash scripts/build.sh --skip-python-package
```

Sign a macOS build:

```bash
bash scripts/build.sh --skip-python-package \
  --sign-identity "Developer ID Application: Your Name (TEAMID)"
```

The identity can also be supplied with `MACOS_SIGNING_IDENTITY`. Inspect
available identities with:

```bash
security find-identity -v -p codesigning
```

## Executable per OS

The executable build is native (PyInstaller), meaning:

- Build macOS executable on macOS
- Build Linux executable on Linux
- Build Windows executable on Windows

Output path:

- `dist/executables/<os>/`

The macOS release script creates a `.zip` containing the `.app` bundle so its
metadata is preserved for Gatekeeper and notarization. Unsigned packaging
requires the explicit `--allow-unsigned` flag and is intended only for local
testing.

Windows packaging runs under Git Bash in CI, but uses PowerShell's native
`Compress-Archive` instead of assuming that the Unix `zip` command exists on
the runner.

The executable build explicitly collects the dynamically discovered
`djmidi.catalog` and `djmidi.software` submodules.  PyInstaller cannot infer
modules imported through `pkgutil`, so omitting these collection directives
produces a binary whose controller registry is empty at startup.  The GUI
also shows a diagnostic placeholder instead of crashing if a future plugin
discovery failure leaves the registry empty.

The build also explicitly collects `mido.backends` and the native `rtmidi`
module.  Mido selects its default backend by importing the backend name at
runtime; without these hidden imports, the packaged application starts but
crashes as soon as Live Monitor enumerates MIDI ports.

The headless smoke mode sets `DJMIDI_DISABLE_MIDI=1`. This avoids a
platform-level RtMidi abort on public runners without CoreMIDI/ALSA while
preserving normal hardware probing for user launches. The release build job
installs its own Linux ALSA/Qt dependencies because matrix jobs do not share
the quality job's filesystem or packages.

Every CI and release build runs `scripts/smoke_test_executable.py` after
PyInstaller. It starts the native executable for six seconds, checks that it
does not exit during startup or emit import/traceback errors, and then stops
it. This catches missing frozen modules such as the Mido/rtmidi backend before
an artifact is uploaded.

The application log path is also resilient to stale permissions: if the
platform-specific user log cannot be opened, the executable falls back to the
system temporary directory.  Set `DJMIDI_LOG_DIR` when a deterministic log
location is required; an explicitly supplied log path remains strict and
reports permission errors.

## SCM, tags, and releases

The provider-neutral helper is `scripts/scm_release.sh`. It detects GitHub or
GitLab from the `origin` URL, or can be forced with `SCM_PROVIDER`:

```bash
git switch -c release/0.44.0
bash scripts/scm_release.sh prepare --version 0.44.0 --base main

# For an already prepared branch, open only the PR/MR:
bash scripts/scm_release.sh pr --base main --title "Prepare 0.44.0"
```

The `prepare` command updates `pyproject.toml` and `uv.lock`, creates the
release commit, generates a PR/MR description from the included commits, and
pushes the current branch. The script uses `gh` for GitHub and `glab` for
GitLab, and requires a clean worktree. Tag pushes trigger the checked-in CI
configuration (`.github/workflows/draft-release.yml` or `.gitlab-ci.yml`), which
builds Linux, macOS, and Windows artifacts and attaches them to the release.
The CI runners must have `uv`; macOS additionally needs a Developer ID
certificate configured so the release job does not reject the app as unsigned.

## GitHub Actions Workflow

Workflow file: `.github/workflows/build-executables.yml`

The CI pipeline runs automatically on every branch push and Pull Request. It
first runs the quality gate on Ubuntu, including the ALSA build dependencies,
then builds the native executable and Python artifacts on Ubuntu, macOS, and
Windows. It also remains available through **Run workflow** for a manual
execution.

Additional release workflow: `.github/workflows/draft-release.yml` (tag-triggered published release with attached artifacts).

Merge-to-release workflow: `.github/workflows/tag-release-on-merge.yml`
(release PR merge → annotated tag → reusable artifact build → published
release). The direct workflow call is intentional: tags pushed by
`GITHUB_TOKEN` do not recursively trigger another workflow.

For recovery, run `Draft Release` manually with an existing tag such as
`v0.44.0`; the workflow accepts the tag as a required input and rebuilds all
assets.

It builds artifacts on a matrix:

- `ubuntu-latest`
- `macos-latest`
- `windows-latest`

and uploads:

- executable bundles
- wheel/sdist artifacts
- documentation screenshots generated from `data/xdj_xz-ddj_xp2-4decks.xml`, including canonical docked and floating MIDI-tool compositions

The tag-triggered workflow runs the quality gate before the build matrix and
regenerates the screenshots in a hardware-free Qt job. GitHub attaches the
generated PNGs to the draft release; GitLab retains them as the screenshots
job artifact.

The CD workflow is deliberately tag-only: pushing a tag matching `v*` runs
the release quality/build pipeline and creates a published GitHub Release. Normal
branch pushes validate and build artifacts but never publish a release.

On Ubuntu runners, `python-rtmidi` is compiled against ALSA when no compatible
wheel is available, and PySide6 needs the system EGL/GL libraries even for
headless tests. The CI workflows install `libasound2-dev`, `pkg-config`,
`libegl1`, `libgl1`, and the XKB libraries before `uv sync`; quality jobs also
set `QT_QPA_PLATFORM=offscreen`.

The executable build passes bundled resource directories to PyInstaller as
absolute native paths because PyInstaller resolves data sources relative to
the generated spec directory. On Windows, the script converts paths with
`cygpath` and disables Git Bash/MSYS path rewriting to avoid invalid paths such
as `D:\\d\\...`.

The GitHub setup and artifact actions use Node.js 24-compatible major versions
(`setup-uv@v9.0.0`, `upload-artifact@v7`, and `download-artifact@v8`). This changes
the Actions runtime only; Node.js is not added to the DJ MIDI Studio
application.

## Release Artifact Packaging

Package OS executable directory into an archive:

```bash
bash scripts/release_artifacts.sh
```

Explicit target OS (useful when packaging artifacts built on CI machines and copied locally):

```bash
bash scripts/release_artifacts.sh --os macos
```

Auto-build current OS executable if missing:

```bash
bash scripts/release_artifacts.sh --build-missing
```

If the current host OS folder is missing, the script falls back to the first
available folder under `dist/executables/` and prints which one it used.

Output path:

- `dist/release/`
