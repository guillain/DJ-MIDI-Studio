#!/usr/bin/env bash
set -euo pipefail

# A stale VIRTUAL_ENV from an old shell/IDE terminal (e.g. a renamed or
# deleted project directory) makes every `uv` command below print a
# mismatch warning and ignore it anyway -- unset it so `uv` picks this
# project's own .venv cleanly and silently.
unset VIRTUAL_ENV || true

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
    --collect-all aalink \
    --hidden-import rtmidi \
    --hidden-import aalink \
    --add-data "$NATIVE_ROOT_DIR/controllers${DATA_SEP}controllers" \
    --osx-bundle-identifier "com.guillain.djmidi" \
    "$NATIVE_ROOT_DIR/src/djmidi/gui/app.py"

  if [[ "$OS_NAME" == "macos" ]]; then
    APP_PATH="$OUT_DIR/$APP_NAME.app"

    # PyInstaller's plain-script CLI mode (no .spec file, as used above) has
    # no flag for CFBundleShortVersionString/CFBundleVersion -- only its
    # BUNDLE() spec-file API takes a version= kwarg -- so every build
    # shipped "0.0.0" in Info.plist regardless of the real release version
    # (found while manually verifying the v0.47.92 release build actually
    # launches: `mdls`/Finder "Get Info" on the released .app showed
    # "0.0.0", the only place this app's version is exposed at all --
    # there's no in-app "About" dialog or version string). Patch it in
    # directly with PlistBuddy (bundled with Xcode CLT on every macOS
    # runner) rather than switching to a generated .spec file for this
    # alone. Must run *before* codesign below -- editing a signed bundle's
    # Info.plist invalidates the signature.
    APP_VERSION="$(sed -nE 's/^version = "([^"]+)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n 1)"
    if [[ -z "$APP_VERSION" ]]; then
      echo "Could not read version from pyproject.toml" >&2
      exit 1
    fi
    echo "==> Setting macOS bundle version to $APP_VERSION"
    PLIST_PATH="$APP_PATH/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST_PATH"
    # CFBundleVersion isn't in PyInstaller's default Info.plist at all (only
    # CFBundleShortVersionString is, defaulted to "0.0.0") -- Set fails on a
    # missing key, so try that first (in case a future PyInstaller version
    # starts including it) and fall back to Add.
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$PLIST_PATH" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$PLIST_PATH"

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
