# macOS Signing and Notarization

> 🔏 How the release build signs (Developer ID, hardened runtime,
> entitlements) and notarizes the macOS app, which secrets turn it on, and
> what happens when they are absent.

📍 [Docs](../../README.md) › [Developer](../README.md) › [CI/CD](README.md) › macOS Signing and Notarization

## Table of Contents

- [Overview](#overview)
- [What runs where](#what-runs-where)
- [Secrets to add](#secrets-to-add)
- [Creating the credentials](#creating-the-credentials)
- [Entitlements](#entitlements)
- [Local use](#local-use)
- [Verifying a release](#verifying-a-release)
- [Related](#related)

## Overview

All of it lives in `scripts/macos_signing.sh` (issue #262), called by
`scripts/build.sh` and the `Draft Release` workflow. Every step is
**optional**: without credentials it prints `macOS signing: ... -- skipping.`
and exits 0, so forks, pull requests and branch builds produce the same
unsigned app as before and CI stays green with no secrets configured. A
*partial* configuration (say, a notary key ID without its key) fails the
build instead, so a mistyped secret can't silently ship an unnotarized app.

Credentials only come from the environment. Nothing is ever written to the
repository: the certificate goes into a throwaway keychain with a random
password, the App Store Connect key is decoded into a private temporary
directory deleted on exit, and dry-run output masks passwords.

## What runs where

| Step | Command | Needs |
| --- | --- | --- |
| Import certificate | `macos_signing.sh import-certificate` | `MACOS_CERTIFICATE_P12_BASE64`, `MACOS_CERTIFICATE_PASSWORD` |
| Sign | `macos_signing.sh sign <App.app>` (from `build.sh`) | `MACOS_SIGNING_IDENTITY` (exported by the import step) |
| Notarize, staple, assess | `macos_signing.sh notarize <App.app>` (from `build.sh`) | A complete API-key **or** Apple-ID set (below) and a Developer ID signature |
| Delete keychain | `macos_signing.sh cleanup` (always runs) | `MACOS_SIGNING_KEYCHAIN` |

Signing is inside-out instead of `codesign --deep`: every nested Mach-O file
(Qt libraries, Python extension modules) is signed deepest first with the
hardened runtime and a secure timestamp, then each `.framework`, then the
bundle itself with `packaging/macos/entitlements.plist`, and finally
`codesign --verify --deep --strict` checks the result. Notarization zips the
app with `ditto`, runs `xcrun notarytool submit --wait`, prints Apple's log
if the submission is not `Accepted`, then `xcrun stapler staple`,
`stapler validate` and `spctl --assess`. The stapled app is what
`scripts/release_artifacts.sh` zips.

Only `.github/workflows/draft-release.yml` (tag pushes, manual runs and the
merge-to-release call, which forwards secrets with `secrets: inherit`) passes
the secrets. `Build Executables` (every branch push and pull request) never
does. When an identity was imported, the release packages without
`--allow-unsigned`, so an app whose signature doesn't verify fails the
release rather than shipping.

The GitLab pipeline (`.gitlab-ci.yml`) still packages with
`--allow-unsigned`; set the same variables on a macOS runner and call the
script the same way to sign there.

## Secrets to add

Add these under **Settings → Secrets and variables → Actions → Repository
secrets**. Signing can be configured on its own, but Gatekeeper only opens
a downloaded app without a warning once it is also notarized.

Signing:

| Secret | Value |
| --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | The *Developer ID Application* certificate and its private key, exported as `.p12`, Base64-encoded on one line |
| `MACOS_CERTIFICATE_PASSWORD` | The password chosen when exporting the `.p12` |
| `MACOS_SIGNING_IDENTITY` | Optional. The full identity name, e.g. `Developer ID Application: Jane Doe (AB12CD34EF)`; detected from the certificate when omitted |

Notarization — **either** an App Store Connect API key (recommended, it
survives Apple ID password changes and two-factor prompts):

| Secret | Value |
| --- | --- |
| `MACOS_NOTARY_KEY_ID` | The key's ID (10 characters) |
| `MACOS_NOTARY_ISSUER_ID` | The issuer ID (a UUID shown above the keys list) |
| `MACOS_NOTARY_KEY_P8_BASE64` | The downloaded `AuthKey_<KEYID>.p8`, Base64-encoded on one line |

**or** an Apple ID:

| Secret | Value |
| --- | --- |
| `MACOS_NOTARY_APPLE_ID` | The Apple ID email of the developer account |
| `MACOS_NOTARY_TEAM_ID` | The 10-character Team ID |
| `MACOS_NOTARY_PASSWORD` | An app-specific password (not the account password) |

If both sets are present the API key wins.

## Creating the credentials

These need a paid Apple Developer Program membership (a maintainer
decision; nothing here works without one).

1. **Certificate.** In Xcode → Settings → Accounts → Manage Certificates, add
   a *Developer ID Application* certificate (or create it at
   developer.apple.com → Certificates). In Keychain Access, select it with its
   private key → Export → `.p12`, choosing a password. Then:

   ```bash
   base64 -i DeveloperID.p12 | tr -d '\n' | pbcopy   # → MACOS_CERTIFICATE_P12_BASE64
   ```

2. **API key.** App Store Connect → Users and Access → Integrations → App
   Store Connect API → Team Keys → generate a key with the *Developer* role.
   Download the `.p8` (only possible once), note the key ID and issuer ID, then:

   ```bash
   base64 -i AuthKey_AB12CD34EF.p8 | tr -d '\n' | pbcopy   # → MACOS_NOTARY_KEY_P8_BASE64
   ```

   Or, for the Apple ID route, create an app-specific password at
   account.apple.com → Sign-In and Security → App-Specific Passwords.

3. Delete the local `.p12`/`.p8` copies once stored as secrets, or keep them
   in a password manager — never in the repository.

## Entitlements

`packaging/macos/entitlements.plist` holds the hardened-runtime exceptions a
PyInstaller app needs: `allow-jit` and `allow-unsigned-executable-memory`
(the embedded CPython and ctypes/cffi modules such as rtmidi and aalink map
writable+executable memory) and `disable-library-validation` (the bootloader
loads the bundled Python library). The app is deliberately not sandboxed — it
opens arbitrary mapping files and CoreMIDI ports — so there is no
`app-sandbox` key. CoreMIDI and Ableton Link's local networking need no
entitlement outside the sandbox.

## Local use

```bash
# Sign with a certificate already in your login keychain, notarize with a key:
export MACOS_NOTARY_KEY_ID=... MACOS_NOTARY_ISSUER_ID=...
export MACOS_NOTARY_KEY_P8_BASE64="$(base64 -i AuthKey_XXXX.p8)"
bash scripts/build.sh --skip-python-package \
  --sign-identity "Developer ID Application: Jane Doe (AB12CD34EF)"

# Rehearse the signing path without a certificate (ad-hoc, not notarizable):
MACOS_SIGNING_IDENTITY=- bash scripts/build.sh --skip-python-package --skip-notarize

# Print what would run, without running it (any OS):
MACOS_SIGNING_DRY_RUN=1 MACOS_SIGNING_IDENTITY=- bash scripts/macos_signing.sh sign path/to/App.app
```

The ad-hoc rehearsal was checked on a real build: every nested binary and
the bundle sign with the hardened runtime and the entitlements, `codesign
--verify --deep --strict` passes, and the app starts. A Developer ID
signature and an actual notarization have not been exercised yet, since that
needs the account above.

## Verifying a release

```bash
codesign --verify --deep --strict --verbose=2 DJMidiStudio.app
codesign -dv --verbose=4 DJMidiStudio.app   # Authority=Developer ID Application: ..., flags=...(runtime)
xcrun stapler validate DJMidiStudio.app
spctl --assess --type execute --verbose DJMidiStudio.app   # source=Notarized Developer ID
```

`tests/test_macos_signing.py` covers the plumbing on every OS through the
dry-run mode: each step skips cleanly without credentials, partial
credentials fail, passwords and keys never reach the output, and only the
release workflow references the secrets.

## Related

- [Build and release](build-and-release.md)
- [Release checklist](release-checklist.md)
