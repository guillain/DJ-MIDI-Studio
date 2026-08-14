#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

UNAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$UNAME" in
  darwin*) OS_NAME="macos" ;;
  linux*) OS_NAME="linux" ;;
  msys*|mingw*|cygwin*) OS_NAME="windows" ;;
  *) OS_NAME="$UNAME" ;;
esac

VERSION="$(uv run python - <<'PY'
import tomllib
from pathlib import Path
pyproject = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
print(pyproject['project']['version'])
PY
)"

ARTIFACT_DIR="dist/release"
mkdir -p "$ARTIFACT_DIR"

if [[ -d "dist/executables/$OS_NAME" ]]; then
  ARCHIVE_BASE="seratomidiconf-${VERSION}-${OS_NAME}"
  if [[ "$OS_NAME" == "windows" ]]; then
    (cd dist/executables && zip -r "../release/${ARCHIVE_BASE}.zip" "$OS_NAME")
    echo "Created dist/release/${ARCHIVE_BASE}.zip"
  else
    (cd dist/executables && tar -czf "../release/${ARCHIVE_BASE}.tar.gz" "$OS_NAME")
    echo "Created dist/release/${ARCHIVE_BASE}.tar.gz"
  fi
else
  echo "No executable directory found at dist/executables/$OS_NAME"
  exit 2
fi

