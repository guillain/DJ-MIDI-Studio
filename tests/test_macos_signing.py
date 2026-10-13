"""scripts/macos_signing.sh (issue #262): every step must skip cleanly with
no Apple credentials (CI and forks have none), fail loudly on a half-set
configuration, and never print a secret. Runs on any OS through the script's
MACOS_SIGNING_DRY_RUN mode, which prints commands instead of running them."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "macos_signing.sh"
ENTITLEMENTS = ROOT / "packaging" / "macos" / "entitlements.plist"
WORKFLOWS = ROOT / ".github" / "workflows"

_SECRET_VARS = (
    "MACOS_CERTIFICATE_P12_BASE64",
    "MACOS_CERTIFICATE_PASSWORD",
    "MACOS_SIGNING_IDENTITY",
    "MACOS_SIGNING_KEYCHAIN",
    "MACOS_NOTARY_KEY_ID",
    "MACOS_NOTARY_ISSUER_ID",
    "MACOS_NOTARY_KEY_P8_BASE64",
    "MACOS_NOTARY_APPLE_ID",
    "MACOS_NOTARY_TEAM_ID",
    "MACOS_NOTARY_PASSWORD",
    "GITHUB_ENV",
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _run(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    base = {key: value for key, value in os.environ.items() if key not in _SECRET_VARS}
    base["MACOS_SIGNING_DRY_RUN"] = "1"
    base.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=base,
        timeout=60,
        check=False,
    )


@pytest.fixture
def app(tmp_path: Path) -> Path:
    bundle = tmp_path / "DJMidiStudio.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "MacOS" / "DJMidiStudio").write_text("not a real binary")
    return bundle


@pytest.mark.parametrize(
    "command", ["import-certificate", "sign", "notarize", "cleanup"]
)
def test_every_step_skips_cleanly_without_credentials(command, app):
    result = _run(command, str(app))
    assert result.returncode == 0, result.stderr
    assert "skipping" in result.stdout
    assert "+ " not in result.stdout  # no command was even attempted


def test_import_certificate_without_password_is_an_error():
    result = _run("import-certificate", MACOS_CERTIFICATE_P12_BASE64="AAAA")
    assert result.returncode != 0
    assert "MACOS_CERTIFICATE_PASSWORD" in result.stderr


def test_import_certificate_exports_to_github_env_and_masks_the_password(tmp_path):
    github_env = tmp_path / "github_env"
    result = _run(
        "import-certificate",
        MACOS_CERTIFICATE_P12_BASE64="AAAA",
        MACOS_CERTIFICATE_PASSWORD="hunter2-secret",
        MACOS_SIGNING_IDENTITY="Developer ID Application: Test (TEAMID1234)",
        GITHUB_ENV=str(github_env),
        RUNNER_TEMP=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert "hunter2-secret" not in result.stdout + result.stderr
    assert "security import" in result.stdout
    exported = github_env.read_text()
    assert (
        "MACOS_SIGNING_IDENTITY=Developer ID Application: Test (TEAMID1234)" in exported
    )
    assert "MACOS_SIGNING_KEYCHAIN=" in exported


def test_sign_uses_hardened_runtime_and_entitlements_on_the_bundle(app):
    result = _run(
        "sign", str(app), MACOS_SIGNING_IDENTITY="Developer ID Application: Test (T)"
    )
    assert result.returncode == 0, result.stderr
    lines = [
        line for line in result.stdout.splitlines() if line.startswith("+ codesign")
    ]
    bundle_sign = lines[-2]
    assert "--options runtime" in bundle_sign
    assert "--timestamp" in bundle_sign
    assert f"--entitlements {ENTITLEMENTS}" in bundle_sign
    assert bundle_sign.endswith(str(app))
    assert "--verify --deep --strict" in lines[-1]
    # Inside-out signing, never the deprecated `--deep` signing shortcut.
    assert not any("--deep" in line and "--sign" in line for line in lines)


def test_adhoc_identity_skips_the_timestamp(app):
    result = _run("sign", str(app), MACOS_SIGNING_IDENTITY="-")
    assert result.returncode == 0, result.stderr
    assert "--timestamp=none" in result.stdout


def test_sign_missing_bundle_is_an_error(tmp_path):
    result = _run("sign", str(tmp_path / "Nope.app"), MACOS_SIGNING_IDENTITY="X")
    assert result.returncode != 0
    assert "not found" in result.stderr


@pytest.mark.parametrize(
    "partial",
    [
        {"MACOS_NOTARY_KEY_ID": "KEY123"},
        {"MACOS_NOTARY_KEY_ID": "KEY123", "MACOS_NOTARY_ISSUER_ID": "issuer"},
        {
            "MACOS_NOTARY_APPLE_ID": "dj@example.com",
            "MACOS_NOTARY_TEAM_ID": "TEAMID1234",
        },
    ],
)
def test_notarize_with_incomplete_credentials_is_an_error(partial, app):
    result = _run(
        "notarize",
        str(app),
        MACOS_SIGNING_IDENTITY="Developer ID Application: T",
        **partial,
    )
    assert result.returncode != 0
    assert "incomplete" in result.stderr


def test_notarize_needs_a_developer_id_signature(app):
    result = _run(
        "notarize",
        str(app),
        MACOS_NOTARY_KEY_ID="KEY123",
        MACOS_NOTARY_ISSUER_ID="issuer",
        MACOS_NOTARY_KEY_P8_BASE64="AAAA",
    )
    assert result.returncode != 0
    assert "MACOS_SIGNING_IDENTITY" in result.stderr


def test_notarize_with_api_key_submits_staples_and_assesses(app):
    result = _run(
        "notarize",
        str(app),
        MACOS_SIGNING_IDENTITY="Developer ID Application: T",
        MACOS_NOTARY_KEY_ID="KEY123",
        MACOS_NOTARY_ISSUER_ID="issuer-uuid",
        MACOS_NOTARY_KEY_P8_BASE64="c2VjcmV0LWtleQ==",
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "xcrun notarytool submit" in out
    assert "--key-id KEY123 --issuer issuer-uuid" in out
    assert "--wait" in out
    assert "xcrun stapler staple" in out
    assert "spctl --assess --type execute" in out
    assert "c2VjcmV0LWtleQ==" not in out + result.stderr


def test_notarize_with_apple_id_masks_the_app_specific_password(app):
    result = _run(
        "notarize",
        str(app),
        MACOS_SIGNING_IDENTITY="Developer ID Application: T",
        MACOS_NOTARY_APPLE_ID="dj@example.com",
        MACOS_NOTARY_TEAM_ID="TEAMID1234",
        MACOS_NOTARY_PASSWORD="abcd-efgh-ijkl-mnop",
    )
    assert result.returncode == 0, result.stderr
    assert (
        "--apple-id dj@example.com --team-id TEAMID1234 --password ***" in result.stdout
    )
    assert "abcd-efgh-ijkl-mnop" not in result.stdout + result.stderr


def test_entitlements_allow_the_python_runtime_without_sandboxing():
    entitlements = plistlib.loads(ENTITLEMENTS.read_bytes())
    assert (
        entitlements["com.apple.security.cs.allow-unsigned-executable-memory"] is True
    )
    assert entitlements["com.apple.security.cs.disable-library-validation"] is True
    assert "com.apple.security.app-sandbox" not in entitlements


def test_secrets_only_reach_the_release_workflow():
    release = (WORKFLOWS / "draft-release.yml").read_text(encoding="utf-8")
    for name in (
        "MACOS_CERTIFICATE_P12_BASE64",
        "MACOS_NOTARY_KEY_P8_BASE64",
        "MACOS_NOTARY_PASSWORD",
    ):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in release
    assert "macos_signing.sh cleanup" in release
    # Branch/PR builds never see the signing secrets.
    assert "secrets." not in (WORKFLOWS / "build-executables.yml").read_text(
        encoding="utf-8"
    )
    # The reusable release call has to forward them explicitly.
    assert "secrets: inherit" in (WORKFLOWS / "tag-release-on-merge.yml").read_text(
        encoding="utf-8"
    )
