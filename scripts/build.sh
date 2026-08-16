#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="DJMidiStudio"
BUILD_PY_PACKAGE=1
BUILD_EXECUTABLE=1
MACOS_SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-python-package)
      BUILD_PY_PACKAGE=0
      ;;
    --skip-executable)
      BUILD_EXECUTABLE=0
      ;;
    --sign-identity)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --sign-identity"
        exit 2
      fi
      MACOS_SIGNING_IDENTITY="$2"
      shift
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  scripts/build.sh [--skip-python-package] [--skip-executable]
                    [--sign-identity "Developer ID Application: ..."]

Build outputs:
  - Python package artifacts: dist/*.whl, dist/*.tar.gz
  - Native executable bundle: dist/executables/<os>/
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

cd "$ROOT_DIR"

UNAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$UNAME" in
  darwin*) OS_NAME="macos" ;;
  linux*) OS_NAME="linux" ;;
  msys*|mingw*|cygwin*) OS_NAME="windows" ;;
  *) OS_NAME="$UNAME" ;;
esac

if [[ "$OS_NAME" == "windows" ]]; then
  DATA_SEP=';'
else
  DATA_SEP=':'
fi

if [[ "$BUILD_PY_PACKAGE" -eq 1 ]]; then
  echo "==> Building Python package (wheel + sdist)"
  uv build
fi

if [[ "$BUILD_EXECUTABLE" -eq 1 ]]; then
  echo "==> Building native executable for $OS_NAME"
  OUT_DIR="dist/executables/$OS_NAME"
  rm -rf "$OUT_DIR"
  mkdir -p "$OUT_DIR"

  # Resource paths are relative to ROOT_DIR (the current directory). Using
  # relative paths avoids MSYS/Git Bash converting an absolute /d/... path
  # twice before PyInstaller receives it on Windows.
  uv run pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --distpath "$OUT_DIR" \
    --workpath "$ROOT_DIR/build/pyinstaller" \
    --specpath "$ROOT_DIR/build/pyinstaller" \
    --paths "$ROOT_DIR/src" \
    --add-data "assets${DATA_SEP}assets" \
    --add-data "docs/controllers${DATA_SEP}docs/controllers" \
    --osx-bundle-identifier "com.guillain.djmidi" \
    "$ROOT_DIR/src/djmidi/gui/app.py"

  if [[ "$OS_NAME" == "macos" ]]; then
    APP_PATH="$OUT_DIR/$APP_NAME.app"
    if [[ -n "$MACOS_SIGNING_IDENTITY" ]]; then
      echo "==> Signing macOS app with identity: $MACOS_SIGNING_IDENTITY"
      codesign --deep --force --verbose --options runtime --timestamp \
        --sign "$MACOS_SIGNING_IDENTITY" "$APP_PATH"
      codesign --verify --deep --strict --verbose=2 "$APP_PATH"
    else
      echo "WARNING: macOS app is unsigned (adhoc), not suitable for distribution."
      echo "         Set MACOS_SIGNING_IDENTITY or pass --sign-identity."
    fi
  fi

  echo "Executable output: $OUT_DIR"
fi
