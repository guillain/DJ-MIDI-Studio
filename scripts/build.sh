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
  NATIVE_ROOT_DIR="$(cygpath -w "$ROOT_DIR")"
  PYINSTALLER_COMMAND=(env MSYS_NO_PATHCONV=1 uv run pyinstaller)
else
  DATA_SEP=':'
  NATIVE_ROOT_DIR="$ROOT_DIR"
  PYINSTALLER_COMMAND=(uv run pyinstaller)
fi

if [[ "$BUILD_PY_PACKAGE" -eq 1 ]]; then
  echo "==> Building Python package (wheel + sdist)"
  uv build
fi

if [[ "$BUILD_EXECUTABLE" -eq 1 ]]; then
  echo "==> Building native executable for $OS_NAME"
  OUT_DIR="dist/executables/$OS_NAME"
  if [[ "$OS_NAME" == "windows" ]]; then
    NATIVE_OUT_DIR="$(cygpath -w "$OUT_DIR")"
  else
    NATIVE_OUT_DIR="$OUT_DIR"
  fi
  rm -rf "$OUT_DIR"
  mkdir -p "$OUT_DIR"

  # PyInstaller resolves --add-data sources relative to the generated spec
  # directory, not the shell's current directory. Use absolute native paths;
  # MSYS_NO_PATHCONV prevents Git Bash from converting Windows paths twice.
  "${PYINSTALLER_COMMAND[@]}" \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --distpath "$NATIVE_OUT_DIR" \
    --workpath "$NATIVE_ROOT_DIR/build/pyinstaller" \
    --specpath "$NATIVE_ROOT_DIR/build/pyinstaller" \
    --paths "$NATIVE_ROOT_DIR/src" \
    --collect-submodules djmidi.catalog \
    --collect-submodules djmidi.software \
    --collect-submodules mido.backends \
    --hidden-import rtmidi \
    --add-data "$NATIVE_ROOT_DIR/assets${DATA_SEP}assets" \
    --add-data "$NATIVE_ROOT_DIR/docs/controllers${DATA_SEP}docs/controllers" \
    --osx-bundle-identifier "com.guillain.djmidi" \
    "$NATIVE_ROOT_DIR/src/djmidi/gui/app.py"

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
