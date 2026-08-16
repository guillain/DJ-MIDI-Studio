# Quickstart

> 🚀 Go from zero to the first mapping view in a few commands.

## Table of Contents

- [Requirements](#requirements)
- [Bootstrap (Recommended)](#bootstrap-recommended)
- [Install Dependencies](#install-dependencies)
- [Run the Application](#run-the-application)
- [Run Tests](#run-tests)
- [Useful Test/Build Scripts](#useful-testbuild-scripts)

## Requirements

- Python `>= 3.14`
- `uv` package manager
- OS: macOS, Linux, or Windows (for GUI and packaging)

## Bootstrap (Recommended)

```bash
bash scripts/bootstrap.sh
```

## Install Dependencies

```bash
uv sync --group dev
```

## Run the Application

![DJ MIDI Studio dashboard](images/layout/dashboard.png)

```bash
uv run djmidi
```

## Run Tests

```bash
uv run pytest
```

## Useful Test/Build Scripts

```bash
bash scripts/test.sh quick
bash scripts/test.sh all
bash scripts/build.sh
bash scripts/release_artifacts.sh
```
