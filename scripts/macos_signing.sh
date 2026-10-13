#!/usr/bin/env bash
set -euo pipefail

# macOS code signing and notarization for the PyInstaller-built app (issue
# #262). Every subcommand is a no-op that exits 0 with a "skipping" notice
# when its credentials are absent, so a fork, a pull request or a machine
# without an Apple Developer account builds an unsigned app exactly as
# before. A *partial* configuration (e.g. a notary key ID without its key)
# is an error instead: silently shipping an unnotarized app because one
# secret was mistyped is worse than a red build.
#
# Credentials only ever come from the environment (GitHub Actions secrets,
# or a developer's own shell) -- never from a file in the repository. The
# list of variables and how to create them is in
# docs/developer/cicd/macos-signing.md.
#
# MACOS_SIGNING_DRY_RUN=1 prints the commands (secrets masked) instead of
# running them; the test suite uses it to check the plumbing on any OS.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTITLEMENTS="${MACOS_ENTITLEMENTS:-$ROOT_DIR/packaging/macos/entitlements.plist}"
DRY_RUN="${MACOS_SIGNING_DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage:
  scripts/macos_signing.sh import-certificate
  scripts/macos_signing.sh sign <path/to/App.app>
  scripts/macos_signing.sh notarize <path/to/App.app>
  scripts/macos_signing.sh cleanup

import-certificate  Import MACOS_CERTIFICATE_P12_BASE64 (password:
                    MACOS_CERTIFICATE_PASSWORD) into a temporary keychain and
                    export MACOS_SIGNING_IDENTITY / MACOS_SIGNING_KEYCHAIN
                    (to $GITHUB_ENV when set, else printed as shell exports).
sign                Sign nested binaries inside-out, then the bundle with the
                    hardened runtime and packaging/macos/entitlements.plist.
                    Needs MACOS_SIGNING_IDENTITY.
notarize            Submit to Apple's notary service, staple the ticket and
                    check Gatekeeper. Needs either an App Store Connect API key
                    (MACOS_NOTARY_KEY_ID, MACOS_NOTARY_ISSUER_ID,
                    MACOS_NOTARY_KEY_P8_BASE64) or an Apple ID
                    (MACOS_NOTARY_APPLE_ID, MACOS_NOTARY_TEAM_ID,
                    MACOS_NOTARY_PASSWORD).
cleanup             Delete the temporary keychain created by import-certificate.

Each subcommand exits 0 and prints "skipping" when its credentials are absent.
EOF
}

log() { echo "==> $*"; }
skip() { echo "macOS signing: $* -- skipping."; }
die() { echo "macOS signing error: $*" >&2; exit 1; }

# Print a command with every secret value replaced by ***.
_masked() {
  local text="$*" secret
  for secret in "${MACOS_CERTIFICATE_PASSWORD:-}" "${MACOS_NOTARY_PASSWORD:-}" \
    "${_KEYCHAIN_PASSWORD:-}"; do
    if [[ -n "$secret" ]]; then
      text="${text//"$secret"/***}"
    fi
  done
  echo "+ $text"
}

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    _masked "$@"
  else
    "$@"
  fi
}

_require_macos() {
  if [[ "$DRY_RUN" != "1" && "$(uname -s)" != "Darwin" ]]; then
    die "$1 needs macOS (codesign/notarytool are Apple tools)"
  fi
}

_export_var() {
  local name="$1" value="$2"
  if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "$name=$value" >> "$GITHUB_ENV"
  else
    printf 'export %s=%q\n' "$name" "$value"
  fi
}

