# Build and Release

## Table of Contents

- [Build Targets](#build-targets)
- [Bootstrap](#bootstrap)
- [Local Build Scripts](#local-build-scripts)
- [Executable per OS](#executable-per-os)
- [GitHub Actions Workflow](#github-actions-workflow)
- [Release Artifact Packaging](#release-artifact-packaging)

## Build Targets

The project now supports:

- Python package artifacts (`wheel` + `sdist`)
- Native executable bundles (built on the host OS)

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

## Executable per OS

The executable build is native (PyInstaller), meaning:

- Build macOS executable on macOS
- Build Linux executable on Linux
- Build Windows executable on Windows

Output path:

- `dist/executables/<os>/`

## GitHub Actions Workflow

Workflow file: `.github/workflows/build-executables.yml`

Additional release workflow: `.github/workflows/draft-release.yml` (tag-triggered draft release with attached artifacts).

It builds artifacts on a matrix:

- `ubuntu-latest`
- `macos-latest`
- `windows-latest`

and uploads:

- executable bundles
- wheel/sdist artifacts

## Release Artifact Packaging

Package OS executable directory into an archive:

```bash
bash scripts/release_artifacts.sh
```

Output path:

- `dist/release/`

