#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_OS=""
BUILD_MISSING=0
ALLOW_UNSIGNED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --os)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --os"
        exit 2
      fi
      TARGET_OS="$2"
      shift
      ;;
    --build-missing)
      BUILD_MISSING=1
      ;;
    --allow-unsigned)
      ALLOW_UNSIGNED=1
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  scripts/release_artifacts.sh [--os macos|linux|windows] [--build-missing]
                                [--allow-unsigned]

Behavior:
  - Defaults to current host OS executable directory in dist/executables/<os>
  - If missing, falls back to the first available OS folder
  - With --build-missing, runs scripts/build.sh --skip-python-package first
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 2
      ;;
  esac
  shift
done

UNAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$UNAME" in
  darwin*) OS_NAME="macos" ;;
  linux*) OS_NAME="linux" ;;
  msys*|mingw*|cygwin*) OS_NAME="windows" ;;
  *) OS_NAME="$UNAME" ;;
esac

if [[ -n "$TARGET_OS" ]]; then
  OS_NAME="$TARGET_OS"
fi

VERSION="$(uv run python - <<'PY'
import tomllib
from pathlib import Path
pyproject = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
print(pyproject['project']['version'])
PY
)"

ARTIFACT_DIR="dist/release"
mkdir -p "$ARTIFACT_DIR"

if [[ "$BUILD_MISSING" -eq 1 && ! -d "dist/executables/$OS_NAME" ]]; then
  echo "No executable directory found for '$OS_NAME'; building it now..."
  bash scripts/build.sh --skip-python-package
fi

if [[ ! -d "dist/executables/$OS_NAME" ]]; then
  FIRST_AVAILABLE="$(find dist/executables -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -n 1 || true)"
  if [[ -n "$FIRST_AVAILABLE" ]]; then
    OS_NAME="$(basename "$FIRST_AVAILABLE")"
    echo "Using available executable directory: dist/executables/$OS_NAME"
  fi
fi

if [[ -d "dist/executables/$OS_NAME" ]]; then
  ARCHIVE_BASE="djmidi-studio-${VERSION}-${OS_NAME}"
  if [[ "$OS_NAME" == "macos" ]]; then
    APP_PATH="dist/executables/$OS_NAME/DJMidiStudio.app"
    if [[ ! -d "$APP_PATH" ]]; then
      echo "Expected macOS app bundle not found: $APP_PATH"
      exit 2
    fi
    SIGNATURE_DETAILS="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1 || true)"
    if ! codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1 \
      || grep -qE 'Signature=adhoc|TeamIdentifier=not set' <<<"$SIGNATURE_DETAILS"; then
      if [[ "$ALLOW_UNSIGNED" -ne 1 ]]; then
        echo "macOS app is unsigned or invalidly signed."
        echo "Build with --sign-identity \"Developer ID Application: ...\"."
        echo "Use --allow-unsigned only for local testing."
        exit 3
      fi
      echo "WARNING: packaging unsigned macOS app because --allow-unsigned was supplied."
    fi
    ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "dist/release/${ARCHIVE_BASE}.zip"
    echo "Created dist/release/${ARCHIVE_BASE}.zip"
  elif [[ "$OS_NAME" == "windows" ]]; then
    (cd dist/executables && zip -r "../release/${ARCHIVE_BASE}.zip" "$OS_NAME")
    echo "Created dist/release/${ARCHIVE_BASE}.zip"
  else
    (cd dist/executables && tar -czf "../release/${ARCHIVE_BASE}.tar.gz" "$OS_NAME")
    echo "Created dist/release/${ARCHIVE_BASE}.tar.gz"
  fi
else
  echo "No executable directory found at dist/executables/$OS_NAME"
  echo "Build one first with: bash scripts/build.sh --skip-python-package"
  echo "Or rerun this command with: --build-missing"
  exit 2
fi
