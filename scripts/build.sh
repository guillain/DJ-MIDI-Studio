#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="SeratoMidiConf"
BUILD_PY_PACKAGE=1
BUILD_EXECUTABLE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-python-package)
      BUILD_PY_PACKAGE=0
      ;;
    --skip-executable)
      BUILD_EXECUTABLE=0
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  scripts/build.sh [--skip-python-package] [--skip-executable]

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

  uv run pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --distpath "$OUT_DIR" \
    --workpath "$ROOT_DIR/build/pyinstaller" \
    --specpath "$ROOT_DIR/build/pyinstaller" \
    --paths "$ROOT_DIR/src" \
    --add-data "$ROOT_DIR/assets${DATA_SEP}assets" \
    "$ROOT_DIR/src/seratomidiconf/gui/app.py"

  echo "Executable output: $OUT_DIR"
fi

