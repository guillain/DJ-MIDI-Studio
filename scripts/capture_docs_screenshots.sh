#!/usr/bin/env bash
set -euo pipefail

# A stale VIRTUAL_ENV from an old shell/IDE terminal (e.g. a renamed or
# deleted project directory) makes every `uv` command below print a
# mismatch warning and ignore it anyway -- unset it so `uv` picks this
# project's own .venv cleanly and silently.
unset VIRTUAL_ENV || true

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export QT_QPA_PLATFORM=offscreen
uv run python scripts/capture_docs_screenshots.py "$@"