cmd_import_certificate() {
  if [[ -z "${MACOS_CERTIFICATE_P12_BASE64:-}" ]]; then
    skip "MACOS_CERTIFICATE_P12_BASE64 is not set"
    return 0
  fi
  if [[ -z "${MACOS_CERTIFICATE_PASSWORD:-}" ]]; then
    die "MACOS_CERTIFICATE_P12_BASE64 is set but MACOS_CERTIFICATE_PASSWORD is not"
  fi
  _require_macos import-certificate

  local work_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
  local keychain="$work_dir/djmidi-signing.keychain-db"
  local p12="$work_dir/djmidi-signing.p12"
  # A throwaway password for a throwaway keychain: generated here, never stored.
  _KEYCHAIN_PASSWORD="$(openssl rand -base64 24)"

  log "Importing the signing certificate into a temporary keychain"
  if [[ "$DRY_RUN" != "1" ]]; then
    printf '%s' "$MACOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$p12"
  fi
  run security create-keychain -p "$_KEYCHAIN_PASSWORD" "$keychain"
  run security set-keychain-settings -lut 21600 "$keychain"
  run security unlock-keychain -p "$_KEYCHAIN_PASSWORD" "$keychain"
  run security import "$p12" -P "$MACOS_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$keychain"
  run security set-key-partition-list -S apple-tool:,apple:,codesign: -s \
    -k "$_KEYCHAIN_PASSWORD" "$keychain"
  if [[ "$DRY_RUN" != "1" ]]; then
    rm -f "$p12"
    # Keep the login/system keychains searchable alongside the new one.
    local existing
    existing="$(security list-keychains -d user | sed -E 's/^[[:space:]]*"(.*)"$/\1/')"
    # shellcheck disable=SC2086
    security list-keychains -d user -s "$keychain" $existing
  fi

  local identity="${MACOS_SIGNING_IDENTITY:-}"
  if [[ -z "$identity" && "$DRY_RUN" != "1" ]]; then
    identity="$(security find-identity -v -p codesigning "$keychain" \
      | sed -nE 's/.*"(Developer ID Application: [^"]+)".*/\1/p' | head -n 1)"
  fi
  if [[ -z "$identity" && "$DRY_RUN" != "1" ]]; then
    die "the imported certificate holds no 'Developer ID Application' identity"
  fi
  _export_var MACOS_SIGNING_KEYCHAIN "$keychain"
  _export_var MACOS_SIGNING_IDENTITY "${identity:-<detected identity>}"
}

cmd_sign() {
  local app="${1:-}"
  [[ -n "$app" ]] || die "sign needs the path to the .app bundle"
  if [[ -z "${MACOS_SIGNING_IDENTITY:-}" ]]; then
    echo "WARNING: macOS app is unsigned (adhoc), not suitable for distribution."
    skip "MACOS_SIGNING_IDENTITY is not set (or pass --sign-identity to build.sh)"
    return 0
  fi
  [[ -d "$app" ]] || die "app bundle not found: $app"
  [[ -f "$ENTITLEMENTS" ]] || die "entitlements file not found: $ENTITLEMENTS"
  _require_macos sign

  local identity="$MACOS_SIGNING_IDENTITY"
  local common=(--force --options runtime)
  # An ad-hoc identity ("-", handy to rehearse locally) can't be timestamped.
  if [[ "$identity" == "-" ]]; then
    common+=(--timestamp=none)
  else
    common+=(--timestamp)
  fi
  if [[ -n "${MACOS_SIGNING_KEYCHAIN:-}" ]]; then
    common+=(--keychain "$MACOS_SIGNING_KEYCHAIN")
  fi

  log "Signing macOS app with identity: $identity"
  # Inside-out rather than `codesign --deep`: Apple's notary service expects
  # every nested Mach-O (Qt frameworks, Python extension modules, dylibs)
  # signed on its own, deepest first, before the enclosing bundle.
  local binary
  while IFS= read -r binary; do
    if file -b "$binary" 2>/dev/null | grep -q 'Mach-O'; then
      run codesign "${common[@]}" --sign "$identity" "$binary"
    fi
  done < <(find "$app/Contents" -type f ! -path "$app/Contents/MacOS/*" \
    | awk -F/ '{ print NF "\t" $0 }' | sort -rn | cut -f2-)
  local framework
  while IFS= read -r framework; do
    run codesign "${common[@]}" --sign "$identity" "$framework"
  done < <(find "$app/Contents" -type d -name '*.framework' \
    | awk -F/ '{ print NF "\t" $0 }' | sort -rn | cut -f2-)
  run codesign "${common[@]}" --entitlements "$ENTITLEMENTS" --sign "$identity" "$app"
  run codesign --verify --deep --strict --verbose=2 "$app"
}

cmd_notarize() {
  local app="${1:-}"
  [[ -n "$app" ]] || die "notarize needs the path to the .app bundle"

  local api_vars=(MACOS_NOTARY_KEY_ID MACOS_NOTARY_ISSUER_ID MACOS_NOTARY_KEY_P8_BASE64)
  local id_vars=(MACOS_NOTARY_APPLE_ID MACOS_NOTARY_TEAM_ID MACOS_NOTARY_PASSWORD)
  local name api_set=0 api_all=1 id_set=0 id_all=1
  for name in "${api_vars[@]}"; do
    if [[ -n "${!name:-}" ]]; then api_set=1; else api_all=0; fi
  done
  for name in "${id_vars[@]}"; do
    if [[ -n "${!name:-}" ]]; then id_set=1; else id_all=0; fi
  done

  if [[ "$api_set" -eq 0 && "$id_set" -eq 0 ]]; then
    skip "no notarization credentials are set"
    return 0
  fi
  if [[ "$api_set" -eq 1 && "$api_all" -eq 0 ]]; then
    die "incomplete App Store Connect API key: set all of ${api_vars[*]}"
  fi
  if [[ "$api_set" -eq 0 && "$id_all" -eq 0 ]]; then
    die "incomplete Apple ID credentials: set all of ${id_vars[*]}"
  fi
  if [[ -z "${MACOS_SIGNING_IDENTITY:-}" || "${MACOS_SIGNING_IDENTITY}" == "-" ]]; then
    die "notarization needs an app signed with a Developer ID identity (MACOS_SIGNING_IDENTITY)"
  fi
  [[ -d "$app" ]] || die "app bundle not found: $app"
  _require_macos notarize

  local work_dir key_file="" zip
  work_dir="$(mktemp -d)"
  _NOTARY_WORK_DIR="$work_dir"
  # The decoded API key must never outlive this script, even on failure.
  trap 'rm -rf "$_NOTARY_WORK_DIR"' EXIT
  zip="$work_dir/$(basename "$app" .app)-notarize.zip"

  local auth=()
  if [[ "$api_set" -eq 1 ]]; then
    key_file="$work_dir/AuthKey_${MACOS_NOTARY_KEY_ID}.p8"
    if [[ "$DRY_RUN" != "1" ]]; then
      (umask 077 && printf '%s' "$MACOS_NOTARY_KEY_P8_BASE64" | base64 --decode > "$key_file")
    fi
    auth=(--key "$key_file" --key-id "$MACOS_NOTARY_KEY_ID" --issuer "$MACOS_NOTARY_ISSUER_ID")
  else
    auth=(--apple-id "$MACOS_NOTARY_APPLE_ID" --team-id "$MACOS_NOTARY_TEAM_ID"
      --password "$MACOS_NOTARY_PASSWORD")
  fi

  log "Submitting $app for notarization (this usually takes a few minutes)"
  run ditto -c -k --sequesterRsrc --keepParent "$app" "$zip"
  if [[ "$DRY_RUN" == "1" ]]; then
    run xcrun notarytool submit "$zip" "${auth[@]}" --wait
  else
    local output submission_id
    output="$(xcrun notarytool submit "$zip" "${auth[@]}" --wait 2>&1)" || true
    echo "$output"
    if ! grep -qE 'status: Accepted' <<<"$output"; then
      submission_id="$(sed -nE 's/^[[:space:]]*id: ([0-9a-f-]+).*/\1/p' <<<"$output" | head -n 1)"
      if [[ -n "$submission_id" ]]; then
        xcrun notarytool log "$submission_id" "${auth[@]}" || true
      fi
      die "notarization was not accepted"
    fi
  fi
  run xcrun stapler staple "$app"
  run xcrun stapler validate "$app"
  run spctl --assess --type execute --verbose=4 "$app"
}

cmd_cleanup() {
  if [[ -z "${MACOS_SIGNING_KEYCHAIN:-}" ]]; then
    skip "no temporary keychain to delete"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" || -f "$MACOS_SIGNING_KEYCHAIN" ]]; then
    run security delete-keychain "$MACOS_SIGNING_KEYCHAIN"
  fi
}

case "${1:-}" in
  import-certificate) cmd_import_certificate ;;
  sign) cmd_sign "${2:-}" ;;
  notarize) cmd_notarize "${2:-}" ;;
  cleanup) cmd_cleanup ;;
  --help|-h) usage ;;
  *)
    usage >&2
    exit 2
    ;;
esac
