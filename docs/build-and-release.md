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

## SCM, tags, and releases

The provider-neutral helper is `scripts/scm_release.sh`. It detects GitHub or
GitLab from the `origin` URL, or can be forced with `SCM_PROVIDER`:

```bash
git switch -c release/1.0.0
# commit the intended changes explicitly
bash scripts/scm_release.sh pr --base main --title "Prepare 1.0.0"

# after the PR/MR is merged
bash scripts/scm_release.sh tag --version 1.0.0
bash scripts/scm_release.sh release --version 1.0.0
```

The script uses `gh` for GitHub and `glab` for GitLab, never stages or commits
files, and requires a clean worktree. Tag pushes trigger the checked-in CI
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

Additional release workflow: `.github/workflows/draft-release.yml` (tag-triggered draft release with attached artifacts).

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
the release quality/build pipeline and creates a draft GitHub Release. Normal
branch pushes validate and build artifacts but never publish a release.

On Ubuntu runners, `python-rtmidi` is compiled against ALSA when no compatible
wheel is available. The CI workflows install `libasound2-dev` and `pkg-config`
before `uv sync`; this is required for the Linux build and quality jobs.

The executable build passes bundled resource directories to PyInstaller as
absolute native paths because PyInstaller resolves data sources relative to
the generated spec directory. On Windows, the script converts paths with
`cygpath` and disables Git Bash/MSYS path rewriting to avoid invalid paths such
as `D:\\d\\...`.

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
